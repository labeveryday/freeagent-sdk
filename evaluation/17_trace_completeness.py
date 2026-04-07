"""
Eval 17: Trace completeness verification — do all expected trace events fire?

5 scenarios against qwen3:4b:
  1. Simple chat (no tools) — run_start, model_call_start, model_call_end, run_end
  2. Single tool call — tool_call, tool_result events
  3. Validation error — validation_error event (if triggered)
  4. Loop trap — max_iterations or loop event
  5. Multi-turn with memory — each run has its own complete trace
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from eval_utils import check_ollama

MODEL = "qwen3:4b"


def get_trace_event_types(agent):
    """Extract event type names from the last run's trace."""
    last = agent.metrics.last_run
    if not last or not hasattr(last, 'trace_events'):
        return []
    return [e.event_type for e in last.trace_events]


def scenario_simple_chat():
    """Scenario 1: Simple chat, no tools."""
    from freeagent import Agent

    print("\n    Scenario 1: Simple chat (no tools)")
    agent = Agent(model=MODEL, conversation=None, auto_tune=True)
    agent.run("Say hello in exactly three words.")

    events = get_trace_event_types(agent)
    expected = {"run_start", "model_call_start", "model_call_end", "run_end"}
    found = expected.intersection(events)
    missing = expected - set(events)

    status = "PASS" if not missing else "FAIL"
    print(f"      {status}: found {sorted(found)}, missing {sorted(missing)}")
    print(f"      All events: {events}")

    return {
        "name": "simple_chat",
        "expected": sorted(expected),
        "found": sorted(found),
        "missing": sorted(missing),
        "all_events": events,
        "passed": len(missing) == 0,
    }


def scenario_tool_call():
    """Scenario 2: Single tool call."""
    from freeagent import Agent, tool as tool_decorator

    print("\n    Scenario 2: Single tool call")

    @tool_decorator(name="calculator")
    def calculator(expression: str) -> dict:
        """Evaluate a math expression."""
        try:
            return {"result": eval(expression)}  # noqa: S307
        except Exception as e:
            return {"error": str(e)}

    agent = Agent(model=MODEL, tools=[calculator], conversation=None, auto_tune=True)
    agent.run("What is 15 * 3?")

    events = get_trace_event_types(agent)
    expected = {"run_start", "model_call_start", "model_call_end", "run_end", "tool_call", "tool_result"}
    found = expected.intersection(events)
    missing = expected - set(events)

    status = "PASS" if not missing else "FAIL"
    print(f"      {status}: found {sorted(found)}, missing {sorted(missing)}")
    print(f"      All events: {events}")

    return {
        "name": "tool_call",
        "expected": sorted(expected),
        "found": sorted(found),
        "missing": sorted(missing),
        "all_events": events,
        "passed": len(missing) == 0,
    }


def scenario_validation_error():
    """Scenario 3: Try to trigger a validation error."""
    from freeagent import Agent, tool as tool_decorator

    print("\n    Scenario 3: Validation error")

    @tool_decorator(name="lookup_city_info")
    def lookup_city_info(city: str, include_weather: bool = False) -> dict:
        """Look up detailed information about a city. City name is required."""
        return {"city": city, "population": 1000000, "weather": "sunny" if include_weather else None}

    agent = Agent(model=MODEL, tools=[lookup_city_info], conversation=None, auto_tune=True)
    # Ask in a way that might confuse the model about args
    agent.run("Tell me about a city. Use the lookup tool.")

    events = get_trace_event_types(agent)
    # We hope for validation_error but it may not fire — that's useful data too
    has_validation = "validation_error" in events
    # At minimum we need the core events
    core_expected = {"run_start", "model_call_start", "model_call_end", "run_end"}
    core_found = core_expected.intersection(events)
    core_missing = core_expected - set(events)

    status = "PASS" if not core_missing else "FAIL"
    print(f"      {status}: core events OK={len(core_missing)==0}, validation_error fired={has_validation}")
    print(f"      All events: {events}")

    return {
        "name": "validation_error",
        "expected_core": sorted(core_expected),
        "found_core": sorted(core_found),
        "missing_core": sorted(core_missing),
        "validation_error_fired": has_validation,
        "all_events": events,
        "passed": len(core_missing) == 0,  # Pass if core events present
        "note": "validation_error is best-effort — models may produce valid calls",
    }


def scenario_loop_trap():
    """Scenario 4: Tool that always errors, forcing retries until max_iterations."""
    from freeagent import Agent, tool as tool_decorator

    print("\n    Scenario 4: Loop trap (max_iterations)")

    @tool_decorator(name="flaky_api")
    def flaky_api(query: str) -> dict:
        """Query an external API. Always returns an error asking to retry."""
        return {"error": "Service temporarily unavailable. Please retry."}

    agent = Agent(
        model=MODEL,
        tools=[flaky_api],
        conversation=None,
        auto_tune=True,
        max_iterations=4,
    )
    agent.run("Use the flaky_api tool to look up 'test data'. Keep trying until it works.")

    events = get_trace_event_types(agent)
    core_expected = {"run_start", "run_end"}
    core_found = core_expected.intersection(events)
    core_missing = core_expected - set(events)

    # Count iterations (tool_call events)
    tool_call_count = events.count("tool_call")
    has_loop_or_max = "loop_detected" in events or "max_iterations" in events

    status = "PASS" if not core_missing else "FAIL"
    print(f"      {status}: core OK, tool_calls={tool_call_count}, loop/max_event={has_loop_or_max}")
    print(f"      All events: {events}")

    return {
        "name": "loop_trap",
        "expected_core": sorted(core_expected),
        "found_core": sorted(core_found),
        "missing_core": sorted(core_missing),
        "tool_call_count": tool_call_count,
        "loop_or_max_event": has_loop_or_max,
        "all_events": events,
        "passed": len(core_missing) == 0,
    }


def scenario_multi_turn():
    """Scenario 5: Two-turn conversation, verify each run has its own trace."""
    from freeagent import Agent, SlidingWindow

    print("\n    Scenario 5: Multi-turn traces")

    agent = Agent(
        model=MODEL,
        conversation=SlidingWindow(max_turns=10),
        auto_tune=True,
    )

    # Turn 1
    agent.run("My name is Alice.")
    run1_events = get_trace_event_types(agent)
    run1_count = len(agent.metrics.last_run.trace_events) if agent.metrics.last_run else 0

    # Turn 2
    agent.run("What's my name?")
    run2_events = get_trace_event_types(agent)
    run2_count = len(agent.metrics.last_run.trace_events) if agent.metrics.last_run else 0

    # Each run should have its own trace
    run1_has_core = {"run_start", "run_end"}.issubset(set(run1_events))
    run2_has_core = {"run_start", "run_end"}.issubset(set(run2_events))
    traces_independent = run1_count > 0 and run2_count > 0

    status = "PASS" if (run1_has_core and run2_has_core and traces_independent) else "FAIL"
    print(f"      {status}: run1={run1_count} events, run2={run2_count} events, both have core={run1_has_core and run2_has_core}")
    print(f"      Run 1 events: {run1_events}")
    print(f"      Run 2 events: {run2_events}")

    return {
        "name": "multi_turn",
        "run1_events": run1_events,
        "run1_count": run1_count,
        "run2_events": run2_events,
        "run2_count": run2_count,
        "run1_has_core": run1_has_core,
        "run2_has_core": run2_has_core,
        "traces_independent": traces_independent,
        "passed": run1_has_core and run2_has_core and traces_independent,
    }


def main():
    print("\n" + "=" * 70)
    print("  EVAL 17: Trace Completeness Verification")
    print(f"  Model: {MODEL}")
    print("=" * 70)

    check_ollama()

    scenarios = [
        scenario_simple_chat,
        scenario_tool_call,
        scenario_validation_error,
        scenario_loop_trap,
        scenario_multi_turn,
    ]

    results = []
    for fn in scenarios:
        try:
            result = fn()
            results.append(result)
        except Exception as e:
            print(f"    ERROR: {e}")
            results.append({
                "name": fn.__name__.replace("scenario_", ""),
                "passed": False,
                "error": str(e),
                "all_events": [],
            })

    # Summary
    print("\n" + "=" * 70)
    print("  TRACE COMPLETENESS SUMMARY")
    print("=" * 70)

    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    print(f"\n  {passed}/{total} scenarios passed\n")

    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"    {status}: {r['name']}")
        if not r["passed"] and r.get("missing"):
            print(f"           Missing: {r.get('missing', r.get('missing_core', []))}")
        if r.get("note"):
            print(f"           Note: {r['note']}")

    print("\n" + "=" * 70)

    # Save
    out_path = Path(__file__).parent / "trace_completeness_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"  Results saved to {out_path}")


if __name__ == "__main__":
    main()
