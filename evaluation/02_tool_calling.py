"""
Baseline Evaluation 2: Tool Calling — Ollama API vs Strands Agents

Tests native tool calling with local Python tools. Measures:
- Tool call success rate (did the model produce valid tool calls)
- Argument accuracy
- Multi-tool orchestration
- Latency & TPS

Tests across: qwen3:8b, qwen3:4b, llama3.1:latest
"""

import json
import time
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from eval_utils import (
    EvalResult, EvalSuite, MODELS, OLLAMA_BASE_URL,
    OLLAMA_TOOL_SPECS, TOOL_FNS,
    ollama_tool_loop, check_response_contains,
    check_ollama, save_results, make_strands_tools,
    extract_strands_metrics, format_strands_metrics,
)

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
        "expected_in_response": ["37"],  # 37.78 — "37" is substring of "37.78"
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


def run_ollama_raw(suite: EvalSuite):
    """Evaluate raw Ollama API tool calling."""
    for model in MODELS:
        print(f"\n  Raw Ollama API / {model}")
        for case in CASES:
            messages = [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": case["prompt"]},
            ]

            result = EvalResult(
                name=case["name"], framework="ollama_raw",
                model=model, prompt=case["prompt"],
                tool_calls_expected=len(case["expected_tools"]),
            )

            try:
                r = ollama_tool_loop(model, messages, OLLAMA_TOOL_SPECS, TOOL_FNS)

                result.response = r["response"]
                result.success = True
                result.latency_ms = r["latency_ms"]
                result.tokens_generated = r["tokens"]
                result.tokens_per_second = r["tps"]
                result.tool_calls_made = len(r["tool_calls"])

                actual_tool_names = [tc["name"] for tc in r["tool_calls"]]
                tools_match = sorted(actual_tool_names) == sorted(case["expected_tools"])
                content_match = check_response_contains(
                    r["response"] + json.dumps(r["tool_calls"]),
                    case["expected_in_response"],
                )
                result.correct = tools_match and content_match

                tool_status = "tools_ok" if tools_match else f"tools_wrong({actual_tool_names})"
                status = "PASS" if result.correct else "FAIL"
                print(f"    {status} {case['name']:25s} [{case['complexity']:7s}] {r['latency_ms']:7.0f}ms  {r['tps']:5.1f} t/s  calls:{len(r['tool_calls'])}  {tool_status}")
            except Exception as e:
                result.error = str(e)[:200]
                print(f"    ERR  {case['name']:25s} {str(e)[:80]}")

            suite.add(result)


def run_strands(suite: EvalSuite):
    """Evaluate Strands Agents tool calling."""
    from strands import Agent
    from strands.models.ollama import OllamaModel

    strands_tools = make_strands_tools()

    for model in MODELS:
        print(f"\n  Strands Agents / {model}")

        for case in CASES:
            # Fresh agent per case — no conversation bleed
            ollama_model = OllamaModel(
                host=OLLAMA_BASE_URL,
                model_id=model,
                temperature=0.1,
            )
            agent = Agent(
                model=ollama_model,
                system_prompt=SYSTEM,
                tools=strands_tools,
            )

            result = EvalResult(
                name=case["name"], framework="strands",
                model=model, prompt=case["prompt"],
                tool_calls_expected=len(case["expected_tools"]),
            )

            try:
                start = time.monotonic()
                response = agent(case["prompt"])
                elapsed_ms = (time.monotonic() - start) * 1000

                content = str(response)
                result.response = content
                result.success = True
                result.latency_ms = elapsed_ms

                sm = extract_strands_metrics(agent)
                result.tool_calls_made = sm["total_tool_calls"]
                result.tokens_generated = sm["total_tokens"]

                # Check tools match + content match (same criteria as raw Ollama)
                actual_tool_names = sm["tools_called"]
                tools_match = sorted(actual_tool_names) == sorted(case["expected_tools"])
                content_match = check_response_contains(content, case["expected_in_response"])
                result.correct = tools_match and content_match

                tool_status = "tools_ok" if tools_match else f"tools_wrong({actual_tool_names})"
                result.notes = f"cycles:{sm['cycles']} tokens:{sm['total_tokens']} {tool_status}"

                status = "PASS" if result.correct else "FAIL"
                print(f"    {status} {case['name']:25s} [{case['complexity']:7s}] {elapsed_ms:7.0f}ms  {format_strands_metrics(sm)}  {tool_status}")
            except Exception as e:
                result.error = str(e)[:200]
                print(f"    ERR  {case['name']:25s} {str(e)[:80]}")

            suite.add(result)


def main():
    suite = EvalSuite(name="Tool Calling Baseline")

    print("\n" + "="*60)
    print("  EVAL 2: Tool Calling — Raw Ollama vs Strands")
    print("="*60)

    check_ollama()

    print("\n-- Raw Ollama API (with tool loop) --")
    run_ollama_raw(suite)

    print("\n-- Strands Agents --")
    run_strands(suite)

    suite.print_report()
    save_results(suite, "tool_calling_results.json")


if __name__ == "__main__":
    main()
