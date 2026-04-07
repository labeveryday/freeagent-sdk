#!/bin/bash
# Autonomous multi-session build runner for FreeAgent SDK
# Usage: ./build.sh
#
# Runs Claude Code in a loop, piping PROMPT.md as input.
# Each session picks up where the last left off via BUILD_PROGRESS.md.
# Logs go to build-logs/. Monitor progress in BUILD_PROGRESS.md.

set -e

cd "$(dirname "$0")"

MAX_RUNS=6
RUN=0
LOG_DIR="build-logs"
mkdir -p "$LOG_DIR"

echo "============================================"
echo "  FreeAgent SDK — Autonomous Build"
echo "============================================"
echo "Max runs: $MAX_RUNS"
echo "Logs: $LOG_DIR/"
echo "Started: $(date)"
echo "============================================"
echo ""

while [ $RUN -lt $MAX_RUNS ]; do
    RUN=$((RUN + 1))
    TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
    LOG_FILE="$LOG_DIR/run_${RUN}_${TIMESTAMP}.log"

    echo ">>> Run $RUN/$MAX_RUNS - $(date)"
    echo ">>> Log: $LOG_FILE"
    echo ""

    cat PROMPT.md | claude --dangerously-skip-permissions --verbose 2>&1 | tee "$LOG_FILE"

    EXIT_CODE=${PIPESTATUS[1]}
    echo ""
    echo ">>> Run $RUN finished with exit code $EXIT_CODE at $(date)"
    echo ""

    sleep 5
done

echo "============================================"
echo "  Build complete - $RUN runs finished"
echo "  $(date)"
echo "============================================"
