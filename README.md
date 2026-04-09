# FreeAgent SDK

[![PyPI version](https://img.shields.io/pypi/v/freeagent-sdk.svg?color=1c5d99&labelColor=222)](https://pypi.org/project/freeagent-sdk/)
[![Python versions](https://img.shields.io/pypi/pyversions/freeagent-sdk.svg?color=639fab&labelColor=222)](https://pypi.org/project/freeagent-sdk/)
[![License: MIT](https://img.shields.io/badge/License-MIT-bbcde5.svg?labelColor=222)](LICENSE)
[![Tests](https://github.com/labeveryday/freeagent-sdk/actions/workflows/tests.yml/badge.svg)](https://github.com/labeveryday/freeagent-sdk/actions/workflows/tests.yml)
[![Docs](https://img.shields.io/badge/docs-freeagentsdk.com-1c5d99?labelColor=222)](https://freeagentsdk.com)
[![Downloads](https://img.shields.io/pypi/dm/freeagent-sdk.svg?color=639fab&labelColor=222)](https://pypi.org/project/freeagent-sdk/)

**A clean local agent SDK for Ollama, vLLM, and OpenAI-compatible servers.**

Streaming. Multi-turn out of the box. Markdown skills and memory. Built-in telemetry. Single dependency.

```
pip install freeagent-sdk
```

**Links:** [Documentation](https://freeagentsdk.com) · [Tutorial](docs/TUTORIAL.md) · [Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md) · [Examples](examples/) · [Evaluation data](evaluation/)

## Why FreeAgent

- **Local-first**: works with Ollama and vLLM — your data never leaves your machine
- **Streaming everywhere**: token-level streaming with semantic events
- **Multi-turn that just works**: conversation state managed automatically with pluggable strategies
- **Markdown is first-class**: skills and memory are human-readable `.md` files with frontmatter
- **Zero-config**: auto-detects model size and tunes defaults — works on 2B and 70B alike
- **Inspectable**: `agent.trace()` shows exactly what happened
- **Fast**: actually 2% faster than raw Ollama API (HTTP connection reuse)
- **Honest**: real benchmark data in this README, not marketing

## Quick Start

### CLI

```bash
# One-shot query with streaming
freeagent ask qwen3:8b "What's the capital of France?"

# Interactive chat
freeagent chat qwen3:8b

# List available models
freeagent models
```

### Python

```python
from freeagent import Agent

agent = Agent(model="qwen3:8b")
print(agent.run("What is Python?"))
```

## Streaming

Real token-by-token streaming, even for tool-using agents:

```python
from freeagent import Agent
from freeagent.events import TokenEvent, ToolCallEvent, ToolResultEvent

agent = Agent(model="qwen3:8b", tools=[weather])

for event in agent.run_stream("What's the weather in Tokyo?"):
    if isinstance(event, TokenEvent):
        print(event.text, end="", flush=True)
    elif isinstance(event, ToolCallEvent):
        print(f"\n[Calling {event.name}...]")
    elif isinstance(event, ToolResultEvent):
        print(f"[{event.name} -> {'ok' if event.success else 'fail'} ({event.duration_ms:.0f}ms)]")
```

Async version: `async for event in agent.arun_stream("query"):`

Event types: `RunStartEvent`, `TokenEvent`, `ToolCallEvent`, `ToolResultEvent`, `ValidationErrorEvent`, `RetryEvent`, `IterationEvent`, `RunCompleteEvent`.

## Custom Tools

```python
from freeagent import Agent, tool

@tool
def weather(city: str) -> dict:
    """Get current weather for a city."""
    return {"city": city, "temp": 72, "condition": "sunny"}

agent = Agent(model="qwen3:8b", tools=[weather])
print(agent.run("What's the weather in Portland?"))
```

## Multi-Turn Conversations

```python
agent = Agent(model="qwen3:8b", tools=[weather])
agent.run("What's the weather in Tokyo?")
agent.run("Convert that to Celsius")  # remembers Tokyo was 85°F
```

### Strategies

```python
from freeagent import Agent, SlidingWindow, TokenWindow

# Default: SlidingWindow(max_turns=20)
agent = Agent(model="qwen3:8b")

# Token-based budget (better for small context models)
agent = Agent(model="qwen3:4b", conversation=TokenWindow(max_tokens=3000))

# Stateless mode (each run independent)
agent = Agent(model="qwen3:8b", conversation=None)
```

### Session Persistence

```python
agent = Agent(model="qwen3:8b", session="my-chat")
agent.run("Hello!")
# Later, in a new process:
agent = Agent(model="qwen3:8b", session="my-chat")  # restores conversation
```

## Inspecting Runs

Every run is fully traced. See exactly what happened:

```python
agent.run("What's 347 * 29?")

# One-line summary
print(agent.last_run.summary())
# Run 1: qwen3:8b (native) 2300ms, 2 iters, 1 tools

# Full timeline
print(agent.trace())
# +     0ms  model_call_start     iter=0
# +   800ms  tool_call            calc(expression='347*29')
# +   802ms  tool_result          calc -> ok (2ms)
# +   803ms  model_call_start     iter=1

# Markdown report
print(agent.last_run.to_markdown())
```

## Model-Aware Defaults

FreeAgent auto-detects model capabilities from Ollama and tunes itself:

```python
# Auto-tuned: detects 2B model, strips skills and memory tool
agent = Agent(model="gemma4:e2b")

# Auto-tuned: detects 8B model, keeps full defaults
agent = Agent(model="qwen3:8b")

# Override auto-tuning
agent = Agent(model="gemma4:e2b", bundled_skills=True, memory_tool=True)

# Disable auto-tuning entirely
agent = Agent(model="qwen3:8b", auto_tune=False)
```

Access detected info: `agent.model_info.parameter_count`, `agent.model_info.context_length`, `agent.model_info.capabilities`.

## Skills (Markdown Prompt Extensions)

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
agent = Agent(model="qwen3:8b", tools=[search, calculator], skills=["./my-skills"])
```

Bundled skills load automatically. User skills extend them — duplicate names override.

## Memory (Markdown-Backed)

Every agent has built-in memory stored as human-readable `.md` files:

```
.freeagent/memory/
├── MEMORY.md          # Index
├── user.md            # auto_load: true → in system prompt
├── facts.md           # Accumulated facts
└── 2026-04-05.md      # Daily log
```

The agent gets a `memory` tool with actions: `read`, `write`, `append`, `search`, `list`. Only the index and `auto_load` files go into the system prompt — everything else is on demand.

## Multi-Provider Support

```python
from freeagent import Agent, VLLMProvider, OpenAICompatProvider

# vLLM
provider = VLLMProvider(model="qwen3-8b")
agent = Agent(model="qwen3-8b", provider=provider, tools=[my_tool])

# Any OpenAI-compatible server
provider = OpenAICompatProvider(model="llama3.1:8b", base_url="http://localhost:1234")
agent = Agent(model="llama3.1:8b", provider=provider, tools=[my_tool])
```

## Telemetry

Built-in, always on:

```python
agent.run("What's the weather?")
print(agent.metrics)               # quick summary
print(agent.metrics.tool_stats())  # per-tool breakdown
agent.metrics.to_json("m.json")   # export
```

Optional OpenTelemetry: `pip install freeagent-sdk[otel]`

## MCP Support

```python
from freeagent.mcp import connect

async with connect("npx -y @modelcontextprotocol/server-filesystem /tmp") as tools:
    agent = Agent(model="qwen3:8b", tools=tools)
    result = await agent.arun("List files in /tmp")
```

Install with: `pip install freeagent-sdk[mcp]`

## Real Performance

Tested against the raw Ollama API with the same eval suite (100+ cases, 4 models). Full data in `evaluation/`.

### Multi-Turn Conversations (6 conversations, 15 turns)

| Model | Raw Ollama | FreeAgent |
|-------|-----------|-----------|
| qwen3:8b | 93% | **87%** |
| qwen3:4b | 93% | **87%** |
| llama3.1:8b | 87% | **80%** |
| gemma4:e2b (2B) | N/A | **80%** |

### Tool Calling Accuracy (8 cases)

| Model | Raw Ollama | FreeAgent |
|-------|-----------|-----------|
| qwen3:8b | 75% | 75% |
| qwen3:4b | 100% | 88% |
| llama3.1:8b | 62% | **75% (+13%)** |

### Streaming Latency (median of 3 runs)

| Model | Chat TTFT | Chat Total | Tool TTFT | Tool Total |
|-------|----------|-----------|----------|-----------|
| qwen3:8b | 12.8s | 13.9s | 5.2s | 10.0s |
| qwen3:4b | 14.7s | 14.5s | 28.2s | 31.6s |
| llama3.1:8b | 1.5s | 1.4s | 1.8s | 2.1s |
| gemma4:e2b | 4.7s | 5.1s | 8.2s | 12.1s |

TTFT ≈ total for chat (generation is fast once started). Tool TTFT includes tool execution round-trip.

### Auto-Tune (v0.3.1)

| Model | auto_tune=True | All On | Manual Strip | Delta vs All On |
|-------|---------------|--------|-------------|----------------|
| qwen3:8b | 91% | 91% | — | +0% |
| qwen3:4b | 91% | 91% | — | +0% |
| llama3.1:8b | 100% | 100% | — | +0% |
| gemma4:e2b | **91%** | 55% | 73% | **+36%** |

Auto-tune detects gemma4:e2b as a small model and strips bundled skills + memory tool. This improves accuracy from 55% → 91%.

### Honest Caveats

- **Guardrails rarely fire**: 0/40 real rescues in adversarial testing. Modern models handle fuzzy names and type coercion natively.
- **Multi-turn gap to raw Ollama is noise**: 87% vs 93% — re-running failures produces passes. Non-deterministic.
- **Skills help qwen3:4b but hurt gemma4:e2b** — fixed by auto-tune, which strips them for small models.
- **Streaming TTFT ≈ total time** on small models: generation is fast, model thinking dominates latency.

Full analysis: `evaluation/THESIS_ANALYSIS.md`

## Tested Models

| Model | Size | Mode | Reliability |
|-------|------|------|-------------|
| Qwen3 8B | 8.2B | Native | Very Good |
| Qwen3 4B | 4.0B | Native | Good (best with skills) |
| Llama 3.1 8B | 8.0B | Native | Good |
| Gemma4 E2B | 5.1B | Native | Good (auto-tuned) |

## Requirements

- Python 3.10+
- Ollama running locally (`ollama serve`)
- A model pulled (`ollama pull qwen3:8b`)

## Documentation

- **[Tutorial](docs/TUTORIAL.md)** — 5-minute walkthrough from install to working agent
- **[Website](https://labeveryday.github.io/free-agent-sdk/)** — landing page and feature overview
- **[Examples](examples/)** — runnable scripts covering tools, memory, hooks, MCP
- **[Evaluation data](evaluation/)** — benchmark results and thesis analysis
- **[Changelog](CHANGELOG.md)** — release history
- **[Contributing](CONTRIBUTING.md)** — how to run tests, add skills, submit PRs

## License

MIT
