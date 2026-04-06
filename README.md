# FreeAgent SDK

**Local-first AI agent framework. Built for models that aren't perfect.**

```
pip install freeagent-sdk
```

FreeAgent is a Python framework for building AI agents that run on local models (Ollama, vLLM). Unlike Strands, LangChain, and CrewAI — which assume your model is smart — FreeAgent wraps your model in guardrails, validation, and recovery so it works reliably even with 4B-8B parameter models.

## Hello World

```python
from freeagent import Agent

agent = Agent(model="llama3.1:8b")
print(agent.run("What is Python?"))
```

## Custom Tools

```python
from freeagent import Agent, tool

@tool
def weather(city: str) -> dict:
    """Get current weather for a city."""
    return {"city": city, "temp": 72, "condition": "sunny"}

agent = Agent(
    model="qwen3:8b",
    system_prompt="You are a weather assistant.",
    tools=[weather],
)

print(agent.run("What's the weather in Portland?"))
```

## Skills (Markdown Prompt Extensions)

Skills are markdown directories with `SKILL.md` files containing frontmatter:

```markdown
---
name: nba-analyst
description: Basketball statistics expert
tools: [search, calculator]
---

You are an NBA analyst. Always cite your sources.
When comparing players, use per-game averages.
```

```python
agent = Agent(
    model="qwen3:8b",
    tools=[search, calculator],
    skills=["./my-skills"],   # directory of skill folders
)
```

Bundled skills (general-assistant, tool-user) load automatically. User skills extend them — duplicate names override.

## Memory (Markdown-Backed)

Every agent has built-in memory stored as human-readable `.md` files in `.freeagent/memory/`:

```
.freeagent/memory/
├── MEMORY.md          # Index of all memory files
├── user.md            # User preferences (auto_load: true → in system prompt)
├── facts.md           # Accumulated facts
└── 2026-04-05.md      # Daily log
```

The agent gets a single `memory` tool with actions: `read`, `write`, `append`, `search`, `list`. Only the index and `auto_load` files go into the system prompt — everything else is pulled on demand. Token-efficient for small models.

```python
# Programmatic access
agent.memory.set("color", "blue")
agent.memory.get("color")  # "blue"
agent.memory.log("User asked about weather")
```

## Multi-Provider Support

```python
from freeagent import Agent, VLLMProvider, OpenAICompatProvider

# vLLM
provider = VLLMProvider(model="qwen3-8b", base_url="http://localhost:8000")
agent = Agent(model="qwen3-8b", provider=provider, tools=[my_tool])

# Any OpenAI-compatible server (LM Studio, LocalAI, TGI)
provider = OpenAICompatProvider(
    model="llama3.1:8b",
    base_url="http://localhost:1234",
    api_key="lm-studio",
)
agent = Agent(model="llama3.1:8b", provider=provider, tools=[my_tool])
```

All providers implement `chat()`, `chat_with_tools()`, `chat_with_format()`. Small-model guardrails (thinking tag stripping, malformed JSON recovery, code fence handling) are built into the OpenAI-compat provider.

## Telemetry

Every agent has built-in telemetry — no setup needed:

```python
agent.run("What's the weather?")

print(agent.metrics)               # quick summary
print(agent.metrics.last_run)      # last run details
print(agent.metrics.tool_stats())  # per-tool breakdown
agent.metrics.to_json("m.json")   # export
```

Optional OpenTelemetry: `pip install freeagent-sdk[otel]` — traces and metrics flow automatically.

## MCP Support

Connect to MCP servers and use their tools:

```python
from freeagent import Agent
from freeagent.mcp import connect

async with connect("npx -y @modelcontextprotocol/server-filesystem /tmp") as tools:
    agent = Agent(model="qwen3:8b", tools=tools)
    result = await agent.arun("List files in /tmp")
```

Supports stdio and streamable HTTP transports. Install with: `pip install freeagent-sdk[mcp]`

## Small-Model Reliability Features

### Tool Output Sanitization
Strips ANSI codes, HTML tags, normalizes whitespace, and flattens deeply nested JSON before feeding results back to the model.

### Context Window Management
Estimates token usage and prunes old tool results when approaching the context limit. Never drops the system prompt or current user message.

### Model Fallback
If the primary model is unreachable, automatically tries fallback models:

```python
agent = Agent(
    model="qwen3:8b",
    fallback_models=["llama3.1:8b", "phi3:mini"],
)
```

### Parallel Tool Calling
When the model requests multiple tool calls, they execute concurrently via `asyncio.gather()`. One bad call doesn't block the others.

## What Makes FreeAgent Different

- **Dual-Mode Execution** — auto-detects native tool calling vs text-based ReAct
- **Constrained JSON** — GBNF grammar forces valid JSON output
- **Retry With Error Feedback** — tells the model exactly what went wrong
- **Circuit Breakers** — detects loops, enforces limits, degrades gracefully
- **Type Coercion** — auto-fixes `"42"` → `42`, `"true"` → `True`
- **Fuzzy Tool Matching** — suggests correct tool names on misspellings
- **~300 token overhead** — skills + memory tool fit in 4K context models

## Configuration

```python
from freeagent import Agent, AgentConfig

config = AgentConfig(
    max_iterations=10,
    max_retries=3,
    timeout_seconds=60,
    temperature=0.1,
    max_tool_result_chars=2000,
    context_window=8192,
    context_soft_threshold=0.8,
    fallback_models=["llama3.1:8b"],
)

agent = Agent(model="qwen3:8b", tools=[my_tool], config=config)
```

## Tested Models

| Model | Mode | Reliability |
|-------|------|------------|
| Qwen3 14B | Native | Excellent |
| Qwen3 8B | Native | Very Good |
| Llama 3.1 8B | Native | Good |
| Mistral 7B | ReAct | Good |
| Phi-3 | ReAct | Fair |

## Requirements

- Python 3.10+
- Ollama running locally (`ollama serve`)
- A model pulled (`ollama pull llama3.1:8b`)

## License

MIT
