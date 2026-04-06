# FreeAgent SDK — Implementation Plan

## Current State (what's built)

- Dual-mode execution engine (NativeEngine + ReactEngine)
- Validator with fuzzy matching, type coercion, error feedback
- Circuit breaker (loop detection, max iterations)
- Hooks system (lifecycle events)
- Memory (JSON file-backed KV store)
- **Telemetry** — `agent.metrics` baked into the agent loop, optional OTEL export
- **Multi-provider** — Ollama (default), vLLM, any OpenAI-compatible server via `Provider` protocol
- **Small-model guardrails** — thinking tag stripping, malformed JSON recovery, code fence handling in provider layer
- **Evaluation suite** — 5 evals (chat, tool calling, MCP single-turn, multi-turn, MCP multi-turn), 100-case NBA dataset, framework-agnostic JSON format
- Built-in tools: calculator, shell, system_info

## Phase 1: Foundation (unblocks everything else)

### 1.1 Rename `src/` → `freeagent/`

Fix package layout so `pip install -e .` works. Update pyproject.toml accordingly.

### 1.2 Replace urllib with httpx

Both providers currently use synchronous `urllib`. Switch to `httpx.AsyncClient` for real non-blocking I/O. httpx is already a declared dependency.

### 1.3 Sync bridge

Dedicated background thread with its own event loop. Works from scripts, notebooks, nested event loops.

```python
class _SyncBridge:
    _loop: asyncio.AbstractEventLoop | None = None
    _thread: threading.Thread | None = None

    @classmethod
    def run(cls, coro):
        if cls._loop is None:
            cls._loop = asyncio.new_event_loop()
            cls._thread = threading.Thread(
                target=cls._loop.run_forever, daemon=True
            )
            cls._thread.start()
        future = asyncio.run_coroutine_threadsafe(coro, cls._loop)
        return future.result()
```

### 1.4 Unit tests

Establish the safety net before refactoring further.

```
tests/
├── test_validator.py       # fuzzy matching, coercion, required fields
├── test_circuit_breaker.py # loop detection, max iterations
├── test_tool.py            # @tool decorator, schema generation
├── test_messages.py        # message formatting, Ollama/OpenAI conversion
├── test_memory.py          # persistence, search, system prompt injection
├── test_telemetry.py       # metrics collection, OTEL bridge
├── test_engines.py         # with mocked provider responses
├── test_agent.py           # full loop with mocked provider
└── test_providers.py       # provider protocol, response parsing, guardrails
```

## Phase 2: Small-Model Reliability (the differentiator)

These features directly address the core thesis: small/local models fail in specific ways, and the framework should catch them.

### 2.1 Tool output truncation

Small models with 4K-8K context get destroyed by large tool results. Add configurable truncation.

```python
@dataclass
class AgentConfig:
    max_tool_result_chars: int = 2000  # truncate tool output before feeding to model
    max_tool_result_strategy: str = "truncate"  # "truncate" | "summarize_head_tail"
```

In the agent loop, after tool execution:
```python
tool_output = tool_result.to_message()
if len(tool_output) > self.config.max_tool_result_chars:
    tool_output = self._truncate_tool_output(tool_output)
```

Strategy `truncate` keeps the first N chars. Strategy `summarize_head_tail` keeps first 40% + last 40% with a `[...truncated...]` marker — preserves both the start (usually headers/structure) and end (usually the actual result).

### 2.2 Context window awareness

Track approximate token count of the message list. Warn or prune when approaching the model's context limit.

```python
@dataclass
class AgentConfig:
    context_window: int = 8192  # model's context limit in tokens
    context_soft_threshold: float = 0.8  # trigger pruning at 80%
```

Token estimation: 1 token ≈ 4 chars (rough but fast, no tokenizer dependency). When messages exceed the soft threshold:
1. Drop the oldest tool result messages (keep system + recent user/assistant)
2. If still over, summarize dropped context into a single system message
3. Never drop the system prompt or the current user message

### 2.3 Model fallback chain

When the primary model fails (connection error, rate limit, or repeated validation failures), fall back to an alternative.

```python
@dataclass
class AgentConfig:
    model: str = "qwen3:8b"
    fallback_models: list[str] = field(default_factory=list)  # e.g., ["qwen3:4b", "llama3.1:latest"]
```

Fallback triggers:
- Connection error to provider → try next model
- 3 consecutive validation errors on the same tool call → try next model with simpler prompt
- Timeout → try next model

### 2.4 Tool output sanitization

Clean tool results before feeding back to the model. Small models get confused by HTML, ANSI codes, binary data, and deeply nested JSON.

```python
def _sanitize_tool_output(self, output: str) -> str:
    # Strip ANSI escape codes
    # Flatten deeply nested JSON (max depth 3)
    # Strip HTML tags if present
    # Normalize whitespace
    return cleaned
```

## Phase 3: Parallel Tool Calling

### New data model
```python
@dataclass
class ToolCall:
    id: str
    name: str
    args: dict

@dataclass
class EngineResult:
    is_tool_call: bool
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
```

### Agent loop flow
```
model → [tool_call_1, tool_call_2, tool_call_3]
         ↓            ↓              ↓
     validate      validate       validate
         ↓            ↓              ↓
     execute       execute        execute    ← asyncio.gather()
         ↓            ↓              ↓
     [result_1,   result_2,     result_3] → append all to messages → model
```

- Validate all calls independently — one bad call doesn't block the good ones
- Execute valid calls concurrently via `asyncio.gather(*executions, return_exceptions=True)`
- Circuit breaker checks each call independently
- NativeEngine returns multiple tool_calls (Ollama and OpenAI-compat both support this)
- ReactEngine stays single-call (text parsing can't reliably extract multiple actions)

## Phase 4: MCP Support

MCP tools are indistinguishable from native tools at the agent level. Adapter pattern.

### Usage
```python
from freeagent import Agent
from freeagent.mcp import connect

# Async
async with connect("npx @modelcontextprotocol/server-filesystem /tmp") as mcp:
    agent = Agent(
        model="qwen3:8b",
        tools=[calculator, *mcp.tools()],
    )
    result = await agent.arun("List files in /tmp")

# Sync
from freeagent.mcp import MCPClient
mcp = MCPClient("npx @modelcontextprotocol/server-filesystem /tmp")
mcp.connect()
agent = Agent(model="qwen3:8b", tools=mcp.tools())
agent.run("List files")
mcp.close()
```

### Internals
- `MCPTool(Tool)` subclass — overrides `execute()` to route through MCP client
- MCP JSON Schema maps directly to `ToolParam` objects
- Supports stdio (local servers) and SSE/streamable HTTP (remote servers)
- Agent, validator, circuit breaker never know the difference

### MCP + small models
- When tool count > 10, auto-generate a tool index in the system prompt to help the model pick
- Truncate MCP tool descriptions to max 100 chars in the schema (some MCP servers have verbose descriptions that eat context)

## Phase 5: Memory Upgrade

Current memory is a flat JSON KV store. Upgrade to support the patterns proven by OpenClaw.

### 5.1 Markdown-backed memory

Memory stored as human-readable markdown files in the workspace, not hidden JSON.

```
.freeagent/
├── memory.md       # long-term facts (auto-updated by agent)
├── user.md         # user preferences (user-editable)
└── logs/
    ├── 2026-04-05.md  # daily conversation log
    └── 2026-04-04.md
```

### 5.2 Hybrid search (future)

When memory grows large enough to matter (50+ entries), add SQLite-backed hybrid search:
- 70% vector similarity (via sqlite-vec or numpy cosine)
- 30% BM25 keyword matching (via SQLite FTS5)
- Chunk markdown to ~400 tokens with 80-token overlap

This is a future optimization — the current KV store is fine for early usage.

## Phase 6: Tool Policies

Simple allow/deny system for tool execution. No complex cascading chains — just enough to be safe.

```python
agent = Agent(
    model="qwen3:8b",
    tools=[shell_exec, calculator, weather],
    tool_policy={
        "shell_exec": "ask",      # prompt user before executing
        "calculator": "allow",     # always allow
        "*": "allow",              # default
    },
)
```

Three modes:
- `allow` — execute without confirmation
- `deny` — never execute, tell model it's unavailable
- `ask` — prompt user for confirmation (sync mode only, auto-deny in async)

## Phase 7: Session Persistence

Optional JSONL session store for conversation history across runs.

```python
agent = Agent(
    model="qwen3:8b",
    session_path="~/.freeagent/sessions/",
)

# Continues from last conversation
agent.run("What did we talk about yesterday?")
```

- Each session is a JSONL file (one message per line)
- `agent.sessions.list()` shows available sessions
- `agent.sessions.resume(session_id)` loads a previous session
- Auto-prune sessions older than 30 days (configurable)

## Revised Package Layout

```
freeagent/
├── __init__.py
├── agent.py
├── config.py
├── circuit_breaker.py
├── validator.py
├── messages.py
├── tool.py
├── skills.py                    # Skill loading, frontmatter parser
├── memory.py                    # Markdown-backed memory, memory tool
├── hooks.py
├── telemetry.py
├── _sync.py                     # _SyncBridge helper
├── context.py                   # Context window management, pruning
├── sanitize.py                  # Tool output sanitization
├── engines/
│   ├── __init__.py              # EngineResult, ToolCall, base class
│   ├── native.py
│   └── react.py
├── providers/
│   ├── __init__.py              # Provider protocol, ProviderResponse
│   ├── ollama.py
│   └── openai_compat.py         # vLLM, LM Studio, LocalAI, TGI
├── mcp/
│   ├── __init__.py
│   ├── client.py
│   └── adapter.py
├── skills/                      # Bundled skills (loaded by default)
│   ├── general-assistant/SKILL.md
│   └── tool-user/SKILL.md
└── tools/
    ├── __init__.py
    ├── calculator.py
    ├── shell.py
    └── system_info.py

.freeagent/memory/               # Created at runtime on first write
├── MEMORY.md                    # Auto-generated index
├── user.md                      # auto_load: true → in system prompt
├── facts.md                     # On-demand via memory tool
└── YYYY-MM-DD.md                # Daily logs

evaluation/                      # Baseline evals (framework-agnostic)
tests/                           # Unit tests
examples/                        # Usage examples
research/                        # Architecture research docs
```

## Build Order

### Done
- [x] Telemetry (baked into agent loop, optional OTEL)
- [x] Multi-provider (Ollama, vLLM, OpenAI-compat)
- [x] Provider protocol with small-model guardrails
- [x] Evaluation suite (5 evals, 100-case NBA dataset)
- [x] Skills system — markdown SKILL.md with frontmatter, bundled defaults, auto-loaded
- [x] Memory system — markdown-backed directory, single memory tool, auto_load files, daily logs
- [x] Token budget optimization — 300 tokens total framework overhead (was 702)

### Next
1. **Rename `src/` → `freeagent/`** — unblocks pip install
2. **Tool output truncation** — immediate reliability win for small models
3. **Context window awareness** — prevent context overflow on 4K-8K models
4. **Replace urllib with httpx** — unblocks real async
5. **Sync bridge** — works everywhere
6. **Unit tests** — safety net
7. **Model fallback chain** — resilience
8. **Parallel tool calling** — performance
9. **MCP adapter** — ecosystem integration
10. **Tool policies** — safety
11. **Session persistence** — conversation continuity
