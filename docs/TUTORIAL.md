# FreeAgent SDK — 5-Minute Tutorial

Build a local AI agent with tools, streaming, and multi-turn conversation. No API keys. No cloud. Just your machine.

## Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai) running locally

## Step 1: Install

```bash
pip install freeagent-sdk
ollama pull qwen3:4b
```

## Step 2: Verify

```bash
freeagent ask qwen3:4b "hello"
```

You should see tokens streaming in your terminal.

## Step 3: Build an Agent

Create a file called `my_agent.py`:

```python
from freeagent import Agent, tool, SlidingWindow
from freeagent.events import TokenEvent, ToolCallEvent, ToolResultEvent

# Define a tool — any Python function with type hints
@tool(name="weather")
def weather(city: str) -> dict:
    """Get current weather for a city."""
    data = {
        "tokyo": {"temp_f": 85, "condition": "sunny"},
        "paris": {"temp_f": 68, "condition": "overcast"},
    }
    key = city.lower().strip()
    for k, v in data.items():
        if k in key:
            return {**v, "city": city}
    return {"city": city, "temp_f": 70, "condition": "unknown"}

@tool(name="calculator")
def calculator(expression: str) -> dict:
    """Evaluate a math expression."""
    result = eval(expression)
    return {"expression": expression, "result": result}

# Create the agent — conversation memory is on by default
agent = Agent(
    model="qwen3:4b",
    tools=[weather, calculator],
    conversation=SlidingWindow(max_turns=10),
)
```

## Step 4: Run It

### Simple call

```python
response = agent.run("What's the weather in Tokyo?")
print(response)
# → "The weather in Tokyo is 85°F and sunny."
```

### Streaming

```python
for event in agent.run_stream("What is 42 * 17?"):
    if isinstance(event, TokenEvent):
        print(event.text, end="", flush=True)
    elif isinstance(event, ToolCallEvent):
        print(f"\n[calling {event.name}]")
```

Tokens appear as they're generated. Tool calls and results are separate events.

### Multi-turn

```python
agent.run("What's the weather in Tokyo?")
agent.run("Convert that to Celsius.")  # remembers Tokyo from the previous turn
```

The `SlidingWindow` keeps recent turns in context automatically.

### Inspect what happened

```python
print(agent.trace())      # Full event log of the last run
print(agent.metrics)       # Latency, tool calls, retries
```

## Step 5: Run the Full Tutorial

```bash
python examples/tutorial.py
```

This runs all the examples above in sequence and prints the output.

## What's Next

- **Custom skills**: Add markdown instructions in `skills/` directories — see the README
- **Memory**: The agent has a built-in memory tool for persistent markdown notes
- **MCP**: Connect to external tool servers with `freeagent.mcp.connect()`
- **Other models**: Works with any Ollama model — try `qwen3:8b`, `llama3.1:8b`, `gemma4:e2b`
- **Other providers**: vLLM, LM Studio, LocalAI via `OpenAICompatProvider` or `VLLMProvider`

See the [README](../README.md) for full documentation.
