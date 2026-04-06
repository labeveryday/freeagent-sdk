# FreeAgent SDK

**Local-first AI agent framework. Built for models that aren't perfect.**

```
pip install freeagent-sdk
```

FreeAgent is a Python framework for building AI agents that run on local models (Ollama, vLLM). Unlike Strands, LangChain, and CrewAI — which assume your model is smart — FreeAgent wraps your model in guardrails, validation, and recovery so it works reliably even with 7B/8B parameter models.

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

## Built-in Tools

```python
from freeagent import Agent
from freeagent.tools import system_info, calculator, shell_exec

agent = Agent(
    model="llama3.1:8b",
    tools=[system_info, calculator],
)
print(agent.run("How much disk space is left?"))
```

## What Makes FreeAgent Different

### Dual-Mode Execution
Auto-detects whether your model supports native tool calling (Ollama API) or needs text-based ReAct parsing. You don't configure this — it just works.

### Constrained JSON Generation
Uses Ollama's GBNF grammar support to force valid JSON output. The model literally cannot produce malformed JSON. This is the single biggest reliability win for local models.

### Retry With Error Feedback
When a tool call fails validation, FreeAgent doesn't silently retry. It tells the model exactly what went wrong: "Missing field 'city'. Schema expects: {city: string}." Small models fix this ~80% of the time.

### Circuit Breakers
Detects when a model is stuck (same tool + same args 3x = loop). Enforces iteration limits. Gracefully degrades to partial results instead of hanging forever.

### Type Coercion
Small models often return `"42"` instead of `42`. FreeAgent auto-coerces string numbers, string booleans, and other common mistakes.

### Fuzzy Tool Matching
Model called `"get_weather"` but your tool is `"weather"`? FreeAgent fuzzy-matches and suggests the correct name in the error feedback.

## Configuration

```python
agent = Agent(
    model="qwen3:8b",
    system_prompt="You are a helpful assistant.",
    tools=[my_tool],
    max_iterations=10,     # max agent loop cycles
    max_retries=3,         # retries per failed tool call
    timeout_seconds=60,    # total timeout
    temperature=0.1,       # low = more reliable tool calling
    ollama_base_url="http://localhost:11434",
)
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
