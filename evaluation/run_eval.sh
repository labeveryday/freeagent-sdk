#!/bin/bash
# Run all evaluations sequentially.
# Usage: bash evaluation/run_eval.sh   (from project root)
#    or: cd evaluation && bash run_eval.sh
#
# Each eval saves JSON results to evaluation/ and prints to stdout.
# Run one at a time — Ollama needs the full GPU for each model swap.

set -e

# Resolve evaluation directory regardless of cwd
EVAL_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$(dirname "$EVAL_DIR")/.venv/bin/python"

if [ ! -f "$VENV" ]; then
    echo "ERROR: Python not found at $VENV"
    echo "Create a venv first: python -m venv .venv && source .venv/bin/activate && pip install -e '.[dev]'"
    exit 1
fi

cd "$EVAL_DIR"

echo "============================================"
echo "  FreeAgent SDK — Baseline Evaluations"
echo "  $(date)"
echo "  Python: $VENV"
echo "============================================"

echo ""
echo ">>> Eval 1: Baseline Chat (no tools)"
echo ""
$VENV 01_baseline_chat.py 2>&1 | tee baseline_chat_output.txt

echo ""
echo ">>> Eval 2: Tool Calling"
echo ""
$VENV 02_tool_calling.py 2>&1 | tee tool_calling_output.txt

echo ""
echo ">>> Eval 3: MCP NBA Stats (single-turn)"
echo ""
$VENV 03_mcp_nba.py 2>&1 | tee mcp_nba_output.txt

echo ""
echo ">>> Eval 4: Multi-Turn Tool Calling"
echo ""
$VENV 04_multi_turn.py 2>&1 | tee multi_turn_output.txt

echo ""
echo ">>> Eval 5: Multi-Turn MCP — NBA Conversations"
echo ""
$VENV 05_mcp_multi_turn.py 2>&1 | tee mcp_multi_turn_output.txt

echo ""
echo ">>> Generating combined report"
echo ""
$VENV run_all_report.py

echo ""
echo "Done! Check evaluation/REPORT.md for the combined report."
