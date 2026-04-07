"""
FreeAgent SDK — 5-Minute Tutorial

This tutorial walks through the core features:
  1. Simple agent.run() call
  2. Streaming with run_stream()
  3. Multi-turn conversation
  4. Trace inspection
  5. Telemetry metrics

Requires:
    pip install freeagent-sdk
    ollama pull qwen3:4b
    python examples/tutorial.py
"""

from freeagent import Agent, tool, SlidingWindow
from freeagent.events import TokenEvent, ToolCallEvent, ToolResultEvent, RunCompleteEvent

# ── Step 1: Define tools ─────────────────────────────────

@tool(name="weather")
def weather(city: str) -> dict:
    """Get current weather for a city."""
    data = {
        "tokyo": {"temp_f": 85, "condition": "sunny"},
        "london": {"temp_f": 61, "condition": "rainy"},
        "new york": {"temp_f": 72, "condition": "partly cloudy"},
        "paris": {"temp_f": 68, "condition": "overcast"},
    }
    key = city.lower().strip()
    for k, v in data.items():
        if k in key:
            return {**v, "city": city}
    return {"city": city, "temp_f": 70, "condition": "unknown"}


@tool(name="calculator")
def calculator(expression: str) -> dict:
    """Evaluate a math expression. Supports +, -, *, /, parentheses."""
    allowed = set("0123456789+-*/.() ")
    if not all(c in allowed for c in expression):
        return {"error": f"Invalid characters: {expression}"}
    result = eval(expression)  # noqa: S307
    return {"expression": expression, "result": result}


# ── Step 2: Create an agent ──────────────────────────────

agent = Agent(
    model="qwen3:4b",
    tools=[weather, calculator],
    conversation=SlidingWindow(max_turns=10),  # remembers recent turns
)

# ── Step 3: Simple run() ─────────────────────────────────

print("=" * 60)
print("  STEP 1: Simple agent.run()")
print("=" * 60)

response = agent.run("What's the weather in Tokyo?")
print(f"\n  Agent: {response}\n")

# ── Step 4: Streaming ────────────────────────────────────

print("=" * 60)
print("  STEP 2: Streaming with run_stream()")
print("=" * 60)

print("\n  Agent: ", end="", flush=True)
for event in agent.run_stream("What is 42 * 17?"):
    if isinstance(event, TokenEvent):
        print(event.text, end="", flush=True)
    elif isinstance(event, ToolCallEvent):
        print(f"\n  [calling {event.name}({event.args})]", flush=True)
        print("  Agent: ", end="", flush=True)
    elif isinstance(event, ToolResultEvent):
        print(f"\n  [result: {event.result[:80]}]", flush=True)
        print("  Agent: ", end="", flush=True)
print("\n")

# ── Step 5: Multi-turn ───────────────────────────────────

print("=" * 60)
print("  STEP 3: Multi-turn conversation")
print("=" * 60)

# The agent remembers the Tokyo weather from Step 1
response = agent.run("Convert that Tokyo temperature to Celsius.")
print(f"\n  Agent: {response}\n")

# ── Step 6: Trace inspection ─────────────────────────────

print("=" * 60)
print("  STEP 4: Trace inspection")
print("=" * 60)

trace = agent.trace()
if trace:
    print(f"\n{trace}\n")
else:
    print("\n  (No trace available)\n")

# ── Step 7: Telemetry ────────────────────────────────────

print("=" * 60)
print("  STEP 5: Telemetry metrics")
print("=" * 60)

m = agent.metrics
print(f"\n  Total runs:        {m.total_runs}")
print(f"  Total tool calls:  {m.total_tool_calls}")
print(f"  Avg latency:       {m.avg_latency_ms:.0f}ms")
if m.runs:
    last = m.runs[-1]
    print(f"  Last run tools:    {last.tools_used}")
    print(f"  Last run retries:  {last.retries}")

print("\n" + "=" * 60)
print("  You just built a local AI agent.")
print("  It runs on your machine. No API keys. No cloud.")
print("=" * 60)
