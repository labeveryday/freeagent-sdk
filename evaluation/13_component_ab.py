"""
Eval 13: Component A/B test — what part of FreeAgent helps vs hurts?

Runs the SAME test cases against 4 FreeAgent variants:
1. default          — bundled skills + memory tool + conversation
2. no_skills        — bundled skills disabled
3. no_memory_tool   — memory tool removed
4. stripped         — no skills, no memory tool (just agent loop + validator + breaker)

Compare per-case accuracy across variants and against raw Ollama.
This tells us EXACTLY what's costing the 6% gap to raw Ollama.

Hypothesis: bundled skills (especially tool-user) push some models to make
unnecessary tool calls, hurting cases where the answer should come from context.
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
    check_response_contains,
    check_ollama,
    save_results,
)


# Use the same multi-turn cases as eval 04 / 11 for direct comparison
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
    """Build an Agent variant by stripping pieces post-init."""
    from freeagent import Agent, SlidingWindow
    from freeagent.validator import Validator

    tools = make_tools()
    agent = Agent(
        model=model,
        tools=tools,
        conversation=SlidingWindow(max_turns=10),
    )

    if variant in ("no_skills", "stripped"):
        agent.skills = []  # disable bundled skills

    if variant in ("no_memory_tool", "stripped"):
        # Strip memory tools from the tool list
        agent.tools = [t for t in agent.tools if not t.name.startswith("memory")]
        agent.validator = Validator(agent.tools)

    return agent


def run_conversation(agent, convo) -> tuple[bool, list[dict], float]:
    """Run a multi-turn conversation through the agent. Returns (all_passed, turn_log, total_latency_ms)."""
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
            "tools_used": last.tools_used if last else [],
            "validation_errors": last.validation_errors if last else 0,
            "retries": last.retries if last else 0,
        })

    if agent.conversation:
        agent.conversation.clear()

    return all_passed, turn_log, total_latency


def main():
    suite = EvalSuite(name="Component A/B — FreeAgent Variants")

    print("\n" + "=" * 70)
    print("  EVAL 13: Component A/B Test")
    print("=" * 70)

    check_ollama()

    variants = ["default", "no_skills", "no_memory_tool", "stripped"]
    results = {model: {v: {} for v in variants} for model in MODELS}

    for model in MODELS:
        print(f"\n  Model: {model}")
        print(f"  {'─' * 60}")

        for variant in variants:
            print(f"\n    Variant: {variant}")
            agent = make_agent(model, variant)

            # Diagnostic: how many tools, how many skills
            n_tools = len(agent.tools)
            n_skills = len(agent.skills)
            print(f"      tools={n_tools} skills={n_skills}")

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

                # Add to suite
                ev = EvalResult(
                    name=f"{convo['name']}_{variant}",
                    framework="freeagent_ab",
                    model=model,
                    prompt=convo["turns"][0]["user"],
                    success=True,
                    correct=passed,
                    latency_ms=latency,
                    notes=f"variant={variant} turns={turns_passed}/{turns_total}",
                )
                suite.add(ev)

    # Comparison summary
    print("\n" + "=" * 70)
    print("  COMPONENT A/B SUMMARY")
    print("=" * 70)

    print(f"\n  Per-model accuracy across variants:")
    print(f"  {'Model':22s} {'default':12s} {'no_skills':12s} {'no_mem':12s} {'stripped':12s}")
    print(f"  {'-' * 80}")
    for model in MODELS:
        cells = []
        for v in variants:
            total_passed = sum(
                r["turns_passed"] for r in results[model][v].values()
            )
            total_turns = sum(
                r["turns_total"] for r in results[model][v].values()
            )
            pct = 100 * total_passed / total_turns if total_turns else 0
            cells.append(f"{total_passed}/{total_turns} ({pct:3.0f}%)")
        print(f"  {model:22s} " + "  ".join(f"{c:11s}" for c in cells))

    # Per-conversation breakdown
    print(f"\n  Per-conversation pass count (across all models):")
    for convo in CONVERSATIONS:
        cells = []
        for v in variants:
            n_pass = sum(1 for m in MODELS if results[m][v][convo["name"]]["passed"])
            cells.append(f"{n_pass}/{len(MODELS)}")
        print(f"  {convo['name']:32s} " + "  ".join(f"{c:8s}" for c in cells))

    print("\n" + "=" * 70)

    # Save
    out_path = Path(__file__).parent / "component_ab_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"  Full log saved to {out_path}")

    save_results(suite, "component_ab_freeagent_results.json")


if __name__ == "__main__":
    main()
