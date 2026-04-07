"""
Eval 15: Auto-tune A/B verification — does auto_tune=True actually help?

Re-runs the SAME 4 multi-turn conversations from eval 13 (component A/B) with:
  1. auto_tune=True  (default — framework decides what to strip)
  2. auto_tune=False, bundled_skills=True, memory_tool=True (force everything on)
  3. (gemma4:e2b only) auto_tune=False, bundled_skills=False, memory_tool=False (manually stripped)

Success criterion: gemma4:e2b with auto_tune=True should match or beat manual_strip.
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
    check_response_contains,
    check_ollama,
    save_results,
)

# Same conversations as eval 13
CONVERSATIONS = [
    {
        "name": "weather_then_convert",
        "turns": [
            {"user": "What's the weather like in Tokyo right now?",
             "expected": ["85", "sunny"]},
            {"user": "Can you convert that temperature to Celsius?",
             "expected": ["29"]},
        ],
    },
    {
        "name": "compare_two_cities",
        "turns": [
            {"user": "What's the weather in New York?", "expected": ["72"]},
            {"user": "Now check London.", "expected": ["61"]},
            {"user": "Which city is warmer and by how much?",
             "expected": ["new york", "11"]},
        ],
    },
    {
        "name": "context_retention_no_tools",
        "turns": [
            {"user": "What's the weather in Paris?",
             "expected": ["68", "overcast"]},
            {"user": "Based on that weather, should I bring an umbrella?",
             "expected": ["yes"]},
        ],
    },
    {
        "name": "three_city_itinerary",
        "turns": [
            {"user": "I'm planning a trip. First, what's the weather in Tokyo?",
             "expected": ["tokyo"]},
            {"user": "What about Sydney?", "expected": ["sydney"]},
            {"user": "And Paris?", "expected": ["paris"]},
            {"user": "Rank these three cities from warmest to coldest.",
             "expected": ["tokyo"]},
        ],
    },
]


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
        """Convert temperature between Fahrenheit and Celsius."""
        try:
            value = float(value)
        except (TypeError, ValueError):
            return {"error": f"invalid value: {value}"}
        if from_unit.lower().startswith("f") and to_unit.lower().startswith("c"):
            return {"result": round((value - 32) * 5 / 9, 2)}
        if from_unit.lower().startswith("c") and to_unit.lower().startswith("f"):
            return {"result": round(value * 9 / 5 + 32, 2)}
        return {"error": f"unknown conversion: {from_unit} to {to_unit}"}

    return [weather, unit_converter]


def make_agent(model: str, variant: str):
    """Build an Agent with specific auto_tune/skills/memory settings."""
    from freeagent import Agent, SlidingWindow

    tools = make_tools()

    if variant == "auto_tune":
        return Agent(
            model=model,
            tools=tools,
            conversation=SlidingWindow(max_turns=10),
            auto_tune=True,
        )
    elif variant == "all_on":
        return Agent(
            model=model,
            tools=tools,
            conversation=SlidingWindow(max_turns=10),
            auto_tune=False,
            bundled_skills=True,
            memory_tool=True,
        )
    elif variant == "manual_strip":
        return Agent(
            model=model,
            tools=tools,
            conversation=SlidingWindow(max_turns=10),
            auto_tune=False,
            bundled_skills=False,
            memory_tool=False,
        )
    else:
        raise ValueError(f"Unknown variant: {variant}")


def run_conversation(agent, convo) -> tuple[bool, list[dict], float]:
    """Run a multi-turn conversation. Returns (all_passed, turn_log, total_latency_ms)."""
    turn_log = []
    all_passed = True
    total_latency = 0

    for i, turn in enumerate(convo["turns"]):
        start = time.monotonic()
        try:
            response = agent.run(turn["user"])
        except Exception as e:
            response = f"[error: {e}]"
            all_passed = False
        elapsed = (time.monotonic() - start) * 1000
        total_latency += elapsed

        passed = check_response_contains(response, turn["expected"])
        if not passed:
            all_passed = False

        last = agent.metrics.last_run
        turn_log.append({
            "turn": i + 1,
            "user": turn["user"],
            "response": response[:200],
            "passed": passed,
            "latency_ms": elapsed,
            "tool_calls": last.tool_call_count if last else 0,
            "validation_errors": last.validation_errors if last else 0,
        })

    if agent.conversation:
        agent.conversation.clear()

    return all_passed, turn_log, total_latency


def main():
    suite = EvalSuite(name="Auto-Tune A/B Verification (v0.3.1)")

    print("\n" + "=" * 70)
    print("  EVAL 15: Auto-Tune A/B Verification")
    print("=" * 70)

    check_ollama()

    # All models get auto_tune and all_on. gemma4:e2b also gets manual_strip.
    results = {}

    for model in MODELS:
        print(f"\n  Model: {model}")
        print(f"  {'─' * 60}")

        variants = ["auto_tune", "all_on"]
        if "gemma4" in model or "gemma3n" in model:
            variants.append("manual_strip")

        results[model] = {}

        for variant in variants:
            print(f"\n    Variant: {variant}")
            agent = make_agent(model, variant)

            # Diagnostic
            n_tools = len(agent.tools)
            n_skills = len(agent.skills)
            is_small = agent.model_info.is_small if agent.model_info else "N/A"
            print(f"      tools={n_tools} skills={n_skills} is_small={is_small}")

            results[model][variant] = {}

            for convo in CONVERSATIONS:
                passed, turn_log, latency = run_conversation(agent, convo)
                turns_passed = sum(1 for t in turn_log if t["passed"])
                turns_total = len(turn_log)
                pct = 100 * turns_passed / turns_total if turns_total else 0
                status = "PASS" if passed else "FAIL"
                print(f"      {convo['name']:30s} {status} {turns_passed}/{turns_total} ({pct:.0f}%)  {latency:.0f}ms")

                results[model][variant][convo["name"]] = {
                    "passed": passed,
                    "turns_passed": turns_passed,
                    "turns_total": turns_total,
                    "latency_ms": latency,
                    "turn_log": turn_log,
                }

                ev = EvalResult(
                    name=f"{convo['name']}_{variant}",
                    framework="freeagent_autotune",
                    model=model,
                    prompt=convo["turns"][0]["user"],
                    success=True,
                    correct=passed,
                    latency_ms=latency,
                    notes=f"variant={variant} turns={turns_passed}/{turns_total}",
                )
                suite.add(ev)

    # Summary table
    print("\n" + "=" * 70)
    print("  AUTO-TUNE A/B SUMMARY")
    print("=" * 70)

    all_variants = ["auto_tune", "all_on", "manual_strip"]
    print(f"\n  {'Model':22s} {'auto_tune':14s} {'all_on':14s} {'manual_strip':14s} {'Delta':10s}")
    print(f"  {'-' * 80}")

    for model in MODELS:
        cells = []
        pcts = {}
        for v in all_variants:
            if v in results[model]:
                total_passed = sum(r["turns_passed"] for r in results[model][v].values())
                total_turns = sum(r["turns_total"] for r in results[model][v].values())
                pct = 100 * total_passed / total_turns if total_turns else 0
                pcts[v] = pct
                cells.append(f"{total_passed}/{total_turns} ({pct:3.0f}%)")
            else:
                cells.append("—")
                pcts[v] = None

        # Delta: auto_tune vs all_on
        if pcts.get("auto_tune") is not None and pcts.get("all_on") is not None:
            delta = pcts["auto_tune"] - pcts["all_on"]
            delta_str = f"{delta:+.0f}%"
        else:
            delta_str = "—"

        print(f"  {model:22s} " + "  ".join(f"{c:13s}" for c in cells) + f"  {delta_str}")

    # gemma4:e2b specific verdict
    if "gemma4:e2b" in results and "manual_strip" in results["gemma4:e2b"]:
        auto_pct = sum(r["turns_passed"] for r in results["gemma4:e2b"]["auto_tune"].values()) / \
                   sum(r["turns_total"] for r in results["gemma4:e2b"]["auto_tune"].values()) * 100
        strip_pct = sum(r["turns_passed"] for r in results["gemma4:e2b"]["manual_strip"].values()) / \
                    sum(r["turns_total"] for r in results["gemma4:e2b"]["manual_strip"].values()) * 100
        all_on_pct = sum(r["turns_passed"] for r in results["gemma4:e2b"]["all_on"].values()) / \
                     sum(r["turns_total"] for r in results["gemma4:e2b"]["all_on"].values()) * 100

        print(f"\n  gemma4:e2b VERDICT:")
        print(f"    auto_tune={auto_pct:.0f}%  all_on={all_on_pct:.0f}%  manual_strip={strip_pct:.0f}%")
        if auto_pct >= strip_pct:
            print(f"    ✓ auto_tune matches or beats manual_strip — FIX VERIFIED")
        else:
            print(f"    ✗ auto_tune ({auto_pct:.0f}%) < manual_strip ({strip_pct:.0f}%) — POSSIBLE BUG")

    print("\n" + "=" * 70)

    # Save
    out_path = Path(__file__).parent / "autotune_ab_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"  Results saved to {out_path}")

    save_results(suite, "autotune_ab_freeagent_results.json")


if __name__ == "__main__":
    main()
