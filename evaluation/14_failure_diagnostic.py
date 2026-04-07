"""
Eval 14: Failure diagnostic — why does FreeAgent lose to raw Ollama on these cases?

Reads existing FreeAgent results and identifies cases where:
- Raw Ollama passed
- FreeAgent failed (default config)

For each such case, runs both raw Ollama and FreeAgent again with FULL trace logging:
- Exact system prompt sent (to see what skills/memory injected)
- Full message list per iteration
- Tool calls made (and any that were extra/wrong)
- Hooks fired
- Telemetry record

Outputs structured diagnostic data to figure out the root cause:
- Skills text confused the model?
- Memory tool spec made the model tool-happy?
- Conversation history accumulated bad context?
- Validator interfered when no validation was needed?
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from eval_utils import (
    EvalResult,
    EvalSuite,
    MODELS,
    OLLAMA_BASE_URL,
    ollama_chat,
    check_response_contains,
    check_ollama,
    save_results,
)


# Cases where FreeAgent loses to raw Ollama (from earlier comparison)
KNOWN_FAILURES = [
    {
        "model": "qwen3:8b",
        "case": "compare_two_cities_turn2",
        "convo": "compare_two_cities",
        "turn_index": 1,
    },
    {
        "model": "llama3.1:latest",
        "case": "compare_two_cities_turn3",
        "convo": "compare_two_cities",
        "turn_index": 2,
    },
    {
        "model": "llama3.1:latest",
        "case": "context_retention_no_tools_turn2",
        "convo": "context_retention_no_tools",
        "turn_index": 1,
    },
    {
        "model": "llama3.1:latest",
        "case": "three_city_itinerary_turn4",
        "convo": "three_city_itinerary",
        "turn_index": 3,
    },
    {
        "model": "qwen3:4b",
        "case": "chained_conversion_and_calc_turn1",
        "convo": "chained_conversion_and_calc",
        "turn_index": 0,
    },
]


CONVERSATIONS = {
    "compare_two_cities": {
        "turns": [
            {"user": "What's the weather in New York?", "expected": ["72"]},
            {"user": "Now check London.", "expected": ["61"]},
            {"user": "Which city is warmer and by how much?",
             "expected": ["new york", "11"]},
        ],
    },
    "context_retention_no_tools": {
        "turns": [
            {"user": "What's the weather in Paris?", "expected": ["68", "overcast"]},
            {"user": "Based on that weather, should I bring an umbrella?",
             "expected": ["yes"]},
        ],
    },
    "three_city_itinerary": {
        "turns": [
            {"user": "I'm planning a trip. First, what's the weather in Tokyo?",
             "expected": ["tokyo"]},
            {"user": "What about Sydney?", "expected": ["sydney"]},
            {"user": "And Paris?", "expected": ["paris"]},
            {"user": "Rank these three cities from warmest to coldest.",
             "expected": ["tokyo"]},
        ],
    },
    "chained_conversion_and_calc": {
        "turns": [
            {"user": "Convert 10 miles to kilometers.", "expected": ["16.09"]},
            {"user": "If I run that distance in 1.5 hours, what's my speed in km/h? Use the calculator.",
             "expected": ["10.7"]},
        ],
    },
}


def make_tools():
    from freeagent import tool as tool_decorator

    WEATHER = {
        "tokyo": {"temp_f": 85, "condition": "sunny"},
        "london": {"temp_f": 61, "condition": "rainy"},
        "new york": {"temp_f": 72, "condition": "partly cloudy"},
        "paris": {"temp_f": 68, "condition": "overcast"},
        "sydney": {"temp_f": 58, "condition": "clear"},
    }

    @tool_decorator(name="weather")
    def weather(city: str) -> dict:
        """Get current weather for a city."""
        key = city.lower().strip()
        for k, v in WEATHER.items():
            if k in key:
                return {**v, "city": city}
        return {"city": city, "temp_f": 70, "condition": "unknown"}

    @tool_decorator(name="unit_converter")
    def unit_converter(value: float, from_unit: str, to_unit: str) -> dict:
        """Convert between units."""
        try:
            value = float(value)
        except (TypeError, ValueError):
            return {"error": f"invalid: {value}"}
        if from_unit.lower().startswith("mi"):
            return {"result": round(value * 1.60934, 2)}
        if from_unit.lower().startswith("km"):
            return {"result": round(value / 1.60934, 2)}
        if from_unit.lower().startswith("f"):
            return {"result": round((value - 32) * 5 / 9, 2)}
        if from_unit.lower().startswith("c"):
            return {"result": round(value * 9 / 5 + 32, 2)}
        return {"error": "unknown conversion"}

    @tool_decorator(name="calculator")
    def calculator(expression: str) -> dict:
        """Evaluate a math expression."""
        try:
            return {"result": eval(expression)}  # noqa
        except Exception as e:
            return {"error": str(e)}

    return [weather, unit_converter, calculator]


def diagnose_failure(failure):
    """Run a failed case with full trace capture."""
    from freeagent import Agent, SlidingWindow

    model = failure["model"]
    convo = CONVERSATIONS[failure["convo"]]
    fail_turn = failure["turn_index"]

    print(f"\n{'─' * 70}")
    print(f"  Diagnosing: {failure['case']} on {model}")
    print(f"{'─' * 70}")

    agent = Agent(
        model=model,
        tools=make_tools(),
        conversation=SlidingWindow(max_turns=10),
    )

    # Capture system prompt that will be sent
    system_prompt = agent._build_system_prompt()
    print(f"\n  System prompt ({len(system_prompt)} chars, ~{len(system_prompt)//4} tokens):")
    print(f"  {'-' * 60}")
    for line in system_prompt.split("\n")[:30]:
        print(f"    {line}")
    if system_prompt.count("\n") > 30:
        print(f"    ... ({system_prompt.count(chr(10))} lines total)")

    # Tool count and names
    tool_names = [t.name for t in agent.tools]
    print(f"\n  Tools available: {tool_names}")
    print(f"  Skills loaded: {[s.name for s in agent.skills]}")

    # Run all turns up to and including the failing one
    diagnostic_log = []
    for i, turn in enumerate(convo["turns"]):
        if i > fail_turn:
            break
        print(f"\n  Turn {i + 1}: {turn['user']}")
        start = time.monotonic()
        response = agent.run(turn["user"])
        elapsed = (time.monotonic() - start) * 1000
        last = agent.metrics.last_run

        passed = check_response_contains(response, turn["expected"])
        status = "PASS" if passed else "FAIL"
        print(f"    Response: {response[:200]}")
        print(f"    {status}  {elapsed:.0f}ms  iters={last.iterations}  tools={last.tools_used}")
        if last.validation_errors or last.retries:
            print(f"    Guardrails: val_err={last.validation_errors} retries={last.retries}")

        diagnostic_log.append({
            "turn": i + 1,
            "user": turn["user"],
            "response": response,
            "passed": passed,
            "expected": turn["expected"],
            "iterations": last.iterations,
            "tools_used": last.tools_used,
            "tool_calls": last.tool_call_count,
            "validation_errors": last.validation_errors,
            "retries": last.retries,
            "loop_detected": last.loop_detected,
            "latency_ms": elapsed,
        })

    return {
        "failure": failure,
        "system_prompt": system_prompt,
        "system_prompt_chars": len(system_prompt),
        "system_prompt_tokens_est": len(system_prompt) // 4,
        "tool_count": len(agent.tools),
        "tool_names": tool_names,
        "skill_names": [s.name for s in agent.skills],
        "turns": diagnostic_log,
    }


def main():
    print("\n" + "=" * 70)
    print("  EVAL 14: Failure Diagnostic")
    print("=" * 70)

    check_ollama()

    diagnostics = []
    for failure in KNOWN_FAILURES:
        try:
            diag = diagnose_failure(failure)
            diagnostics.append(diag)
        except Exception as e:
            print(f"  ERROR diagnosing {failure['case']}: {e}")

    out_path = Path(__file__).parent / "failure_diagnostic_results.json"
    with open(out_path, "w") as f:
        json.dump(diagnostics, f, indent=2, default=str)

    print(f"\n  Diagnostic data saved to {out_path}")

    # Quick summary
    print("\n" + "=" * 70)
    print("  DIAGNOSTIC SUMMARY")
    print("=" * 70)
    for diag in diagnostics:
        f = diag["failure"]
        last_turn = diag["turns"][-1] if diag["turns"] else None
        if last_turn:
            print(f"\n  {f['case']:35s} {f['model']:20s}")
            print(f"    System prompt: ~{diag['system_prompt_tokens_est']} tokens")
            print(f"    Tools: {diag['tool_count']}, Skills: {len(diag['skill_names'])}")
            print(f"    Final turn passed: {last_turn['passed']}")
            print(f"    Tools used at final turn: {last_turn['tools_used']}")
            print(f"    Iterations: {last_turn['iterations']}")
            if last_turn['validation_errors'] or last_turn['retries']:
                print(f"    Guardrails fired: val_err={last_turn['validation_errors']} retries={last_turn['retries']}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
