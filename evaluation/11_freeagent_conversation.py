"""
FreeAgent Evaluation 11: Multi-Turn with Conversation Manager

Same test cases as eval 04 (raw Ollama multi-turn baseline), but using
FreeAgent's new ConversationManager (default SlidingWindow). ONE Agent
per conversation, sequential run() calls — the conversation manager
handles context retention.

This replaces eval 07 which had no multi-turn state (fresh agent per turn).

Tests across: qwen3:8b, qwen3:4b, llama3.1:latest, gemma4:e2b
- gemma4:e2b uses ReactEngine (not in native_tool_models)

Measures:
- Per-turn: latency, tool calls, content accuracy
- Per-conversation: total latency, pass/fail, turn count
- FreeAgent metrics: last_run, turn_count
- ReactEngine-specific: parse errors, guardrail saves (gemma4:e2b)
"""

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
from freeagent import Agent, tool as freeagent_tool


# ── Tools (same as eval 04/07) ───────────────────────────

@freeagent_tool
def weather(city: str) -> dict:
    """Get current weather for a city.

    city: City name
    """
    mock_data = {
        "new york": {"temp_f": 72, "condition": "partly cloudy", "humidity": 55},
        "london": {"temp_f": 61, "condition": "rainy", "humidity": 80},
        "tokyo": {"temp_f": 85, "condition": "sunny", "humidity": 40},
        "paris": {"temp_f": 68, "condition": "overcast", "humidity": 65},
        "sydney": {"temp_f": 58, "condition": "clear", "humidity": 45},
    }
    key = city.lower().strip()
    for k, v in mock_data.items():
        if k in key:
            return {**v, "city": city}
    return {"city": city, "temp_f": 70, "condition": "unknown", "humidity": 50}


@freeagent_tool
def calculator(expression: str) -> dict:
    """Evaluate a math expression. Supports basic arithmetic.

    expression: Math expression like '2 + 3 * 4'
    """
    try:
        allowed = set("0123456789+-*/.() ")
        if not all(c in allowed for c in expression):
            return {"error": f"Invalid characters: {expression}"}
        result = eval(expression)
        return {"expression": expression, "result": result}
    except Exception as e:
        return {"error": str(e)}


@freeagent_tool
def unit_converter(value: float, from_unit: str, to_unit: str) -> dict:
    """Convert between common units (miles/km, fahrenheit/celsius, pounds/kg, feet/meters).

    value: Numeric value to convert
    from_unit: Unit to convert from
    to_unit: Unit to convert to
    """
    try:
        value = float(value)
    except (TypeError, ValueError):
        return {"error": f"Invalid value: {value}"}

    conversions = {
        ("miles", "km"): lambda v: v * 1.60934,
        ("km", "miles"): lambda v: v / 1.60934,
        ("fahrenheit", "celsius"): lambda v: (v - 32) * 5/9,
        ("celsius", "fahrenheit"): lambda v: v * 9/5 + 32,
        ("pounds", "kg"): lambda v: v * 0.453592,
        ("kg", "pounds"): lambda v: v / 0.453592,
        ("feet", "meters"): lambda v: v * 0.3048,
        ("meters", "feet"): lambda v: v / 0.3048,
    }
    key = (from_unit.lower().strip(), to_unit.lower().strip())
    if key in conversions:
        result = conversions[key](value)
        return {"value": value, "from": from_unit, "to": to_unit, "result": round(result, 2)}
    return {"error": f"Unknown conversion: {from_unit} to {to_unit}"}


TOOLS = [weather, calculator, unit_converter]


# ── Conversations (SAME as eval 04 — raw Ollama baseline) ─

CONVERSATIONS = [
    {
        "name": "weather_then_convert",
        "description": "Get weather, then ask to convert the temperature",
        "turns": [
            {
                "user": "What's the weather like in Tokyo right now?",
                "expected_tools": ["weather"],
                "expected_in_response": ["85", "sunny"],
            },
            {
                "user": "Can you convert that temperature to Celsius?",
                "expected_tools": ["unit_converter"],
                "expected_in_response": ["29"],
            },
        ],
    },
    {
        "name": "compare_two_cities",
        "description": "Check one city, then another, then compare",
        "turns": [
            {
                "user": "What's the weather in New York?",
                "expected_tools": ["weather"],
                "expected_in_response": ["72"],
            },
            {
                "user": "Now check London.",
                "expected_tools": ["weather"],
                "expected_in_response": ["61"],
            },
            {
                "user": "Which city is warmer and by how much?",
                "expected_tools": [],
                "expected_in_response": ["new york", "11"],
            },
        ],
    },
    {
        "name": "chained_conversion_and_calc",
        "description": "Convert units, then do math with the result",
        "turns": [
            {
                "user": "Convert 10 miles to kilometers.",
                "expected_tools": ["unit_converter"],
                "expected_in_response": ["16.09"],
            },
            {
                "user": "If I run that distance in 1.5 hours, what's my speed in km/h? Use the calculator.",
                "expected_tools": ["calculator"],
                "expected_in_response": ["10.7"],
            },
        ],
    },
    {
        "name": "context_retention_no_tools",
        "description": "First turn uses tool, second asks about the result without needing a tool",
        "turns": [
            {
                "user": "What's the weather in Paris?",
                "expected_tools": ["weather"],
                "expected_in_response": ["68", "overcast"],
            },
            {
                "user": "Based on that weather, should I bring an umbrella?",
                "expected_tools": [],
                "expected_in_response": ["yes"],
            },
        ],
    },
    {
        "name": "three_city_itinerary",
        "description": "Check weather for 3 cities one by one, then summarize",
        "turns": [
            {
                "user": "I'm planning a trip. First, what's the weather in Tokyo?",
                "expected_tools": ["weather"],
                "expected_in_response": ["tokyo"],
            },
            {
                "user": "What about Sydney?",
                "expected_tools": ["weather"],
                "expected_in_response": ["sydney"],
            },
            {
                "user": "And Paris?",
                "expected_tools": ["weather"],
                "expected_in_response": ["paris"],
            },
            {
                "user": "Rank these three cities from warmest to coldest.",
                "expected_tools": [],
                "expected_in_response": ["tokyo"],
            },
        ],
    },
    {
        "name": "correction_handling",
        "description": "User corrects a previous request mid-conversation",
        "turns": [
            {
                "user": "What's the temperature in London in Fahrenheit?",
                "expected_tools": ["weather"],
                "expected_in_response": ["61"],
            },
            {
                "user": "Actually, I meant Celsius. Convert it.",
                "expected_tools": ["unit_converter"],
                "expected_in_response": ["16"],
            },
        ],
    },
]

SYSTEM = "You are a helpful assistant. Use the provided tools when needed. Be concise."


def run_freeagent_conversation(suite: EvalSuite):
    """Evaluate FreeAgent with conversation manager (default SlidingWindow)."""
    for model in MODELS:
        print(f"\n  FreeAgent (conversation) / {model}")

        # Detect if this model will use ReactEngine
        from freeagent.config import AgentConfig
        is_react = not AgentConfig().supports_native_tools(model)
        if is_react:
            print(f"    [ReactEngine — {model} not in native_tool_models]")

        for convo in CONVERSATIONS:
            print(f"\n    Conversation: {convo['name']}")

            # ONE agent per conversation — conversation manager persists state
            agent = Agent(
                model=model,
                system_prompt=SYSTEM,
                tools=TOOLS,
                # Default SlidingWindow(max_turns=20) — just use the default
            )

            conv_start = time.monotonic()
            all_passed = True
            conv_notes = []

            for i, turn in enumerate(convo["turns"]):
                result = EvalResult(
                    name=f"{convo['name']}_turn{i+1}",
                    framework="freeagent_conversation",
                    model=model,
                    prompt=turn["user"],
                    tool_calls_expected=len(turn["expected_tools"]),
                )

                try:
                    start = time.monotonic()
                    response = agent.run(turn["user"])
                    elapsed_ms = (time.monotonic() - start) * 1000

                    result.response = response or ""
                    result.success = True
                    result.latency_ms = elapsed_ms

                    # Extract FreeAgent metrics
                    run_record = agent.metrics.runs[-1] if agent.metrics.runs else None
                    if run_record:
                        result.tool_calls_made = run_record.tool_call_count
                        eval_tools = [t for t in run_record.tools_used if t != "memory"]
                        val_errors = run_record.validation_errors
                        retries = run_record.retries
                    else:
                        eval_tools = []
                        val_errors = 0
                        retries = 0

                    # Check correctness
                    tools_match = sorted(eval_tools) == sorted(turn["expected_tools"])
                    content_match = check_response_contains(
                        result.response, turn["expected_in_response"],
                    )
                    result.correct = tools_match and content_match

                    # Build notes
                    notes = []
                    if is_react:
                        notes.append("react")
                    if val_errors:
                        notes.append(f"val_errors:{val_errors}")
                    if retries:
                        notes.append(f"retries:{retries}")
                    if not tools_match:
                        notes.append(f"tools_expected:{turn['expected_tools']} got:{eval_tools}")
                    if not content_match:
                        notes.append("content_miss")
                    notes.append(f"turns:{agent.conversation.turn_count}")
                    result.notes = " ".join(notes)

                    if not result.correct:
                        all_passed = False

                    status = "PASS" if result.correct else "FAIL"
                    print(f"      Turn {i+1}: {status}  {elapsed_ms:7.0f}ms  {result.notes}")

                except Exception as e:
                    result.error = str(e)[:200]
                    all_passed = False
                    print(f"      Turn {i+1}: ERR  {str(e)[:80]}")

                suite.add(result)

            conv_elapsed = (time.monotonic() - conv_start) * 1000
            conv_status = "PASS" if all_passed else "FAIL"
            print(f"    -> {conv_status}  total:{conv_elapsed:7.0f}ms  turns:{agent.conversation.turn_count}")

            # Clear conversation for next test case
            agent.conversation.clear()


def main():
    suite = EvalSuite(name="FreeAgent Conversation Multi-Turn")

    print("\n" + "=" * 60)
    print("  EVAL 11: FreeAgent Multi-Turn with Conversation Manager")
    print("=" * 60)

    check_ollama()

    print("\n-- FreeAgent with SlidingWindow (default) --")
    run_freeagent_conversation(suite)

    suite.print_report()
    save_results(suite, "freeagent_conversation_results.json")

    # Print per-conversation summary
    print("\n" + "=" * 60)
    print("  PER-CONVERSATION SUMMARY")
    print("=" * 60)

    for model in MODELS:
        print(f"\n  {model}:")
        for convo in CONVERSATIONS:
            turns = [
                r for r in suite.results
                if r.model == model and r.name.startswith(convo["name"])
            ]
            passed = all(r.correct for r in turns)
            total_ms = sum(r.latency_ms for r in turns)
            status = "PASS" if passed else "FAIL"
            turn_details = " | ".join(
                "OK" if r.correct else "FAIL" for r in turns
            )
            print(f"    {convo['name']:30s} {status}  {total_ms:7.0f}ms  [{turn_details}]")

    print()


if __name__ == "__main__":
    main()
