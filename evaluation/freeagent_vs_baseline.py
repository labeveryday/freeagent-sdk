"""
FreeAgent vs Baseline Comparison

Reads all result JSON files and prints a comparison table:
  | Test          | Raw Ollama | Strands | FreeAgent | Delta |
"""

import json
from pathlib import Path

EVAL_DIR = Path(__file__).parent


def load_results(filename: str) -> dict | None:
    """Load a results JSON file."""
    path = EVAL_DIR / filename
    if not path.exists():
        # Check backup directory
        backup = EVAL_DIR / "baseline_results" / filename
        if backup.exists():
            path = backup
        else:
            return None
    with open(path) as f:
        return json.load(f)


def extract_accuracy(data: dict, framework_prefix: str) -> dict:
    """Extract per-model accuracy from results data."""
    accuracies = {}
    if not data:
        return accuracies

    for key, stats in data.get("summary", {}).items():
        # key format: "framework / model"
        if framework_prefix in key:
            model = key.split("/")[-1].strip()
            acc_str = stats.get("accuracy", "0/0 (0%)")
            # Parse "6/8 (75%)" format
            try:
                pct = acc_str.split("(")[1].rstrip("%)")
                accuracies[model] = int(pct)
            except (IndexError, ValueError):
                accuracies[model] = 0
    return accuracies


def main():
    print("\n" + "="*80)
    print("  FREEAGENT vs BASELINE COMPARISON")
    print("="*80)

    # ── Tool Calling ──
    print("\n  Tool Calling Accuracy")
    print(f"  {'Model':<20s} {'Raw Ollama':<12s} {'Strands':<12s} {'FreeAgent':<12s} {'Delta vs Raw':<12s}")
    print(f"  {'─'*68}")

    baseline = load_results("tool_calling_results.json")
    freeagent = load_results("freeagent_tool_calling_results.json")

    raw_acc = extract_accuracy(baseline, "ollama_raw")
    strands_acc = extract_accuracy(baseline, "strands")
    fa_acc = extract_accuracy(freeagent, "freeagent")

    models = ["qwen3:8b", "qwen3:4b", "llama3.1:latest"]
    for model in models:
        raw = raw_acc.get(model, "—")
        strands = strands_acc.get(model, "—")
        fa = fa_acc.get(model, "—")
        delta = ""
        if isinstance(raw, int) and isinstance(fa, int):
            d = fa - raw
            delta = f"+{d}%" if d > 0 else f"{d}%" if d < 0 else "0%"
        print(f"  {model:<20s} {str(raw)+'%':<12s} {str(strands)+'%':<12s} {str(fa)+'%':<12s} {delta:<12s}")

    # ── Multi-Turn ──
    print("\n  Multi-Turn Accuracy")
    print(f"  {'Model':<20s} {'Raw Ollama':<12s} {'Strands':<12s} {'FreeAgent':<12s}")
    print(f"  {'─'*56}")

    mt_baseline = load_results("multi_turn_results.json")
    mt_freeagent = load_results("freeagent_multi_turn_results.json")

    mt_raw = extract_accuracy(mt_baseline, "ollama_raw")
    mt_strands = extract_accuracy(mt_baseline, "strands")
    mt_fa = extract_accuracy(mt_freeagent, "freeagent")

    for model in models:
        raw = mt_raw.get(model, "—")
        strands = mt_strands.get(model, "—")
        fa = mt_fa.get(model, "—")
        print(f"  {model:<20s} {str(raw)+'%':<12s} {str(strands)+'%':<12s} {str(fa)+'%':<12s}")

    # ── MCP ──
    print("\n  MCP NBA Stats Accuracy")
    print(f"  {'Model':<20s} {'Raw Ollama':<12s} {'Strands':<12s} {'FreeAgent':<12s}")
    print(f"  {'─'*56}")

    mcp_baseline = load_results("mcp_nba_results.json")
    mcp_freeagent = load_results("freeagent_mcp_results.json")

    mcp_raw = extract_accuracy(mcp_baseline, "ollama_raw")
    mcp_strands = extract_accuracy(mcp_baseline, "strands")
    mcp_fa = extract_accuracy(mcp_freeagent, "freeagent")

    for model in models:
        raw = mcp_raw.get(model, "—")
        strands = mcp_strands.get(model, "—")
        fa = mcp_fa.get(model, "—")
        print(f"  {model:<20s} {str(raw)+'%':<12s} {str(strands)+'%':<12s} {str(fa)+'%':<12s}")

    # ── Skills A/B ──
    skills_data = load_results("skills_ab_results.json")
    if skills_data:
        print("\n  Skills A/B Test")
        print(f"  {'Model':<20s} {'With Skills':<15s} {'No Skills':<15s} {'Delta':<10s}")
        print(f"  {'─'*60}")

        with_acc = extract_accuracy(skills_data, "freeagent_with_skills")
        no_acc = extract_accuracy(skills_data, "freeagent_no_skills")

        for model in models:
            ws = with_acc.get(model, "—")
            ns = no_acc.get(model, "—")
            delta = ""
            if isinstance(ws, int) and isinstance(ns, int):
                d = ws - ns
                delta = f"+{d}%" if d > 0 else f"{d}%" if d < 0 else "0%"
            print(f"  {model:<20s} {str(ws)+'%':<15s} {str(ns)+'%':<15s} {delta:<10s}")

    # ── Memory Usability ──
    mem_data = load_results("memory_usability_results.json")
    if mem_data:
        print("\n  Memory Tool Usability")
        print(f"  {'Model':<20s} {'Accuracy':<15s}")
        print(f"  {'─'*35}")

        mem_acc = extract_accuracy(mem_data, "freeagent_memory")
        for model in models:
            acc = mem_acc.get(model, "—")
            print(f"  {model:<20s} {str(acc)+'%':<15s}")

    print(f"\n{'='*80}\n")


if __name__ == "__main__":
    main()
