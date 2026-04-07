# Changelog

## 0.3.0 (2026-04-07)

### Phase 20: Streaming Support
- Added `freeagent/events.py` with semantic event types: `RunStartEvent`, `TokenEvent`, `ToolCallEvent`, `ToolResultEvent`, `ValidationErrorEvent`, `RetryEvent`, `IterationEvent`, `RunCompleteEvent`
- Added `StreamChunk` dataclass and `chat_stream`/`chat_stream_with_tools` to Provider protocol
- Implemented streaming in `OllamaProvider` (JSONL parsing) and `OpenAICompatProvider` (SSE parsing)
- Added `Agent.arun_stream()` — async generator yielding `RunEvent`s
- Added `Agent.run_stream()` — sync wrapper using `SyncBridge` queue
- Refactored `Agent.arun()` to internally consume `arun_stream()` (backward compatible)
- All event types exported from `freeagent` and `freeagent.events`
- 19 new unit tests, live integration tests for streaming

### Phase 21: Model-Aware Defaults
- Added `freeagent/model_info.py` — `ModelInfo` dataclass and `fetch_model_info()` for Ollama `/api/show`
- Auto-tune: small models (<3B) strip bundled skills and memory tool by default
- Auto-tune: context window set from model's actual limit
- Auto-tune: engine selection uses detected capabilities instead of hardcoded list
- New Agent parameters: `auto_tune` (default True), `bundled_skills`, `memory_tool`
- Explicit `bundled_skills=True` or `memory_tool=True` overrides auto-tune
- 16 new unit tests, 6 live integration tests

### Phase 22: Trace API for Inspection
- Added `TraceEvent` dataclass to `RunRecord` — timestamped event log for each run
- Metrics methods now append trace events alongside count updates
- `RunRecord.trace()` — human-readable timeline with relative timestamps
- `RunRecord.to_markdown()` — full markdown report with sections
- `RunRecord.summary()` — one-line run summary
- `Agent.last_run` property and `Agent.trace()` shortcut
- 12 new unit tests

## 0.2.0 (2026-04-06)

### Phase 1: Package Restructure & httpx Migration
- Renamed `src/` → `freeagent/` for proper Python package layout
- Bumped version to 0.2.0
- Replaced `urllib.request` with `httpx.AsyncClient` in both providers (Ollama, OpenAI-compat)
- Added `_SyncBridge` for safe sync→async bridging (handles Jupyter, nested loops)
- Updated `Agent.run()` to use `_SyncBridge` instead of fragile `asyncio.run()`/`ThreadPoolExecutor`
- Updated all examples to use `from freeagent import ...`

### Phase 2: Small-Model Reliability Features
- Added `sanitize.py` — ANSI stripping, HTML removal, whitespace normalization, JSON flattening
- Added `context.py` — token estimation, context window management with message pruning
- Added tool output truncation with "truncate" and "summarize_head_tail" strategies
- Added model fallback on `ConnectionError` via `fallback_models` config
- New `AgentConfig` fields: `max_tool_result_chars`, `context_window`, `context_soft_threshold`, `fallback_models`
- Wired sanitization + truncation into agent loop after tool execution
- Wired context window checking before each model call

### Phase 3: Comprehensive Unit Tests
- 173 tests covering all modules: validator, circuit breaker, tool, messages, skills, memory, telemetry, providers, engines, agent
- Full integration tests with mock providers: chat mode, tool calls, validation retry, circuit breaker, timeout, hooks, telemetry
- pytest-asyncio auto mode configured

### Phase 4: Parallel Tool Calling
- Added `ToolCall` dataclass in engines for structured tool call representation
- Updated `EngineResult` to support multiple tool calls via `tool_calls` list
- `NativeEngine` now handles all `response.tool_calls`, not just `[0]`
- Agent loop validates each call independently, executes concurrently with `asyncio.gather()`
- One bad call doesn't block good ones — valid calls execute, errors get feedback
- Circuit breaker checks each call independently
- ReactEngine stays single-call (by design — small models)

### Phase 5: MCP Support
- Added `freeagent/mcp/` package with client and adapter modules
- `connect()` context manager for stdio and streamable HTTP transports
- MCP tool schemas converted to FreeAgent ToolParam objects
- Verbose descriptions auto-truncated to 100 chars for small model context budgets
- Tool index builder for system prompt when > 10 tools
- Conditional export: only available if `mcp` package is installed
- `pip install freeagent-sdk[mcp]` optional dependency

### Phase 6: Documentation & Polish
- Updated README.md with skills, memory, providers, telemetry, MCP, and reliability sections
- Updated freeagent-sdk.html with Skills, Providers, and Telemetry panels
- Updated stats, roadmap, and feature grid to reflect v0.2.0 capabilities
- 191 tests passing across all modules

### Phase 7: Baseline Evaluations
- 5 evaluations: baseline chat, tool calling, MCP NBA stats, multi-turn, multi-turn MCP
- Compared raw Ollama API vs Strands Agents SDK across 3 models
- Results: Raw Ollama generally matches or beats Strands in accuracy

### Phase 8: Live Integration Tests
- 29 integration tests across 5 files: chat, tools, memory, skills, ReactEngine
- All 3 models (qwen3:8b, qwen3:4b, llama3.1) work end-to-end with FreeAgent
- All tests marked `@pytest.mark.integration` for CI skip
- Memory tool single-action pattern understood by all models

### Phases 9-11: FreeAgent Evaluations
- 5 FreeAgent eval scripts: tool calling, multi-turn, MCP, skills A/B, memory usability
- FreeAgent matches or beats Strands accuracy across all eval types
- FreeAgent improves llama3.1 tool calling by +13% vs raw Ollama
- Skills improve qwen3:4b accuracy by +20%
- Memory tool usability at 60% — fixed `.md` extension bug

### Phase 12: Data-Driven Fixes
- Fixed `Memory._resolve()` to auto-append `.md` when models omit the file extension
- 220 total tests passing (191 unit + 29 integration)

### Phase 13: Final Documentation & Release Prep
- Added Benchmarks panel to freeagent-sdk.html with full comparison data
- Updated evaluation REPORT.md title and description to reflect FreeAgent results
- Updated test counts (191 → 220) across HTML and footer
- Verified all examples run end-to-end with Ollama
- Verified `pip install -e .` works and all 191 unit tests pass

### Conversation Manager & SyncBridge Fix
- Added `freeagent/conversation.py` — pluggable multi-turn conversation strategies
  - `SlidingWindow(max_turns=20)` — default, keeps last N turns
  - `TokenWindow(max_tokens=4000)` — budget-based pruning for small context models
  - `UnlimitedHistory` — no pruning, use with caution
  - `ConversationManager` ABC for custom strategies
  - `Session` persistence — save/restore conversations to `.freeagent/sessions/`
- Agent defaults to `SlidingWindow(max_turns=20)` — multi-turn works out of the box
- `conversation=None` for stateless mode (each `run()` independent, like v0.1)
- `session="name"` parameter for automatic session persistence
- Fixed `_SyncBridge` to use a persistent background event loop instead of `asyncio.run()`
  - Old code created/destroyed loops on each `run()`, breaking httpx connection pool
  - Now the loop persists for the process lifetime
- 218 unit tests (including 27 conversation tests), 5 live integration tests

### Phases 14-15: Multi-Turn Evaluation with Conversation Manager
- New eval: `evaluation/11_freeagent_conversation.py` — 6 conversations, 15 turns, 4 models
- First evaluation of gemma4:e2b (2B) with ReactEngine
- FreeAgent conversation manager: 87% accuracy (qwen3:8b, qwen3:4b), up from 78% without state
- FreeAgent beats Strands on multi-turn: 87% vs 73-80% across models
- gemma4:e2b achieves 80% via ReactEngine — matches llama3.1 accuracy at 1/4 the size
- Comparison report: `evaluation/CONVERSATION_REPORT.md`

### Phase 16: Documentation Update
- README: Added Conversation Manager section (strategies, persistence, clear/reset)
- README: Added multi-turn benchmark results with conversation manager
- README: Added gemma4:e2b to tested models table
- CHANGELOG: Updated with conversation manager, SyncBridge fix, evaluation results

### Phases 17-18: Adversarial, Component A/B, and Failure Diagnostic Evals
- Added `evaluation/12_adversarial.py` — 10 adversarial cases × 4 models testing guardrail rescue rate
- Added `evaluation/13_component_ab.py` — A/B test of 4 FreeAgent variants (default, no_skills, no_memory_tool, stripped)
- Added `evaluation/14_failure_diagnostic.py` — trace-level diagnosis of 5 previously-failing cases
- Added `evaluation/adversarial_cases.py` — adversarial case definitions
- Added `evaluation/THESIS_ANALYSIS.md` — honest assessment of framework value based on eval data
- **Finding:** Guardrails (fuzzy match, type coercion, circuit breaker) don't fire in practice — models handle adversarial inputs natively
- **Finding:** Skills improve qwen3:4b by +25% on multi-turn but overwhelm gemma4:e2b (2B)
- **Finding:** Multi-turn failures are non-deterministic (noise), not systematic framework penalty
- Updated REPORT.md, README.md with adversarial and component A/B results
