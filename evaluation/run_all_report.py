"""
Generate combined REPORT.md from individual eval JSON results.
Run after the evals complete: python run_all_report.py
"""

import json
from pathlib import Path

EVAL_DIR = Path(__file__).parent

FILES = [
    ("baseline_chat_results.json", "Baseline Chat"),
    ("tool_calling_results.json", "Tool Calling"),
    ("mcp_nba_results.json", "MCP NBA Stats"),
    ("multi_turn_results.json", "Multi-Turn Tool Calling"),
    ("mcp_multi_turn_results.json", "Multi-Turn MCP — NBA Conversations"),
]


def load_results(filename: str) -> dict | None:
    p = EVAL_DIR / filename
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return None


def generate_report():
    all_results = []
    for filename, label in FILES:
        data = load_results(filename)
        if data:
            all_results.append(data)
            print(f"  Loaded {filename}")
        else:
            print(f"  Skipped {filename} (not found)")

    if not all_results:
        print("No results found. Run the evaluations first.")
        return

    report = []
    report.append("# FreeAgent SDK — Baseline Evaluation Report")
    report.append("")
    report.append("Pre-framework baseline comparing raw Ollama API vs Strands Agents SDK.")
    report.append("These results establish the performance floor that FreeAgent must beat.")
    report.append("")
    report.append("**Models tested:** qwen3:8b, qwen3:4b, llama3.1:latest")
    report.append("")

    for result_data in all_results:
        suite_name = result_data.get("suite", "Unknown")
        summary = result_data.get("summary", {})

        report.append(f"## {suite_name}")
        report.append("")

        if summary:
            report.append("| Framework / Model | Success Rate | Accuracy | Avg Latency | Avg TPS |")
            report.append("|---|---|---|---|---|")

            for key, stats in summary.items():
                tps = stats.get("avg_tokens_per_second", 0)
                tps_str = f"{tps}" if isinstance(tps, (int, float)) and tps > 0 else "N/A"
                report.append(
                    f"| {key} | {stats['success_rate']} | {stats['accuracy']} | "
                    f"{stats['avg_latency_ms']}ms | {tps_str} |"
                )
            report.append("")

            for key, stats in summary.items():
                if stats.get("errors"):
                    report.append(f"**Errors ({key}):**")
                    for err in stats["errors"]:
                        report.append(f"- `{err[:120]}`")
                    report.append("")

        results = result_data.get("results", [])
        if results:
            report.append("<details>")
            report.append(f"<summary>Detailed Results ({len(results)} cases)</summary>")
            report.append("")
            report.append("| Case | Framework | Model | Pass | Latency | TPS | Error |")
            report.append("|---|---|---|---|---|---|---|")
            for r in results:
                pass_str = "PASS" if r["correct"] else ("ERR" if r["error"] else "FAIL")
                err = r["error"][:60] if r["error"] else ""
                tps = f"{r['tokens_per_second']:.1f}" if r.get("tokens_per_second") else "-"
                report.append(
                    f"| {r['name']} | {r['framework']} | {r['model']} | "
                    f"{pass_str} | {r['latency_ms']:.0f}ms | {tps} | {err} |"
                )
            report.append("")
            report.append("</details>")
            report.append("")

    report.append("---")
    report.append("")
    report.append("## Key Takeaways")
    report.append("")
    report.append("*To be filled in after reviewing results.*")
    report.append("")
    report.append("### What FreeAgent needs to beat:")
    report.append("- Raw Ollama API latency (the floor — no framework overhead)")
    report.append("- Strands accuracy on tool calling (the comparison point)")
    report.append("- MCP integration reliability with real-world tools")
    report.append("")

    report_text = "\n".join(report)

    out = EVAL_DIR / "REPORT.md"
    with open(out, "w") as f:
        f.write(report_text)

    print(f"\n  Report saved to {out}")


if __name__ == "__main__":
    generate_report()
