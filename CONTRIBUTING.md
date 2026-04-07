# Contributing to FreeAgent SDK

## Setup

```bash
git clone https://github.com/freeagent-sdk/freeagent.git
cd freeagent
pip install -e ".[dev]"
```

## Running Tests

```bash
# Unit tests (fast, no external deps)
pytest tests/ -q --ignore=tests/integration -m "not integration"

# Integration tests (requires Ollama running locally)
pytest tests/integration/ -v -m integration
```

## Running Evaluations

Evals test against real Ollama models. They're slow (10-30 min each).

```bash
# Requires: ollama pull qwen3:8b qwen3:4b llama3.1:latest gemma4:e2b
cd evaluation
python 15_autotune_ab.py      # auto-tune verification
python 16_streaming_latency.py # streaming benchmark
python 17_trace_completeness.py # trace API verification
```

Results are saved as JSON in `evaluation/`.

## Adding a Skill

1. Create a directory under `src/skills/` (bundled) or your project's `skills/` directory
2. Add a `SKILL.md` file with YAML frontmatter:

```markdown
---
name: my-skill
description: What this skill does
tools: [tool1, tool2]
---

Instructions for the model when this skill is active.
```

3. Pass to the agent: `Agent(skills=["./skills"])`

## Code Style

- No PyYAML — use the built-in frontmatter parser
- Tool errors are values (`ToolResult.fail()`), not exceptions
- Hooks silently swallow exceptions
- Token budget matters — every token added to system prompt costs context on small models

## Project Structure

```
freeagent/          # Core package
├── agent.py        # Agent class
├── providers/      # Ollama, vLLM, OpenAI-compat
├── engines/        # NativeEngine, ReactEngine
├── events.py       # Streaming events
├── memory.py       # Markdown-backed memory
├── skills.py       # Skill loading
└── telemetry.py    # Metrics + trace

evaluation/         # Eval scripts + results (don't modify 01-14)
examples/           # Runnable examples
tests/              # Unit + integration tests
```
