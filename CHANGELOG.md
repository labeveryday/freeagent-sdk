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
