# Evaluation Suite

Baseline evaluations comparing **raw Ollama API** vs **Strands Agents SDK** across chat, tool calling, and MCP integration. These establish the performance floor that FreeAgent SDK must beat.

## Prerequisites

- **Ollama running locally** (`ollama serve`)
- **Models pulled**: `qwen3:8b`, `qwen3:4b`, `llama3.1:latest`
- **Python deps installed**: `pip install -e ".[dev]" && pip install "strands-agents[ollama]" nba-stats-mcp`

Override the Ollama URL with `OLLAMA_HOST` env var if not on `localhost:11434`.

## Running

Run everything (expect ~45-60 min on 16GB Mac):

```bash
bash evaluation/run_eval.sh
```

Or run individual evals:

```bash
cd evaluation
../.venv/bin/python 01_baseline_chat.py     # ~10 min
../.venv/bin/python 02_tool_calling.py      # ~15 min
../.venv/bin/python 03_mcp_nba.py           # ~15 min
../.venv/bin/python 04_multi_turn.py        # ~20 min
../.venv/bin/python 05_mcp_multi_turn.py    # ~30 min
```

After evals finish, regenerate the combined report:

```bash
../.venv/bin/python run_all_report.py
```

## What Each Eval Tests

### Eval 1: Baseline Chat (`01_baseline_chat.py`)

Pure chat completion, no tools. 5 cases per model (factual recall, math reasoning, code generation, multi-step logic, instruction following).

**Measures:** latency, tokens/sec (TPS), response accuracy.

**Why:** Establishes the raw model speed floor. Any framework overhead shows up as latency delta vs this baseline.

### Eval 2: Tool Calling (`02_tool_calling.py`)

Native tool calling with 3 mock Python tools (weather, calculator, unit_converter). 8 cases per model ranging from single-tool to multi-step chains.

**Measures:** tool call success rate (did it pick the right tool?), argument accuracy, multi-tool orchestration, latency, TPS.

**Why:** Tests whether the model can produce valid tool calls and whether the framework adds overhead to the tool-calling loop.

### Eval 3: MCP Single-Turn (`03_mcp_nba.py`)

Real MCP tool calling with the [nba-stats-mcp](https://pypi.org/project/nba-stats-mcp/) server (22 tools). 8 single-turn queries (team lookup, player stats, standings, player comparison).

**Measures:** MCP integration reliability, latency with real network I/O (NBA API calls), tool selection from a large tool set.

**Why:** Tests real-world MCP with a large tool catalog and live data. Small models struggle with 22+ tools — this reveals where guardrails matter.

### Eval 4: Multi-Turn Tool Calling (`04_multi_turn.py`)

Conversational tool use across turns with mock tools. 6 conversations (2-4 turns each) where each message builds on prior context.

**Measures:** context retention across turns, correct tool selection given prior results, chained reasoning accuracy.

**Conversations include:**
- Get weather → convert temperature from previous result
- Check two cities sequentially → compare from memory
- Convert units → calculate with the converted value
- Get weather → reason about it without tools
- Check 3 cities → rank from memory
- Get data → user corrects ("actually, I meant Celsius")

**Why:** Real users don't ask one-shot questions. The agent needs to remember what tools returned and use that context in subsequent turns.

### Eval 5: Multi-Turn MCP — NBA Conversations (`05_mcp_multi_turn.py`)

Multi-turn conversations using the NBA MCP server with live data. 5 conversations (3-4 turns each) testing complex real-world queries.

**Conversations:**
- **LeBron vs MJ**: Compare career stats → compare awards/MVPs → GOAT reasoning
- **MJ vs Kobe**: Side-by-side stats → awards → game log best/worst performances → career verdict
- **Team deep dive**: Warriors overview → best player stats → advanced metrics vs Celtics
- **Scoring leaders drill**: Top scorers → compare top 2 → shooting splits for #1
- **Player career arc**: Curry profile → career stats → awards → compare vs Durant

**Measures:** multi-turn context with live data, complex tool orchestration (compare_players, get_player_stats, get_player_awards, get_shooting_data), minimum tool call enforcement, conversational reasoning.

**Why:** This is the hardest test. Multi-turn + large tool catalog + live data + complex reasoning. If FreeAgent can match or beat these baselines here, the framework is doing its job.

## File Structure

```
evaluation/
├── eval_utils.py            # Shared: EvalResult, EvalSuite, Ollama helpers, mock tools
├── 01_baseline_chat.py      # Eval 1: pure chat
├── 02_tool_calling.py       # Eval 2: tool calling with mock tools
├── 03_mcp_nba.py            # Eval 3: MCP single-turn with NBA stats
├── 04_multi_turn.py         # Eval 4: multi-turn with mock tools
├── 05_mcp_multi_turn.py     # Eval 5: multi-turn MCP with NBA stats
├── run_eval.sh              # Run all evals sequentially
├── run_all_report.py        # Generate combined REPORT.md from JSON results
├── README.md                # This file
│
│  (generated after running)
├── baseline_chat_results.json
├── tool_calling_results.json
├── mcp_nba_results.json
├── multi_turn_results.json
├── mcp_multi_turn_results.json
├── REPORT.md                # Combined report with tables
└── *_output.txt             # Raw stdout from each eval
```

## Architecture

All evals share `eval_utils.py` which provides:

- **`EvalResult` / `EvalSuite`** — data model for results, summary stats, JSON export
- **`ollama_chat()` / `ollama_tool_loop()`** — single Ollama HTTP implementation used everywhere
- **`TOOL_FNS` / `OLLAMA_TOOL_SPECS`** — mock tools defined once, used by evals 2 and 4
- **`make_strands_tools()`** — creates Strands tool wrappers with names matching the Ollama specs
- **`check_ollama()`** — connectivity pre-check, exits early with clear message if Ollama is down
- **`save_results()`** — writes JSON to the `evaluation/` directory regardless of cwd

Each eval runs both frameworks (raw Ollama API + Strands Agents) against all 3 models and writes a JSON results file. The report generator reads all available JSON files and produces a combined markdown table.

## Known Limitations

- **Strands TPS**: Strands doesn't expose raw Ollama eval metrics (eval_count, eval_duration), so TPS shows as N/A for Strands results. Latency is still measured end-to-end.
- **Strands tool call counting**: Strands doesn't expose tool call counts in its response object. We verify correctness by response content, not by confirming which tools were called.
- **Live NBA data**: MCP eval results depend on NBA API availability and current season data. Player stats, rosters, and standings change daily.
- **Model swapping**: On 16GB unified RAM, Ollama swaps models in/out of memory. The first query to a new model includes load time. Run evals sequentially (not parallel) to avoid OOM.
