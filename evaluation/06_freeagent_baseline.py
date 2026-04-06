"""
FreeAgent Evaluation 6: Tool Calling Baseline

Same test cases as eval 02, but using FreeAgent Agent instead of raw Ollama API.
This is the core thesis test: does FreeAgent's guardrails improve tool calling?

Metrics captured:
- Accuracy (correct tool + correct answer)
- Latency
- Validation errors, retries, circuit breaker triggers
- Failure modes (WHY something fails)
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

# Import FreeAgent
sys.path.insert(0, str(Path(__file__).parent.parent))
from freeagent import Agent, tool as freeagent_tool

# ── FreeAgent-wrapped versions of eval tools ──

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

CASES = [
    {
        "name": "single_weather",
        "prompt": "What's the weather in Tokyo?",
        "expected_tools": ["weather"],
        "expected_in_response": ["tokyo", "sunny"],
        "complexity": "simple",
    },
    {
        "name": "single_calc",
        "prompt": "What is 347 * 29?",
        "expected_tools": ["calculator"],
        "expected_in_response": ["10063"],
        "complexity": "simple",
    },
    {
        "name": "single_convert",
        "prompt": "Convert 100 fahrenheit to celsius.",
        "expected_tools": ["unit_converter"],
        "expected_in_response": ["37"],
        "complexity": "simple",
    },
    {
        "name": "tool_selection",
        "prompt": "I'm going to London. What should I pack? Check the weather first.",
        "expected_tools": ["weather"],
        "expected_in_response": ["london"],
        "complexity": "medium",
    },
    {
        "name": "multi_step_convert",
        "prompt": "The temperature in Paris is in Fahrenheit. Get the weather in Paris, then convert the temperature to Celsius.",
        "expected_tools": ["weather", "unit_converter"],
        "expected_in_response": ["paris", "20"],
        "complexity": "complex",
    },
    {
        "name": "multi_tool_compare",
        "prompt": "Compare the weather in New York and Tokyo. Which city is warmer?",
        "expected_tools": ["weather", "weather"],
        "expected_in_response": ["tokyo", "warmer"],
        "complexity": "complex",
    },
    {
        "name": "tool_plus_calc",
        "prompt": "What is the temperature difference between New York (72F) and London (61F)? Use the calculator.",
        "expected_tools": ["calculator"],
        "expected_in_response": ["11"],
        "complexity": "medium",
    },
    {
        "name": "chained_reasoning",
        "prompt": "Convert 5 miles to km, then calculate how many minutes it takes to walk that distance at 5 km/h.",
        "expected_tools": ["unit_converter", "calculator"],
        "expected_in_response": ["8.05"],
        "complexity": "complex",
    },
]

SYSTEM = "You are a helpful assistant. Use the provided tools when needed. Be concise in your final answer."


def run_freeagent(suite: EvalSuite):
    """Evaluate FreeAgent Agent tool calling."""
    for model in MODELS:
        print(f"\n  FreeAgent / {model}")

        for case in CASES:
            # Fresh agent per case — no conversation bleed
            agent = Agent(
                model=model,
                system_prompt=SYSTEM,
                tools=TOOLS,
            )

            result = EvalResult(
                name=case["name"], framework="freeagent",
                model=model, prompt=case["prompt"],
                tool_calls_expected=len(case["expected_tools"]),
            )

            try:
                start = time.monotonic()
                response = agent.run(case["prompt"])
                elapsed_ms = (time.monotonic() - start) * 1000

                result.response = response or ""
                result.success = True
                result.latency_ms = elapsed_ms

                # Extract metrics from agent.metrics
                run = agent.metrics.runs[-1] if agent.metrics.runs else None
                if run:
                    result.tool_calls_made = run.tool_call_count
                    actual_tool_names = run.tools_used
                    val_errors = run.validation_errors
                    retries = run.retries
                    loop = run.loop_detected
                    max_iter = run.max_iter_hit
                else:
                    actual_tool_names = []
                    val_errors = retries = 0
                    loop = max_iter = False

                # Check correctness (same criteria as eval 02)
                # Filter out "memory" from tool calls for comparison
                eval_tools = [t for t in actual_tool_names if t != "memory"]
                tools_match = sorted(eval_tools) == sorted(case["expected_tools"])
                content_match = check_response_contains(
                    result.response, case["expected_in_response"],
                )
                result.correct = tools_match and content_match

                # Build notes with failure modes
                notes_parts = []
                if val_errors:
                    notes_parts.append(f"val_errors:{val_errors}")
                if retries:
                    notes_parts.append(f"retries:{retries}")
                if loop:
                    notes_parts.append("LOOP_DETECTED")
                if max_iter:
                    notes_parts.append("MAX_ITER")
                if not tools_match:
                    notes_parts.append(f"tools_wrong({eval_tools})")
                if not content_match:
                    notes_parts.append(f"content_miss")
                result.notes = " ".join(notes_parts)

                tool_status = "tools_ok" if tools_match else f"tools_wrong({eval_tools})"
                status = "PASS" if result.correct else "FAIL"
                print(f"    {status} {case['name']:25s} [{case['complexity']:7s}] {elapsed_ms:7.0f}ms  calls:{result.tool_calls_made}  {tool_status}  {result.notes}")

            except Exception as e:
                result.error = str(e)[:200]
                print(f"    ERR  {case['name']:25s} {str(e)[:80]}")

            suite.add(result)


def main():
    suite = EvalSuite(name="FreeAgent Tool Calling Baseline")

    print("\n" + "="*60)
    print("  EVAL 6: FreeAgent Tool Calling Baseline")
    print("="*60)

    check_ollama()

    print("\n-- FreeAgent Agent --")
    run_freeagent(suite)

    suite.print_report()
    save_results(suite, "freeagent_tool_calling_results.json")


if __name__ == "__main__":
    main()
