"""
FreeAgent Evaluation 7: Multi-Turn Tool Calling

Same cases as eval 04, but using FreeAgent Agent.

IMPORTANT: FreeAgent Agent.run() creates a fresh conversation each time.
There is no built-in conversation history. Each run() is independent.
This means multi-turn tests where later turns reference prior results
will rely on:
  1. Skills/system prompt giving context
  2. The user explicitly restating context in the prompt

This eval tests FreeAgent's single-shot capability on each turn independently,
providing context in the prompt where needed. This is a realistic test of how
users would actually use FreeAgent for multi-step tasks.
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


# Same tools as eval 06
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

# Multi-turn conversations adapted for FreeAgent's single-shot model.
# Each turn is self-contained with enough context to work independently.
CONVERSATIONS = [
    {
        "name": "weather_then_convert",
        "description": "Get weather, then convert the temperature",
        "turns": [
            {
                "user": "What's the weather like in Tokyo right now?",
                "expected_tools": ["weather"],
                "expected_in_response": ["85", "sunny"],
            },
            {
                # Self-contained: includes the value from the previous turn
                "user": "The temperature in Tokyo is 85°F. Convert that to Celsius.",
                "expected_tools": ["unit_converter"],
                "expected_in_response": ["29"],
            },
        ],
    },
    {
        "name": "compare_two_cities",
        "description": "Check two cities and compare",
        "turns": [
            {
                "user": "What's the weather in New York?",
                "expected_tools": ["weather"],
                "expected_in_response": ["72"],
            },
            {
                "user": "What's the weather in London?",
                "expected_tools": ["weather"],
                "expected_in_response": ["61"],
            },
            {
                # Self-contained comparison
                "user": "New York is 72°F and London is 61°F. Which city is warmer and by how much?",
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
                "user": "If I run 16.09 km in 1.5 hours, what's my speed in km/h? Use the calculator to divide 16.09 by 1.5.",
                "expected_tools": ["calculator"],
                "expected_in_response": ["10.7"],
            },
        ],
    },
    {
        "name": "context_retention_no_tools",
        "description": "First turn uses tool, second asks about the result",
        "turns": [
            {
                "user": "What's the weather in Paris?",
                "expected_tools": ["weather"],
                "expected_in_response": ["68", "overcast"],
            },
            {
                "user": "The weather in Paris is overcast with humidity at 65%. Should I bring an umbrella?",
                "expected_tools": [],
                "expected_in_response": ["yes"],
            },
        ],
    },
]

SYSTEM = "You are a helpful assistant. Use the provided tools when needed. Be concise."


def run_freeagent_multi_turn(suite: EvalSuite):
    """Evaluate FreeAgent on multi-turn conversations (each turn independent)."""
    for model in MODELS:
        print(f"\n  FreeAgent / {model}")

        for conv in CONVERSATIONS:
            print(f"    Conversation: {conv['name']}")

            for i, turn in enumerate(conv["turns"]):
                # Fresh agent per turn (FreeAgent has no multi-turn state)
                agent = Agent(
                    model=model,
                    system_prompt=SYSTEM,
                    tools=TOOLS,
                )

                result = EvalResult(
                    name=f"{conv['name']}_turn{i}",
                    framework="freeagent",
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

                    run = agent.metrics.runs[-1] if agent.metrics.runs else None
                    if run:
                        result.tool_calls_made = run.tool_call_count
                        eval_tools = [t for t in run.tools_used if t != "memory"]
                        val_errors = run.validation_errors
                    else:
                        eval_tools = []
                        val_errors = 0

                    tools_match = sorted(eval_tools) == sorted(turn["expected_tools"])
                    content_match = check_response_contains(
                        result.response, turn["expected_in_response"],
                    )
                    result.correct = tools_match and content_match

                    notes = []
                    if val_errors:
                        notes.append(f"val_errors:{val_errors}")
                    if not tools_match:
                        notes.append(f"tools({eval_tools})")
                    if not content_match:
                        notes.append("content_miss")
                    result.notes = " ".join(notes)

                    status = "PASS" if result.correct else "FAIL"
                    print(f"      Turn {i}: {status}  {elapsed_ms:7.0f}ms  {result.notes}")

                except Exception as e:
                    result.error = str(e)[:200]
                    print(f"      Turn {i}: ERR  {str(e)[:80]}")

                suite.add(result)


def main():
    suite = EvalSuite(name="FreeAgent Multi-Turn")

    print("\n" + "="*60)
    print("  EVAL 7: FreeAgent Multi-Turn Tool Calling")
    print("="*60)

    check_ollama()

    print("\n-- FreeAgent Agent (single-shot per turn) --")
    run_freeagent_multi_turn(suite)

    suite.print_report()
    save_results(suite, "freeagent_multi_turn_results.json")


if __name__ == "__main__":
    main()
