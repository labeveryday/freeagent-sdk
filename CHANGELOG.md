# Changelog

## 0.2.0 (2026-04-06)

### Phase 1: Package Restructure & httpx Migration
- Renamed `src/` → `freeagent/` for proper Python package layout
- Bumped version to 0.2.0
- Replaced `urllib.request` with `httpx.AsyncClient` in both providers (Ollama, OpenAI-compat)
- Added `_SyncBridge` for safe sync→async bridging (handles Jupyter, nested loops)
- Updated `Agent.run()` to use `_SyncBridge` instead of fragile `asyncio.run()`/`ThreadPoolExecutor`
- Updated all examples to use `from freeagent import ...`
