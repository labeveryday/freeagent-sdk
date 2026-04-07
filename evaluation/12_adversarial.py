"""
Eval 12: Adversarial test — does FreeAgent rescue cases where raw Ollama fails?

For each adversarial case:
1. Run with raw Ollama API + manual tool loop (no framework rescue)
2. Run with FreeAgent (full guardrails)
3. Compare outcomes:
   - Both pass → no rescue needed
   - Both fail → guardrails insufficient
   - Raw fails, FreeAgent passes → RESCUE (was a guardrail involved?)
   - Raw passes, FreeAgent fails → REGRESSION (framework hurt)
4. Track which guardrails fired in FreeAgent (validation_errors, retries, loop, etc.)

Output: rescue rate, regression rate, guardrail trigger counts.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from adversarial_cases import (
    ADVERSARIAL_CASES,
    TOOL_FNS,
    TARGETS,
)
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


# ── Raw Ollama runner (no framework) ─────────────────────

def run_raw_ollama(model: str, case: dict, max_iterations: int = 5):
    """Manual tool loop with raw Ollama API. No framework rescue."""
    messages = [
        {"role": "system", "content": "You are a helpful assistant. Use the provided tools."},
        {"role": "user", "content": case["prompt"]},
    ]

    tools = case["tools"]
    tool_calls_made = []
    total_latency = 0
    total_tokens = 0
    raw_errors = []  # tool not found, missing args, etc.

    for iteration in range(max_iterations):
        start = time.monotonic()
        try:
            resp = ollama_chat(model, messages, tools)
        except Exception as e:
            raw_errors.append(f"connection: {e}")
            return {
                "response": "[connection error]",
                "tool_calls": tool_calls_made,
                "latency_ms": total_latency,
                "tokens": total_tokens,
                "raw_errors": raw_errors,
            }
        elapsed = (time.monotonic() - start) * 1000
        total_latency += elapsed
        total_tokens += resp.get("eval_count", 0)

        msg = resp.get("message", {})
        tool_calls = msg.get("tool_calls", [])

        if not tool_calls:
            return {
                "response": msg.get("content", ""),
                "tool_calls": tool_calls_made,
                "latency_ms": total_latency,
                "tokens": total_tokens,
                "raw_errors": raw_errors,
            }

        messages.append(msg)

        for tc in tool_calls:
            fn_name = tc.get("function", {}).get("name", "")
            fn_args = tc.get("function", {}).get("arguments", {})
            tool_calls_made.append({"name": fn_name, "args": fn_args})

            fn = TOOL_FNS.get(fn_name)
            if fn is None:
                # Tool not found — raw Ollama has no fuzzy matching
                err_msg = json.dumps({"error": f"Unknown tool: {fn_name}. Available tools: {list(TOOL_FNS.keys())}"})
                raw_errors.append(f"unknown_tool:{fn_name}")
                messages.append({"role": "tool", "content": err_msg})
                continue

            try:
                # For "huge_tool_output" cases, inject a giant payload
                if case.get("use_huge_output"):
                    real_result = fn(**fn_args)
                    huge = "X" * 5000
                    real_result["padding"] = huge
                    result = real_result
                else:
                    result = fn(**fn_args)
            except TypeError as e:
                raw_errors.append(f"type_error:{e}")
                result = {"error": f"TypeError: {e}"}
            except Exception as e:
                raw_errors.append(f"exception:{e}")
                result = {"error": str(e)}

            messages.append({"role": "tool", "content": json.dumps(result)})

    return {
        "response": "[max iterations]",
        "tool_calls": tool_calls_made,
        "latency_ms": total_latency,
        "tokens": total_tokens,
        "raw_errors": raw_errors,
    }


# ── FreeAgent runner ──────────────────────────────────────

def run_freeagent(model: str, case: dict):
    """Run via FreeAgent with full guardrails."""
    from freeagent import Agent, tool as tool_decorator
    from freeagent.providers.ollama import OllamaProvider

    # Build FreeAgent tools that match the case spec names
    @tool_decorator(name="weather")
    def weather(city: str) -> dict:
        """Get current weather for a city."""
        result = TOOL_FNS["weather"](city)
        if case.get("use_huge_output"):
            result["padding"] = "X" * 5000
        return result

    @tool_decorator(name="calculator")
    def calculator(expression: str) -> dict:
        """Evaluate a math expression."""
        return TOOL_FNS["calculator"](expression)

    @tool_decorator(name="unit_converter")
    def unit_converter(value: float, from_unit: str, to_unit: str) -> dict:
        """Convert between units (miles/km, F/C, lbs/kg)."""
        return TOOL_FNS["unit_converter"](value, from_unit, to_unit)

    # Match case tools
    tool_map = {"weather": weather, "calculator": calculator, "unit_converter": unit_converter}
    case_tool_names = {t["function"]["name"] for t in case["tools"]}
    fa_tools = [tool_map[n] for n in case_tool_names if n in tool_map]

    agent = Agent(
        model=model,
        tools=fa_tools,
        system_prompt="You are a helpful assistant. Use the provided tools.",
        conversation=None,  # single-shot, no multi-turn for this eval
    )

    start = time.monotonic()
    try:
        response = agent.run(case["prompt"])
    except Exception as e:
        return {
            "response": f"[error: {e}]",
            "latency_ms": (time.monotonic() - start) * 1000,
            "guardrails": {},
            "metrics": None,
        }

    elapsed = (time.monotonic() - start) * 1000
    last = agent.metrics.last_run

    guardrails = {
        "validation_errors": last.validation_errors if last else 0,
        "retries": last.retries if last else 0,
        "loop_detected": last.loop_detected if last else False,
        "max_iter_hit": last.max_iter_hit if last else False,
        "timed_out": last.timed_out if last else False,
        "fallback_model": last.fallback_model if last else "",
        "tool_calls": last.tool_call_count if last else 0,
        "tools_used": last.tools_used if last else [],
        "iterations": last.iterations if last else 0,
    }

    return {
        "response": response,
        "latency_ms": elapsed,
        "guardrails": guardrails,
        "metrics": last,
    }


# ── Main ──────────────────────────────────────────────────

def main():
    suite = EvalSuite(name="Adversarial — Framework Rescue Test")

    print("\n" + "=" * 70)
    print("  EVAL 12: Adversarial — Does FreeAgent Rescue Failures?")
    print("=" * 70)

    check_ollama()

    rescue_log = []

    for model in MODELS:
        print(f"\n  Model: {model}")
        print(f"  {'─' * 60}")

        for case in ADVERSARIAL_CASES:
            print(f"\n    Case: {case['name']:25s} (target: {case['target']})")

            # Raw Ollama
            try:
                raw = run_raw_ollama(model, case)
                raw_text = raw["response"] + " " + json.dumps(raw["tool_calls"])
                raw_pass = check_response_contains(raw_text, case["expected_in_response"])
                raw_status = "PASS" if raw_pass else "FAIL"
                raw_err = f" errors:{len(raw['raw_errors'])}" if raw['raw_errors'] else ""
                print(f"      raw_ollama:   {raw_status}  {raw['latency_ms']:6.0f}ms{raw_err}")
            except Exception as e:
                raw_pass = False
                raw = {"response": f"[error: {e}]", "raw_errors": [str(e)], "latency_ms": 0}
                print(f"      raw_ollama:   ERR   {str(e)[:60]}")

            # FreeAgent
            try:
                fa = run_freeagent(model, case)
                fa_pass = check_response_contains(fa["response"], case["expected_in_response"])
                fa_status = "PASS" if fa_pass else "FAIL"
                g = fa["guardrails"]
                triggers = []
                if g.get("validation_errors"):
                    triggers.append(f"val_err={g['validation_errors']}")
                if g.get("retries"):
                    triggers.append(f"retries={g['retries']}")
                if g.get("loop_detected"):
                    triggers.append("LOOP")
                if g.get("max_iter_hit"):
                    triggers.append("MAX_ITER")
                if g.get("timed_out"):
                    triggers.append("TIMEOUT")
                trig_str = "  triggers:[" + ",".join(triggers) + "]" if triggers else ""
                print(f"      freeagent:    {fa_status}  {fa['latency_ms']:6.0f}ms{trig_str}")
            except Exception as e:
                fa_pass = False
                fa = {"response": f"[error: {e}]", "guardrails": {}, "latency_ms": 0}
                print(f"      freeagent:    ERR   {str(e)[:60]}")

            # Outcome category
            if raw_pass and fa_pass:
                outcome = "both_pass"
            elif not raw_pass and fa_pass:
                outcome = "RESCUE"
            elif raw_pass and not fa_pass:
                outcome = "REGRESSION"
            else:
                outcome = "both_fail"

            # If rescue, was it real (guardrail triggered) or accidental?
            real_rescue = False
            if outcome == "RESCUE":
                g = fa["guardrails"]
                real_rescue = bool(
                    g.get("validation_errors") or g.get("retries") or
                    g.get("loop_detected") or g.get("max_iter_hit")
                )

            print(f"      → {outcome}{' (REAL guardrail rescue!)' if real_rescue else ''}")

            rescue_log.append({
                "case": case["name"],
                "target": case["target"],
                "model": model,
                "raw_pass": raw_pass,
                "fa_pass": fa_pass,
                "outcome": outcome,
                "real_rescue": real_rescue,
                "raw_response": (raw.get("response") or "")[:200],
                "fa_response": (fa.get("response") or "")[:200],
                "raw_errors": raw.get("raw_errors", []),
                "fa_guardrails": fa.get("guardrails", {}),
                "raw_latency_ms": raw.get("latency_ms", 0),
                "fa_latency_ms": fa.get("latency_ms", 0),
            })

            # Add to EvalSuite for the summary report
            ev = EvalResult(
                name=f"{case['name']}_{model}",
                framework="freeagent_adversarial",
                model=model,
                prompt=case["prompt"],
                response=fa.get("response", "")[:500],
                success=True,
                correct=fa_pass,
                latency_ms=fa.get("latency_ms", 0),
                notes=f"target={case['target']} outcome={outcome} real_rescue={real_rescue}",
            )
            suite.add(ev)

    # Aggregate summary
    print("\n" + "=" * 70)
    print("  ADVERSARIAL EVAL SUMMARY")
    print("=" * 70)

    total = len(rescue_log)
    both_pass = sum(1 for r in rescue_log if r["outcome"] == "both_pass")
    rescues = sum(1 for r in rescue_log if r["outcome"] == "RESCUE")
    real_rescues = sum(1 for r in rescue_log if r["real_rescue"])
    regressions = sum(1 for r in rescue_log if r["outcome"] == "REGRESSION")
    both_fail = sum(1 for r in rescue_log if r["outcome"] == "both_fail")

    print(f"\n  Total runs: {total}")
    print(f"  Both pass:       {both_pass} ({100*both_pass/total:.0f}%)")
    print(f"  Rescues:         {rescues} ({100*rescues/total:.0f}%)")
    print(f"    of which real: {real_rescues} (guardrail triggered)")
    print(f"  Regressions:     {regressions} ({100*regressions/total:.0f}%)")
    print(f"  Both fail:       {both_fail} ({100*both_fail/total:.0f}%)")

    # By target
    print(f"\n  Rescue rate by target guardrail:")
    for target, desc in TARGETS.items():
        target_runs = [r for r in rescue_log if r["target"] == target]
        if not target_runs:
            continue
        target_rescues = sum(1 for r in target_runs if r["outcome"] == "RESCUE")
        target_real = sum(1 for r in target_runs if r["real_rescue"])
        print(f"    {target:20s} {target_rescues}/{len(target_runs)} rescues ({target_real} real)  — {desc}")

    print("\n" + "=" * 70)

    # Save full log
    out_path = Path(__file__).parent / "adversarial_results.json"
    with open(out_path, "w") as f:
        json.dump({
            "summary": {
                "total": total,
                "both_pass": both_pass,
                "rescues": rescues,
                "real_rescues": real_rescues,
                "regressions": regressions,
                "both_fail": both_fail,
            },
            "rescue_log": rescue_log,
        }, f, indent=2, default=str)
    print(f"  Full log saved to {out_path}")

    save_results(suite, "adversarial_freeagent_results.json")


if __name__ == "__main__":
    main()
