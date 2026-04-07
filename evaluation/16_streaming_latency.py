"""
Eval 16: Streaming latency benchmark — time-to-first-token across models.

For each model:
  - No-tools streaming: stream a simple chat prompt, measure TTFT
  - Tool-using streaming: calculator tool, measure TTFT after tool result
  - Non-streaming baseline: same prompts with agent.run(), measure total time

Each case runs 3 times, report median.
"""

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from eval_utils import MODELS, check_ollama

CHAT_PROMPT = "Write a haiku about autumn."
TOOL_PROMPT = "What is 47 + 23? Walk me through it step by step."

RUNS_PER_CASE = 3


def make_calculator():
    from freeagent import tool as tool_decorator

    @tool_decorator(name="calculator")
    def calculator(expression: str) -> dict:
        """Evaluate a math expression. Supports basic arithmetic (+, -, *, /, parentheses)."""
        try:
            allowed = set("0123456789+-*/.() ")
            if not all(c in allowed for c in expression):
                return {"error": f"Invalid characters: {expression}"}
            result = eval(expression)  # noqa: S307
            return {"expression": expression, "result": result}
        except Exception as e:
            return {"error": str(e)}

    return calculator


def measure_streaming(model: str, prompt: str, tools=None):
    """Measure TTFT and total time for a streaming run. Returns (ttft_ms, total_ms, response)."""
    from freeagent import Agent
    from freeagent.events import TokenEvent

    agent = Agent(
        model=model,
        tools=tools or [],
        conversation=None,
        auto_tune=True,
    )

    start = time.monotonic()
    ttft = None
    response_text = ""

    for event in agent.run_stream(prompt):
        if isinstance(event, TokenEvent):
            if ttft is None:
                ttft = (time.monotonic() - start) * 1000
            response_text += event.text

    total_ms = (time.monotonic() - start) * 1000
    if ttft is None:
        ttft = total_ms  # no tokens streamed — TTFT = total

    return ttft, total_ms, response_text


def measure_nonstreaming(model: str, prompt: str, tools=None):
    """Measure total time for a non-streaming run. Returns (total_ms, response)."""
    from freeagent import Agent

    agent = Agent(
        model=model,
        tools=tools or [],
        conversation=None,
        auto_tune=True,
    )

    start = time.monotonic()
    response = agent.run(prompt)
    total_ms = (time.monotonic() - start) * 1000
    return total_ms, response


def median(values):
    return statistics.median(values) if values else 0


def main():
    print("\n" + "=" * 70)
    print("  EVAL 16: Streaming Latency Benchmark")
    print("=" * 70)

    check_ollama()

    calc = make_calculator()
    results = {}

    for model in MODELS:
        print(f"\n  Model: {model}")
        print(f"  {'─' * 60}")

        model_results = {
            "chat_streaming": {"ttft_ms": [], "total_ms": []},
            "tool_streaming": {"ttft_ms": [], "total_ms": []},
            "chat_nonstreaming": {"total_ms": []},
            "tool_nonstreaming": {"total_ms": []},
        }

        # Chat streaming
        for i in range(RUNS_PER_CASE):
            try:
                ttft, total, resp = measure_streaming(model, CHAT_PROMPT)
                model_results["chat_streaming"]["ttft_ms"].append(ttft)
                model_results["chat_streaming"]["total_ms"].append(total)
                print(f"    chat_stream  run {i+1}: TTFT={ttft:.0f}ms total={total:.0f}ms")
            except Exception as e:
                print(f"    chat_stream  run {i+1}: ERROR {e}")

        # Tool streaming
        for i in range(RUNS_PER_CASE):
            try:
                ttft, total, resp = measure_streaming(model, TOOL_PROMPT, tools=[calc])
                model_results["tool_streaming"]["ttft_ms"].append(ttft)
                model_results["tool_streaming"]["total_ms"].append(total)
                print(f"    tool_stream  run {i+1}: TTFT={ttft:.0f}ms total={total:.0f}ms")
            except Exception as e:
                print(f"    tool_stream  run {i+1}: ERROR {e}")

        # Chat non-streaming
        for i in range(RUNS_PER_CASE):
            try:
                total, resp = measure_nonstreaming(model, CHAT_PROMPT)
                model_results["chat_nonstreaming"]["total_ms"].append(total)
                print(f"    chat_nostre  run {i+1}: total={total:.0f}ms")
            except Exception as e:
                print(f"    chat_nostre  run {i+1}: ERROR {e}")

        # Tool non-streaming
        for i in range(RUNS_PER_CASE):
            try:
                total, resp = measure_nonstreaming(model, TOOL_PROMPT, tools=[calc])
                model_results["tool_nonstreaming"]["total_ms"].append(total)
                print(f"    tool_nostre  run {i+1}: total={total:.0f}ms")
            except Exception as e:
                print(f"    tool_nostre  run {i+1}: ERROR {e}")

        # Compute medians
        results[model] = {
            "chat_stream_ttft_ms": round(median(model_results["chat_streaming"]["ttft_ms"])),
            "chat_stream_total_ms": round(median(model_results["chat_streaming"]["total_ms"])),
            "tool_stream_ttft_ms": round(median(model_results["tool_streaming"]["ttft_ms"])),
            "tool_stream_total_ms": round(median(model_results["tool_streaming"]["total_ms"])),
            "chat_nonstream_total_ms": round(median(model_results["chat_nonstreaming"]["total_ms"])),
            "tool_nonstream_total_ms": round(median(model_results["tool_nonstreaming"]["total_ms"])),
            "raw": {k: {kk: [round(v) for v in vv] for kk, vv in v.items()} for k, v in model_results.items()},
        }

    # Summary table
    print("\n" + "=" * 70)
    print("  STREAMING LATENCY SUMMARY (median of 3 runs)")
    print("=" * 70)

    print(f"\n  {'Model':22s} {'Chat TTFT':>10s} {'Chat Total':>11s} {'Tool TTFT':>10s} {'Tool Total':>11s} {'NoStr Chat':>11s} {'NoStr Tool':>11s}")
    print(f"  {'-' * 90}")
    for model in MODELS:
        r = results[model]
        print(f"  {model:22s} {r['chat_stream_ttft_ms']:>8d}ms {r['chat_stream_total_ms']:>9d}ms "
              f"{r['tool_stream_ttft_ms']:>8d}ms {r['tool_stream_total_ms']:>9d}ms "
              f"{r['chat_nonstream_total_ms']:>9d}ms {r['tool_nonstream_total_ms']:>9d}ms")

    # TTFT advantage
    print(f"\n  TTFT vs Non-Streaming Total (chat):")
    for model in MODELS:
        r = results[model]
        if r['chat_nonstream_total_ms'] > 0:
            speedup = r['chat_nonstream_total_ms'] / r['chat_stream_ttft_ms'] if r['chat_stream_ttft_ms'] > 0 else 0
            print(f"    {model:22s} TTFT={r['chat_stream_ttft_ms']}ms vs Total={r['chat_nonstream_total_ms']}ms  ({speedup:.1f}x faster first token)")

    print("\n" + "=" * 70)

    # Save
    out_path = Path(__file__).parent / "streaming_latency_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"  Results saved to {out_path}")


if __name__ == "__main__":
    main()
