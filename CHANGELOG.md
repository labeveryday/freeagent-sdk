# Changelog

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
