"""
Baseline Evaluation 4: Multi-Turn Tool Calling

Tests conversational tool use where each user message builds on prior context.
The agent must maintain state across turns and use previous tool results.

Measures:
- Context retention across turns
- Correct tool selection given prior results
- Accuracy of chained reasoning
- Total conversation latency & TPS

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
    ollama_chat, check_response_contains,
    check_ollama, save_results, make_strands_tools,
    extract_strands_metrics, format_strands_metrics,
)

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


def run_turn(model: str, messages: list[dict], max_iterations: int = 5):
    """
    Run one turn through Ollama with tool calling. Mutates messages in place.
    Returns (response_text, tool_calls_made, latency_ms, tokens, tps).
    """
    total_latency = 0
    total_tokens = 0
    total_eval_duration = 0
    tool_calls_made = []

    for _ in range(max_iterations):
        start = time.monotonic()
        resp = ollama_chat(model, messages, OLLAMA_TOOL_SPECS)
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

            fn = TOOL_FNS.get(fn_name)
            if fn:
                try:
                    result = fn(**fn_args)
                except Exception as e:
                    result = {"error": str(e)}
            else:
                result = {"error": f"Unknown tool: {fn_name}"}

            messages.append({"role": "tool", "content": json.dumps(result)})

    messages.append({"role": "assistant", "content": "[Max iterations]"})
    tps = (total_tokens / total_eval_duration * 1e9) if total_eval_duration > 0 else 0
    return "[Max iterations]", tool_calls_made, total_latency, total_tokens, tps


def run_ollama_raw(suite: EvalSuite):
    """Run multi-turn conversations with raw Ollama API."""
    for model in MODELS:
        print(f"\n  Raw Ollama API / {model}")

        for convo in CONVERSATIONS:
            print(f"\n    Conversation: {convo['name']}")
            messages = [{"role": "system", "content": SYSTEM}]
            all_passed = True

            for i, turn in enumerate(convo["turns"]):
                messages.append({"role": "user", "content": turn["user"]})

                ev = EvalResult(
                    name=f"{convo['name']}_turn{i+1}", framework="ollama_raw",
                    model=model, prompt=turn["user"],
                    tool_calls_expected=len(turn["expected_tools"]),
                )

                try:
                    response, tool_calls, latency, tokens, tps = run_turn(model, messages)

                    ev.response = response
                    ev.success = True
                    ev.latency_ms = latency
                    ev.tokens_generated = tokens
                    ev.tokens_per_second = tps
                    ev.tool_calls_made = len(tool_calls)

                    actual_tools = [tc["name"] for tc in tool_calls]
                    if turn["expected_tools"]:
                        tools_ok = sorted(actual_tools) == sorted(turn["expected_tools"])
                    else:
                        tools_ok = True

                    content_ok = check_response_contains(
                        response + " " + json.dumps(tool_calls),
                        turn["expected_in_response"],
                    )
                    ev.correct = tools_ok and content_ok

                    if not ev.correct:
                        all_passed = False

                    status = "PASS" if ev.correct else "FAIL"
                    tool_info = f"tools:{actual_tools}" if actual_tools else "no tools"
                    print(f"      Turn {i+1}: {status}  {latency:7.0f}ms  {tps:5.1f} t/s  {tool_info}")
                except Exception as e:
                    ev.error = str(e)[:200]
                    all_passed = False
                    print(f"      Turn {i+1}: ERR   {str(e)[:80]}")

                suite.add(ev)

            print(f"    -> {'PASS' if all_passed else 'FAIL'}")


def run_strands(suite: EvalSuite):
    """Run multi-turn conversations with Strands Agents."""
    from strands import Agent
    from strands.models.ollama import OllamaModel

    strands_tools = make_strands_tools()

    for model in MODELS:
        print(f"\n  Strands Agents / {model}")

        for convo in CONVERSATIONS:
            print(f"\n    Conversation: {convo['name']}")

            # Fresh agent per conversation (maintains state within the convo)
            ollama_model = OllamaModel(
                host=OLLAMA_BASE_URL, model_id=model, temperature=0.1,
            )
            agent = Agent(
                model=ollama_model, system_prompt=SYSTEM,
                tools=strands_tools,
            )

            all_passed = True

            for i, turn in enumerate(convo["turns"]):
                ev = EvalResult(
                    name=f"{convo['name']}_turn{i+1}", framework="strands",
                    model=model, prompt=turn["user"],
                    tool_calls_expected=len(turn["expected_tools"]),
                )

                try:
                    start = time.monotonic()
                    response = agent(turn["user"])
                    elapsed_ms = (time.monotonic() - start) * 1000

                    content = str(response)
                    ev.response = content
                    ev.success = True
                    ev.latency_ms = elapsed_ms

                    # Extract real metrics from Strands
                    sm = extract_strands_metrics(agent)
                    ev.tool_calls_made = sm["total_tool_calls"]
                    ev.tokens_generated = sm["total_tokens"]

                    # Check tools match + content (same as raw Ollama path)
                    actual_tools = sm["tools_called"]
                    if turn["expected_tools"]:
                        tools_ok = sorted(actual_tools) == sorted(turn["expected_tools"])
                    else:
                        tools_ok = True
                    content_ok = check_response_contains(content, turn["expected_in_response"])
                    ev.correct = tools_ok and content_ok
                    ev.notes = f"cycles:{sm['cycles']} tokens:{sm['total_tokens']} tools:{actual_tools}"

                    if not ev.correct:
                        all_passed = False

                    status = "PASS" if ev.correct else "FAIL"
                    print(f"      Turn {i+1}: {status}  {elapsed_ms:7.0f}ms  {format_strands_metrics(sm)}")
                except Exception as e:
                    ev.error = str(e)[:200]
                    all_passed = False
                    print(f"      Turn {i+1}: ERR   {str(e)[:80]}")

                suite.add(ev)

            print(f"    -> {'PASS' if all_passed else 'FAIL'}")


def main():
    suite = EvalSuite(name="Multi-Turn Tool Calling")

    print("\n" + "="*60)
    print("  EVAL 4: Multi-Turn Tool Calling")
    print("="*60)

    check_ollama()

    print("\n-- Raw Ollama API --")
    run_ollama_raw(suite)

    print("\n-- Strands Agents --")
    run_strands(suite)

    suite.print_report()
    save_results(suite, "multi_turn_results.json")


if __name__ == "__main__":
    main()
