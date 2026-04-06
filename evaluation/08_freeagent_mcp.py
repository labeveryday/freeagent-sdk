"""
FreeAgent Evaluation 8: MCP Tool Calling with NBA Stats

Same cases as eval 03, but using FreeAgent Agent + freeagent.mcp.connect().
Tests FreeAgent's MCP integration end-to-end.
"""

import asyncio
import json
import time
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from eval_utils import (
    EvalResult, EvalSuite, MODELS,
    check_response_contains, check_ollama, save_results,
)

sys.path.insert(0, str(Path(__file__).parent.parent))
from freeagent import Agent
from freeagent.mcp import connect

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


async def run_freeagent_mcp(suite: EvalSuite):
    """Evaluate FreeAgent Agent with MCP tools."""
    mcp_command = f"{sys.executable} -m nba_mcp_server"

    async with connect(command=mcp_command) as mcp_tools:
        print(f"  FreeAgent MCP connected — {len(mcp_tools)} tools available")
        tool_names = [t.name for t in mcp_tools]
        print(f"  Tools: {tool_names[:10]}{'...' if len(tool_names) > 10 else ''}")

        for model in MODELS:
            print(f"\n  FreeAgent + MCP / {model}")

            for case in CASES:
                agent = Agent(
                    model=model,
                    system_prompt=SYSTEM,
                    tools=mcp_tools,
                )

                ev = EvalResult(
                    name=case["name"], framework="freeagent_mcp",
                    model=model, prompt=case["prompt"],
                )

                try:
                    start = time.monotonic()
                    # Use arun() directly since we're already in an async context.
                    # agent.run() -> SyncBridge -> background thread, which can't
                    # share the MCP session's event loop for tool calls.
                    response = await agent.arun(case["prompt"])
                    elapsed_ms = (time.monotonic() - start) * 1000

                    ev.response = response or ""
                    ev.success = True
                    ev.latency_ms = elapsed_ms

                    run = agent.metrics.runs[-1] if agent.metrics.runs else None
                    if run:
                        ev.tool_calls_made = run.tool_call_count
                        eval_tools = [t for t in run.tools_used if t != "memory"]
                        val_errors = run.validation_errors
                    else:
                        eval_tools = []
                        val_errors = 0

                    ev.correct = check_response_contains(
                        ev.response, case["expected_in_response"],
                    )

                    notes = []
                    if val_errors:
                        notes.append(f"val_errors:{val_errors}")
                    if run and run.loop_detected:
                        notes.append("LOOP")
                    if run and run.max_iter_hit:
                        notes.append("MAX_ITER")
                    ev.notes = " ".join(notes)

                    status = "PASS" if ev.correct else "FAIL"
                    print(f"    {status} {case['name']:25s} [{case['complexity']:7s}] {elapsed_ms:7.0f}ms  tools:{eval_tools}  {ev.notes}")

                except Exception as e:
                    ev.error = str(e)[:200]
                    print(f"    ERR  {case['name']:25s} {str(e)[:80]}")

                suite.add(ev)


async def async_main():
    suite = EvalSuite(name="FreeAgent MCP NBA Stats")

    print("\n" + "="*60)
    print("  EVAL 8: FreeAgent + MCP NBA Stats")
    print("="*60)

    check_ollama()

    print("\n-- FreeAgent Agent + MCP --")
    await run_freeagent_mcp(suite)

    suite.print_report()
    save_results(suite, "freeagent_mcp_results.json")


if __name__ == "__main__":
    asyncio.run(async_main())
