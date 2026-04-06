"""
Run all evaluations and generate a combined report.

Usage:
    cd evaluation
    python run_all.py           # run all evals
    python run_all.py --quick   # just baseline chat (fastest)
"""

import json
import subprocess
import sys
import time
from pathlib import Path


EVALS = [
    ("01_baseline_chat.py", "Baseline Chat"),
    ("02_tool_calling.py", "Tool Calling"),
    ("03_mcp_nba.py", "MCP NBA Stats"),
]


def run_eval(script: str, name: str) -> dict | None:
    """Run a single eval script and return its results."""
    print(f"\n{'#'*60}")
    print(f"# Running: {name}")
    print(f"{'#'*60}")

    start = time.monotonic()
    result = subprocess.run(
        [sys.executable, script],
        capture_output=False,
        timeout=600,  # 10 min max per eval
    )
    elapsed = time.monotonic() - start

    print(f"\n  Completed in {elapsed:.1f}s (exit code: {result.returncode})")

    # Try to load the results file
    results_files = {
        "01_baseline_chat.py": "baseline_chat_results.json",
        "02_tool_calling.py": "tool_calling_results.json",
        "03_mcp_nba.py": "mcp_nba_results.json",
    }
    results_file = results_files.get(script)
    if results_file and Path(results_file).exists():
        with open(results_file) as f:
            return json.load(f)
    return None


def generate_report(all_results: list[dict]):
    """Generate a combined markdown report."""
    report = []
    report.append("# FreeAgent SDK — Baseline Evaluation Report")
    report.append("")
    report.append("Pre-framework baseline comparing raw Ollama API vs Strands Agents SDK.")
    report.append("These results establish the performance floor that FreeAgent must beat.")
    report.append("")
    report.append(f"**Models tested:** qwen3:8b, qwen3:4b, llama3.1:latest")
    report.append("")

    for result_data in all_results:
        if result_data is None:
            continue

        suite_name = result_data.get("suite", "Unknown")
        summary = result_data.get("summary", {})

        report.append(f"## {suite_name}")
        report.append("")

        if summary:
            # Build table
            report.append("| Framework / Model | Success Rate | Accuracy | Avg Latency | Avg TPS |")
            report.append("|---|---|---|---|---|")

            for key, stats in summary.items():
                tps = stats.get("avg_tokens_per_second", "N/A")
                tps_str = f"{tps}" if isinstance(tps, (int, float)) and tps > 0 else "N/A"
                report.append(
                    f"| {key} | {stats['success_rate']} | {stats['accuracy']} | "
                    f"{stats['avg_latency_ms']}ms | {tps_str} |"
                )
            report.append("")

            # Note errors
            for key, stats in summary.items():
                if stats.get("errors"):
                    report.append(f"**Errors ({key}):**")
                    for err in stats["errors"]:
                        report.append(f"- `{err[:120]}`")
                    report.append("")

        # Individual results detail
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
                tps = f"{r['tokens_per_second']:.1f}" if r.get("tokens_per_second") else "—"
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
    report.append("*To be filled in after running evaluations.*")
    report.append("")
    report.append("### What FreeAgent needs to beat:")
    report.append("- Raw Ollama API latency (the floor — no framework overhead)")
    report.append("- Strands accuracy on tool calling (the comparison point)")
    report.append("- MCP integration reliability with real-world tools")
    report.append("")

    report_text = "\n".join(report)

    with open("REPORT.md", "w") as f:
        f.write(report_text)

    print(f"\n{'='*60}")
    print("  Combined report saved to evaluation/REPORT.md")
    print(f"{'='*60}")


def main():
    quick = "--quick" in sys.argv

    evals_to_run = EVALS[:1] if quick else EVALS
    all_results = []

    for script, name in evals_to_run:
        try:
            result = run_eval(script, name)
            all_results.append(result)
        except subprocess.TimeoutExpired:
            print(f"  TIMEOUT: {name} exceeded 10 minutes")
            all_results.append(None)
        except Exception as e:
            print(f"  ERROR: {name} failed: {e}")
            all_results.append(None)

    generate_report(all_results)


if __name__ == "__main__":
    main()
