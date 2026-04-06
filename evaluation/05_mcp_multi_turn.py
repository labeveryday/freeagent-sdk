"""
Baseline Evaluation 5: Multi-Turn MCP — NBA Stats Conversations

Real conversational NBA queries using the nba-stats-mcp server.
Tests context retention, complex tool orchestration, and multi-step reasoning
across turns with live NBA data.

Conversations:
1. LeBron vs MJ GOAT debate (compare + awards + reasoning)
2. MJ vs Kobe + best/worst performances (compare + awards + game logs)
3. Team deep dive across turns (overview + player stats + advanced metrics)
4. Scoring leaders drill-down (leaders + compare + shooting)
5. Player career arc (profile + career stats + awards + compare)

Tests across: qwen3:8b, qwen3:4b, llama3.1:latest
"""

import asyncio
import json
import time
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from eval_utils import (
    EvalResult, EvalSuite, MODELS, OLLAMA_BASE_URL,
    ollama_chat, check_response_contains,
    check_ollama, save_results,
    extract_strands_metrics, format_strands_metrics,
)

CONVERSATIONS = [
    {
        "name": "lebron_vs_mj",
        "description": "GOAT debate: LeBron James vs Michael Jordan",
        "turns": [
            {
                "user": "Who is better, LeBron James or Michael Jordan? Compare their career stats.",
                "expected_in_response": ["lebron", "jordan"],
                "min_tools": 1,
            },
            {
                "user": "What about their awards? Who has more MVPs and championships?",
                "expected_in_response": ["mvp"],
                "min_tools": 1,
            },
            {
                "user": "Based on everything you've found, who do you think is the GOAT and why?",
                "expected_in_response": [],
                "min_tools": 0,
            },
        ],
    },
    {
        "name": "mj_vs_kobe_deep",
        "description": "MJ vs Kobe with best/worst performances",
        "turns": [
            {
                "user": "Who is better, Michael Jordan or Kobe Bryant? Compare their stats side by side.",
                "expected_in_response": ["jordan", "kobe"],
                "min_tools": 1,
            },
            {
                "user": "What are their career highlights and awards?",
                "expected_in_response": [],
                "min_tools": 1,
            },
            {
                "user": "Can you look at their game logs and tell me about their best and worst performances?",
                "expected_in_response": [],
                "min_tools": 1,
            },
            {
                "user": "So overall, who had the better career and why?",
                "expected_in_response": [],
                "min_tools": 0,
            },
        ],
    },
    {
        "name": "team_exploration",
        "description": "Deep dive into a team across multiple turns",
        "turns": [
            {
                "user": "Give me a full overview of the Golden State Warriors.",
                "expected_in_response": ["warriors"],
                "min_tools": 1,
            },
            {
                "user": "Who is their best player right now? Show me their stats.",
                "expected_in_response": [],
                "min_tools": 1,
            },
            {
                "user": "How do the Warriors compare to the Celtics in terms of advanced metrics?",
                "expected_in_response": ["warriors", "celtics"],
                "min_tools": 1,
            },
        ],
    },
    {
        "name": "scoring_leaders_drill",
        "description": "Start from league leaders, drill into specific players",
        "turns": [
            {
                "user": "Who are the top 5 scoring leaders in the NBA this season?",
                "expected_in_response": ["points"],
                "min_tools": 1,
            },
            {
                "user": "Compare the top 2 scorers head to head.",
                "expected_in_response": [],
                "min_tools": 1,
            },
            {
                "user": "What are the shooting splits for the #1 scorer?",
                "expected_in_response": [],
                "min_tools": 1,
            },
        ],
    },
    {
        "name": "player_career_arc",
        "description": "Explore a player's full career across turns",
        "turns": [
            {
                "user": "Tell me about Stephen Curry's profile and bio.",
                "expected_in_response": ["curry"],
                "min_tools": 1,
            },
            {
                "user": "What are his career stats?",
                "expected_in_response": [],
                "min_tools": 1,
            },
            {
                "user": "How about his awards and accolades?",
                "expected_in_response": [],
                "min_tools": 1,
            },
            {
                "user": "Now compare him to Kevin Durant.",
                "expected_in_response": ["durant"],
                "min_tools": 1,
            },
        ],
    },
]

SYSTEM = (
    "You are an NBA stats expert. Use the provided tools to look up real stats — "
    "never guess or make up numbers. When comparing players, use the compare_players tool "
    "or look up each player's stats. Be concise but thorough."
)


def mcp_tools_to_ollama(tools) -> list[dict]:
    """Convert MCP tool list to Ollama tool spec format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": t.inputSchema if t.inputSchema else {
                    "type": "object", "properties": {},
                },
            },
        }
        for t in tools
    ]


async def run_turn_mcp(session, model: str, messages: list[dict],
                       ollama_tools: list, max_iterations: int = 6):
    """
    Run one conversation turn through Ollama with MCP tools.
    Mutates messages in place. Returns (response, tool_calls, latency_ms, tokens, tps).
    """
    total_latency = 0
    total_tokens = 0
    total_eval_duration = 0
    tool_calls_made = []

    for _ in range(max_iterations):
        start = time.monotonic()
        resp = ollama_chat(model, messages, ollama_tools)
        elapsed = (time.monotonic() - start) * 1000
        total_latency += elapsed
        total_tokens += resp.get("eval_count", 0)
        total_eval_duration += resp.get("eval_duration", 0)

        msg = resp.get("message", {})
        tool_calls = msg.get("tool_calls", [])

        if not tool_calls:
            messages.append({"role": "assistant", "content": msg.get("content", "")})
            tps = (total_tokens / total_eval_duration * 1e9) if total_eval_duration > 0 else 0
            return msg.get("content", ""), tool_calls_made, total_latency, total_tokens, tps

        messages.append(msg)

        for tc in tool_calls:
            fn_name = tc.get("function", {}).get("name", "")
            fn_args = tc.get("function", {}).get("arguments", {})
            tool_calls_made.append({"name": fn_name, "args": fn_args})

            try:
                result = await session.call_tool(fn_name, fn_args)
                texts = [c.text for c in result.content if hasattr(c, "text")]
                tool_result = "\n".join(texts) if texts else str(result.content)
            except Exception as e:
                tool_result = json.dumps({"error": str(e)})

            messages.append({"role": "tool", "content": tool_result[:3000]})

    messages.append({"role": "assistant", "content": "[Max iterations reached]"})
    tps = (total_tokens / total_eval_duration * 1e9) if total_eval_duration > 0 else 0
    return "[Max iterations]", tool_calls_made, total_latency, total_tokens, tps


async def run_ollama_raw_mcp(suite: EvalSuite):
    """Run multi-turn conversations with raw Ollama + MCP."""
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client, StdioServerParameters

    server_params = StdioServerParameters(
        command=sys.executable, args=["-m", "nba_mcp_server"],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.list_tools()
            ollama_tools = mcp_tools_to_ollama(result.tools)
            print(f"  MCP server ready — {len(ollama_tools)} tools available")

            for model in MODELS:
                print(f"\n  Raw Ollama + MCP / {model}")

                for convo in CONVERSATIONS:
                    print(f"\n    Conversation: {convo['name']}")
                    messages = [{"role": "system", "content": SYSTEM}]
                    convo_total_latency = 0
                    convo_total_tools = 0
                    all_passed = True

                    for i, turn in enumerate(convo["turns"]):
                        messages.append({"role": "user", "content": turn["user"]})

                        ev = EvalResult(
                            name=f"{convo['name']}_turn{i+1}",
                            framework="ollama_raw_mcp", model=model,
                            prompt=turn["user"],
                        )

                        try:
                            response, tool_calls, latency, tokens, tps = await run_turn_mcp(
                                session, model, messages, ollama_tools,
                            )

                            ev.response = response
                            ev.success = True
                            ev.latency_ms = latency
                            ev.tokens_generated = tokens
                            ev.tokens_per_second = tps
                            ev.tool_calls_made = len(tool_calls)

                            convo_total_latency += latency
                            convo_total_tools += len(tool_calls)

                            # Content check
                            if turn["expected_in_response"]:
                                full_text = response + " " + json.dumps(tool_calls)
                                ev.correct = check_response_contains(full_text, turn["expected_in_response"])
                            else:
                                ev.correct = len(response) > 20

                            # Min tools check
                            if turn["min_tools"] > 0 and len(tool_calls) < turn["min_tools"]:
                                ev.correct = False
                                ev.notes = f"Expected >= {turn['min_tools']} tool calls, got {len(tool_calls)}"

                            if not ev.correct:
                                all_passed = False

                            status = "PASS" if ev.correct else "FAIL"
                            tools_used = [tc["name"] for tc in tool_calls]
                            tools_str = ", ".join(tools_used) if tools_used else "none"
                            print(f"      Turn {i+1}: {status}  {latency:7.0f}ms  {tps:5.1f} t/s  tools:[{tools_str}]")
                        except Exception as e:
                            ev.error = str(e)[:200]
                            all_passed = False
                            print(f"      Turn {i+1}: ERR   {str(e)[:80]}")

                        suite.add(ev)

                    print(f"    -> {'PASS' if all_passed else 'FAIL'}  total: {convo_total_latency:.0f}ms  {convo_total_tools} tool calls")


async def run_strands_mcp(suite: EvalSuite):
    """Run multi-turn conversations with Strands + MCP."""
    from strands import Agent
    from strands.models.ollama import OllamaModel
    from strands.tools.mcp import MCPClient
    from mcp.client.stdio import StdioServerParameters, stdio_client

    server_params = StdioServerParameters(
        command=sys.executable, args=["-m", "nba_mcp_server"],
    )

    mcp_client = MCPClient(lambda: stdio_client(server_params))

    with mcp_client:
        tools = mcp_client.list_tools_sync()
        print(f"  Strands MCP client started — {len(tools)} tools")

        for model in MODELS:
            print(f"\n  Strands + MCP / {model}")

            for convo in CONVERSATIONS:
                print(f"\n    Conversation: {convo['name']}")

                convo_total_latency = 0
                all_passed = True

                # Fresh agent per conversation — maintains state across turns.
                # Pass resolved tools (not the client) to avoid re-start error.
                ollama_model = OllamaModel(
                    host=OLLAMA_BASE_URL, model_id=model, temperature=0.1,
                )
                agent = Agent(
                    model=ollama_model, system_prompt=SYSTEM,
                    tools=tools,
                )

                for i, turn in enumerate(convo["turns"]):
                    ev = EvalResult(
                        name=f"{convo['name']}_turn{i+1}",
                        framework="strands_mcp", model=model,
                        prompt=turn["user"],
                    )

                    try:
                        start = time.monotonic()
                        response = agent(turn["user"])
                        elapsed_ms = (time.monotonic() - start) * 1000

                        content = str(response)
                        ev.response = content
                        ev.success = True
                        ev.latency_ms = elapsed_ms
                        convo_total_latency += elapsed_ms

                        # Extract real metrics from Strands
                        sm = extract_strands_metrics(agent)
                        ev.tool_calls_made = sm["total_tool_calls"]
                        ev.tokens_generated = sm["total_tokens"]

                        if turn["expected_in_response"]:
                            ev.correct = check_response_contains(content, turn["expected_in_response"])
                        else:
                            ev.correct = len(content) > 20

                        # Min tools check — now using real tool call count
                        if turn["min_tools"] > 0 and sm["total_tool_calls"] < turn["min_tools"]:
                            ev.correct = False
                            ev.notes = f"Expected >= {turn['min_tools']} tool calls, got {sm['total_tool_calls']}"
                        else:
                            ev.notes = f"cycles:{sm['cycles']} tokens:{sm['total_tokens']}"

                        if not ev.correct:
                            all_passed = False

                        status = "PASS" if ev.correct else "FAIL"
                        print(f"      Turn {i+1}: {status}  {elapsed_ms:7.0f}ms  {format_strands_metrics(sm)}")
                    except Exception as e:
                        ev.error = str(e)[:200]
                        all_passed = False
                        print(f"      Turn {i+1}: ERR   {str(e)[:80]}")

                    suite.add(ev)

                print(f"    -> {'PASS' if all_passed else 'FAIL'}  total: {convo_total_latency:.0f}ms")


async def async_main():
    suite = EvalSuite(name="Multi-Turn MCP — NBA Conversations")

    print("\n" + "="*60)
    print("  EVAL 5: Multi-Turn MCP — NBA Stats Conversations")
    print("="*60)

    check_ollama()

    print("\n-- Raw Ollama API + MCP --")
    await run_ollama_raw_mcp(suite)

    print("\n-- Strands Agents + MCP --")
    await run_strands_mcp(suite)

    suite.print_report()
    save_results(suite, "mcp_multi_turn_results.json")


if __name__ == "__main__":
    asyncio.run(async_main())
