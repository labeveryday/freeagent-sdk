# Evaluation Suite

FreeAgent SDK evaluation scripts. Every script runs against a real Ollama instance and produces a JSON result file you can inspect.

## Prerequisites

- **Ollama running locally** (`ollama serve`)
- **Models pulled**: `qwen3:8b`, `qwen3:4b`, `llama3.1:latest`, `gemma4:e2b`
- **Python deps installed**: `pip install -e ".[dev]"` (add `nba-stats-mcp` for MCP evals)

Override the Ollama URL with `OLLAMA_HOST` if not on `localhost:11434`.

## Scripts

| # | Script | What it measures |
|---|--------|-----------------|
| 06 | `06_freeagent_baseline.py` | Tool calling accuracy (8 cases × 4 models) |
| 07 | `07_freeagent_multi_turn.py` | Multi-turn conversation without conversation manager |
| 08 | `08_freeagent_mcp.py` | MCP NBA stats integration (21 tools) |
| 09 | `09_skills_ab_test.py` | Bundled skills on vs off |
| 10 | `10_memory_usability.py` | Built-in memory tool usability |
| 11 | `11_freeagent_conversation.py` | Multi-turn with `SlidingWindow` conversation manager |
| 12 | `12_adversarial.py` | Fuzzy names, type coercion, loop traps |
| 13 | `13_component_ab.py` | Skills × memory tool variants |
| 14 | `14_failure_diagnostic.py` | Re-run previously failing cases with trace |
| 15 | `15_autotune_ab.py` | `auto_tune=True` vs forced defaults |
| 16 | `16_streaming_latency.py` | Time-to-first-token for chat + tool runs |
| 17 | `17_trace_completeness.py` | Verify every trace event type fires |

## Running

```bash
cd evaluation
../.venv/bin/python 06_freeagent_baseline.py     # ~15 min
../.venv/bin/python 11_freeagent_conversation.py # ~25 min
../.venv/bin/python 15_autotune_ab.py            # ~20 min
```

Each script writes `*_results.json` in this directory.

## Architecture

`eval_utils.py` provides shared helpers:

- **`EvalResult` / `EvalSuite`** — data model, summary stats, JSON export
- **`ollama_chat()` / `ollama_tool_loop()`** — single Ollama HTTP implementation
- **`TOOL_FNS` / `OLLAMA_TOOL_SPECS`** — mock tools (weather, calculator, unit_converter)
- **`check_ollama()`** — connectivity pre-check
- **`save_results()`** — writes JSON regardless of cwd

## Known Limitations

- **Live NBA data**: MCP eval results depend on NBA API availability. Stats change daily.
- **Model swapping**: On 16GB unified RAM, Ollama swaps models in/out. Run sequentially (not parallel) to avoid OOM.
- **Non-determinism**: Sampling means re-running a failing case often passes. Treat small deltas as noise.
