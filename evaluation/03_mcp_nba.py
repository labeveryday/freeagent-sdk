"""
Baseline Evaluation 3: MCP Tool Calling — nba-stats-mcp

Tests real MCP tool calling with the NBA Stats MCP server.
Measures TPS, accuracy, latency with single-turn queries.

Runs nba-stats-mcp as a subprocess via stdio transport, then:
1. Raw Ollama API + manual MCP client loop
2. Strands Agents + MCP integration

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

CASES = [
    {
        "name": "team_lookup",
        "prompt": "Look up the team ID for the Los Angeles Lakers.",
        "expected_in_response": ["lakers"],
        "complexity": "simple",
    },
    {
        "name": "player_lookup",
        "prompt": "Look up LeBron James player info.",
        "expected_in_response": ["lebron", "james"],
        "complexity": "simple",
    },
    {
        "name": "standings",
        "prompt": "What are the current NBA standings? Show the top teams in the Eastern conference.",
        "expected_in_response": ["east"],
        "complexity": "simple",
    },
    {
        "name": "player_stats",
        "prompt": "What are LeBron James's season stats?",
        "expected_in_response": ["lebron"],
        "complexity": "medium",
    },
    {
        "name": "team_roster",
        "prompt": "Who is on the Boston Celtics roster?",
        "expected_in_response": ["celtics"],
        "complexity": "medium",
    },
    {
        "name": "compare_players",
        "prompt": "Compare LeBron James and Stephen Curry stats side by side.",
        "expected_in_response": ["lebron", "curry"],
        "complexity": "complex",
    },
    {
        "name": "team_deep_dive",
        "prompt": "Give me a complete overview of the Golden State Warriors — roster, record, and upcoming schedule.",
        "expected_in_response": ["warriors"],
        "complexity": "complex",
    },
    {
        "name": "league_leaders",
        "prompt": "Who are the current NBA scoring leaders this season?",
        "expected_in_response": ["points"],
        "complexity": "medium",
    },
]

SYSTEM = (
    "You are an NBA stats assistant. Use the provided tools to answer questions about NBA "
    "players, teams, games, and stats. Always use tools rather than guessing. Be concise."
)


async def mcp_tool_loop(session, model: str, prompt: str,
                         ollama_tools: list, max_iterations: int = 5) -> dict:
    """Run Ollama tool loop with MCP tools as the backend."""
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": prompt},
    ]

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
            tps = (total_tokens / total_eval_duration * 1e9) if total_eval_duration > 0 else 0
            return {
                "response": msg.get("content", ""),
                "tool_calls": tool_calls_made,
                "latency_ms": total_latency,
                "tokens": total_tokens,
                "tps": tps,
            }

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

            messages.append({"role": "tool", "content": tool_result[:2000]})

    tps = (total_tokens / total_eval_duration * 1e9) if total_eval_duration > 0 else 0
    return {
        "response": "[Max iterations reached]",
        "tool_calls": tool_calls_made,
        "latency_ms": total_latency,
        "tokens": total_tokens,
        "tps": tps,
    }


def mcp_tools_to_ollama(tools) -> list[dict]:
    """Convert MCP tool list to Ollama tool spec format."""
    ollama_tools = []
    for tool in tools:
        ollama_tools.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema if tool.inputSchema else {
                    "type": "object", "properties": {},
                },
            },
        })
    return ollama_tools


async def run_ollama_raw_mcp(suite: EvalSuite):
    """Run eval with raw Ollama API + MCP tools."""
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
                for case in CASES:
                    ev = EvalResult(
                        name=case["name"], framework="ollama_raw_mcp",
                        model=model, prompt=case["prompt"],
                    )

                    try:
                        r = await mcp_tool_loop(session, model, case["prompt"], ollama_tools)

                        ev.response = r["response"]
                        ev.success = True
                        ev.latency_ms = r["latency_ms"]
                        ev.tokens_generated = r["tokens"]
                        ev.tokens_per_second = r["tps"]
                        ev.tool_calls_made = len(r["tool_calls"])

                        full_text = r["response"] + " " + json.dumps(r["tool_calls"])
                        ev.correct = check_response_contains(full_text, case["expected_in_response"])

                        actual_tools = [tc["name"] for tc in r["tool_calls"]]
                        status = "PASS" if ev.correct else "FAIL"
                        print(f"    {status} {case['name']:25s} [{case['complexity']:7s}] {r['latency_ms']:7.0f}ms  {r['tps']:5.1f} t/s  tools:{actual_tools}")
                    except Exception as e:
                        ev.error = str(e)[:200]
                        print(f"    ERR  {case['name']:25s} {str(e)[:80]}")

                    suite.add(ev)


async def run_strands_mcp(suite: EvalSuite):
    """Run eval with Strands Agents + MCP."""
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

            for case in CASES:
                ev = EvalResult(
                    name=case["name"], framework="strands_mcp",
                    model=model, prompt=case["prompt"],
                )

                try:
                    ollama_model = OllamaModel(
                        host=OLLAMA_BASE_URL, model_id=model, temperature=0.1,
                    )
                    agent = Agent(
                        model=ollama_model, system_prompt=SYSTEM,
                        tools=tools,
                    )

                    start = time.monotonic()
                    response = agent(case["prompt"])
                    elapsed_ms = (time.monotonic() - start) * 1000

                    content = str(response)
                    ev.response = content
                    ev.success = True
                    ev.latency_ms = elapsed_ms
                    ev.correct = check_response_contains(content, case["expected_in_response"])

                    # Extract real metrics from Strands
                    sm = extract_strands_metrics(agent)
                    ev.tool_calls_made = sm["total_tool_calls"]
                    ev.tokens_generated = sm["total_tokens"]
                    ev.notes = f"cycles:{sm['cycles']} tokens:{sm['total_tokens']} duration:{sm['total_duration']:.2f}s"

                    status = "PASS" if ev.correct else "FAIL"
                    print(f"    {status} {case['name']:25s} [{case['complexity']:7s}] {elapsed_ms:7.0f}ms  {format_strands_metrics(sm)}")
                except Exception as e:
                    ev.error = str(e)[:200]
                    print(f"    ERR  {case['name']:25s} {str(e)[:80]}")

                suite.add(ev)


async def async_main():
    suite = EvalSuite(name="MCP NBA Stats Baseline")

    print("\n" + "="*60)
    print("  EVAL 3: MCP Tool Calling — NBA Stats")
    print("="*60)

    check_ollama()

    print("\n-- Raw Ollama API + MCP --")
    await run_ollama_raw_mcp(suite)

    print("\n-- Strands Agents + MCP --")
    await run_strands_mcp(suite)

    suite.print_report()
    save_results(suite, "mcp_nba_results.json")


if __name__ == "__main__":
    asyncio.run(async_main())
