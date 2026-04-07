"""
FreeAgent Conversation Comparison — reads baseline + FreeAgent results
and generates a comparison table + CONVERSATION_REPORT.md.
"""

import json
from pathlib import Path

EVAL_DIR = Path(__file__).parent

CONVERSATIONS = [
    "weather_then_convert",
    "compare_two_cities",
    "chained_conversion_and_calc",
    "context_retention_no_tools",
    "three_city_itinerary",
    "correction_handling",
]

MODELS_3 = ["qwen3:8b", "qwen3:4b", "llama3.1:latest"]
MODELS_4 = ["qwen3:8b", "qwen3:4b", "llama3.1:latest", "gemma4:e2b"]


def load_results(path):
    with open(path) as f:
        return json.load(f)


def conv_pass_fail(results, framework, model, conv_name):
    """Check if all turns in a conversation passed."""
    turns = [
        r for r in results
        if r["framework"] == framework
        and r["model"] == model
        and r["name"].startswith(conv_name + "_turn")
    ]
    if not turns:
        return None
    return all(r["correct"] for r in turns)


def accuracy_pct(results, framework, model):
    """Overall accuracy for framework+model."""
    matching = [
        r for r in results
        if r["framework"] == framework and r["model"] == model
    ]
    if not matching:
        return None
    correct = sum(1 for r in matching if r["correct"])
    return round(100 * correct / len(matching))


def main():
    # Load all results
    baseline = load_results(EVAL_DIR / "baseline_results" / "multi_turn_results.json")
    old_fa = load_results(EVAL_DIR / "freeagent_multi_turn_results.json")
    new_fa = load_results(EVAL_DIR / "freeagent_conversation_results.json")

    all_baseline = baseline["results"]
    all_old_fa = old_fa["results"]
    all_new_fa = new_fa["results"]

    # ── Print comparison table ──
    print("\n" + "=" * 90)
    print("  MULTI-TURN CONVERSATION COMPARISON")
    print("=" * 90)

    # Per-conversation table for 3 shared models
    header = f"{'Conversation':<30s} {'Model':<18s} {'Raw Ollama':>10s} {'Strands':>10s} {'FA (old)':>10s} {'FA (conv)':>10s}"
    print(f"\n{header}")
    print("-" * 90)

    for conv in CONVERSATIONS:
        for model in MODELS_3:
            raw = conv_pass_fail(all_baseline, "ollama_raw", model, conv)
            strands = conv_pass_fail(all_baseline, "strands", model, conv)
            old = conv_pass_fail(all_old_fa, "freeagent", model, conv)
            new = conv_pass_fail(all_new_fa, "freeagent_conversation", model, conv)

            def fmt(v):
                if v is None:
                    return "N/A"
                return "PASS" if v else "FAIL"

            label = conv if model == MODELS_3[0] else ""
            print(f"{label:<30s} {model:<18s} {fmt(raw):>10s} {fmt(strands):>10s} {fmt(old):>10s} {fmt(new):>10s}")

    # gemma4:e2b (new model, no baselines)
    print(f"\n{'--- gemma4:e2b (ReactEngine, no baseline) ---'}")
    for conv in CONVERSATIONS:
        new = conv_pass_fail(all_new_fa, "freeagent_conversation", "gemma4:e2b", conv)
        print(f"  {conv:<35s} {'PASS' if new else 'FAIL'}")

    # Overall accuracy
    print(f"\n{'=' * 90}")
    print("  OVERALL ACCURACY (turn-level)")
    print(f"{'=' * 90}")
    print(f"\n{'Model':<18s} {'Raw Ollama':>10s} {'Strands':>10s} {'FA (old)':>10s} {'FA (conv)':>10s} {'Delta vs Raw':>12s}")
    print("-" * 70)

    for model in MODELS_3:
        raw = accuracy_pct(all_baseline, "ollama_raw", model)
        strands = accuracy_pct(all_baseline, "strands", model)
        old = accuracy_pct(all_old_fa, "freeagent", model)
        new = accuracy_pct(all_new_fa, "freeagent_conversation", model)
        delta = f"{new - raw:+d}%" if raw is not None and new is not None else "N/A"
        print(f"{model:<18s} {raw:>9d}% {strands:>9d}% {old:>9d}% {new:>9d}% {delta:>12s}")

    # gemma4:e2b
    new_gemma = accuracy_pct(all_new_fa, "freeagent_conversation", "gemma4:e2b")
    print(f"{'gemma4:e2b':<18s} {'N/A':>10s} {'N/A':>10s} {'N/A':>10s} {new_gemma:>9d}% {'(new)':>12s}")

    # ── Generate CONVERSATION_REPORT.md ──
    report = generate_report(all_baseline, all_old_fa, all_new_fa)
    report_path = EVAL_DIR / "CONVERSATION_REPORT.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"\nReport saved to {report_path}")


def generate_report(all_baseline, all_old_fa, all_new_fa):
    lines = []
    lines.append("# Multi-Turn Conversation Evaluation Report")
    lines.append("")
    lines.append("Comparison of multi-turn conversation performance across frameworks.")
    lines.append("")
    lines.append("## Setup")
    lines.append("")
    lines.append("- **Test cases**: 6 multi-turn conversations (15 total turns)")
    lines.append("- **Frameworks**: Raw Ollama API, Strands Agents, FreeAgent (old, no state), FreeAgent (conversation manager)")
    lines.append("- **Models**: qwen3:8b, qwen3:4b, llama3.1:latest, gemma4:e2b (FreeAgent only)")
    lines.append("- **FreeAgent conversation strategy**: SlidingWindow(max_turns=20) (default)")
    lines.append("- **gemma4:e2b**: Uses ReactEngine (text-based ReAct) — not in native_tool_models")
    lines.append("")

    # Overall accuracy table
    lines.append("## Overall Accuracy (turn-level)")
    lines.append("")
    lines.append("| Model | Raw Ollama | Strands | FreeAgent (old) | FreeAgent (conversation) | Delta vs Raw |")
    lines.append("|-------|-----------|---------|-----------------|-------------------------|-------------|")

    for model in MODELS_3:
        raw = accuracy_pct(all_baseline, "ollama_raw", model)
        strands = accuracy_pct(all_baseline, "strands", model)
        old = accuracy_pct(all_old_fa, "freeagent", model)
        new = accuracy_pct(all_new_fa, "freeagent_conversation", model)
        delta = f"{new - raw:+d}%" if raw is not None and new is not None else "N/A"
        lines.append(f"| {model} | {raw}% | {strands}% | {old}% | {new}% | {delta} |")

    new_gemma = accuracy_pct(all_new_fa, "freeagent_conversation", "gemma4:e2b")
    lines.append(f"| gemma4:e2b | N/A | N/A | N/A | {new_gemma}% | (new) |")
    lines.append("")

    # Per-conversation table
    lines.append("## Per-Conversation Results")
    lines.append("")
    lines.append("| Conversation | Model | Raw Ollama | Strands | FA (old) | FA (conversation) |")
    lines.append("|-------------|-------|-----------|---------|----------|-------------------|")

    for conv in CONVERSATIONS:
        for i, model in enumerate(MODELS_3):
            raw = conv_pass_fail(all_baseline, "ollama_raw", model, conv)
            strands = conv_pass_fail(all_baseline, "strands", model, conv)
            old = conv_pass_fail(all_old_fa, "freeagent", model, conv)
            new = conv_pass_fail(all_new_fa, "freeagent_conversation", model, conv)

            def fmt(v):
                if v is None:
                    return "N/A"
                return "PASS" if v else "FAIL"

            label = conv if i == 0 else ""
            lines.append(f"| {label} | {model} | {fmt(raw)} | {fmt(strands)} | {fmt(old)} | {fmt(new)} |")

    lines.append("")

    # gemma4:e2b results
    lines.append("## gemma4:e2b (ReactEngine)")
    lines.append("")
    lines.append("First evaluation of ReactEngine with a real ReAct-only model (2B params).")
    lines.append("")
    lines.append("| Conversation | Result |")
    lines.append("|-------------|--------|")

    for conv in CONVERSATIONS:
        new = conv_pass_fail(all_new_fa, "freeagent_conversation", "gemma4:e2b", conv)
        lines.append(f"| {conv} | {'PASS' if new else 'FAIL'} |")

    lines.append("")

    # Failure analysis
    lines.append("## Failure Analysis")
    lines.append("")

    # Collect failures
    failures = [r for r in all_new_fa if not r["correct"]]
    if failures:
        lines.append("| Model | Turn | Notes |")
        lines.append("|-------|------|-------|")
        for f in failures:
            notes = f.get("notes", "")
            resp_preview = f.get("response", "")[:80].replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {f['model']} | {f['name']} | {notes} |")
        lines.append("")

    # Key findings
    lines.append("## Key Findings")
    lines.append("")
    lines.append("1. **Conversation manager improves multi-turn accuracy** — FreeAgent with conversation manager (87% qwen3:8b, 87% qwen3:4b) vs old FreeAgent without state (78% both). The conversation context allows later turns to reference earlier results without restating them.")
    lines.append("")
    lines.append("2. **FreeAgent now matches or beats Strands on multi-turn** — 87% vs 73% (qwen3:8b), 87% vs 80% (qwen3:4b), 80% vs 73% (llama3.1). Strands had the advantage of built-in conversation state; now FreeAgent does too.")
    lines.append("")
    lines.append("3. **Raw Ollama still edges out on qwen models** (93% vs 87%) — the raw API has zero framework overhead in the system prompt, while FreeAgent adds ~300 tokens of skills+memory context that can confuse multi-turn reasoning on some cases.")
    lines.append("")
    lines.append("4. **gemma4:e2b (ReactEngine) performs well at 80%** — matching llama3.1 accuracy despite being a 2B model using text-based ReAct instead of native tool calling. ReactEngine successfully parses tool calls from text output.")
    lines.append("")
    lines.append("5. **Common failure mode: `context_retention_no_tools`** — all 4 models struggle with the umbrella question. Models either re-call the weather tool unnecessarily or don't include 'yes' in their response about overcast weather.")
    lines.append("")
    lines.append("6. **llama3.1 quirk: unnecessary tool calls** — when asked to compare or rank without tools, llama3.1 sometimes calls calculator or weather anyway. This was also observed in Phase 8 integration tests.")
    lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    main()
