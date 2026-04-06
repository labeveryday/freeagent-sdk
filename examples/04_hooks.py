"""
FreeAgent — Hooks Example

Hooks let you observe and modify agent behavior at every
lifecycle event without subclassing.

    ollama pull llama3.1:8b
    python examples/04_hooks.py
"""

from freeagent import Agent, tool, log_hook, cost_hook

@tool
def weather(city: str) -> dict:
    """Get current weather for a city.

    city: The city name
    """
    temps = {"portland": 58, "seattle": 52, "new york": 71}
    return {
        "city": city,
        "temp_f": temps.get(city.lower(), 65),
        "condition": "cloudy",
    }

agent = Agent(
    model="llama3.1:8b",
    system_prompt="You are a weather assistant.",
    tools=[weather],
)

# ── Hook 1: Logging (pre-built) ──
logger = log_hook(verbose=True)
agent.on("before_run", logger)
agent.on("before_tool", logger)
agent.on("after_tool", logger)
agent.on("after_run", logger)

# ── Hook 2: Cost tracking (pre-built) ──
track, stats = cost_hook()
agent.on("before_tool", track)
agent.on("on_error", track)

# ── Hook 3: Custom hook as decorator ──
@agent.on("after_tool")
def save_to_memory(ctx):
    """Automatically remember weather checks."""
    if ctx.result and ctx.result.success:
        data = ctx.result.data
        agent.memory.set(
            f"weather.{ctx.args.get('city', 'unknown')}",
            data,
            source="tool",
        )

# ── Hook 4: Guard hook ──
@agent.on("before_tool")
def block_if_cached(ctx):
    """Skip tool call if we already have recent data."""
    cached = agent.memory.get(f"weather.{ctx.args.get('city', '')}")
    if cached:
        print(f"  [cache hit for {ctx.args.get('city')}]")
        # ctx.skip = True  # uncomment to actually skip

# Run it
print(agent.run("What's the weather in Portland?"))
print(f"\nTool call stats: {stats()}")
print(f"Memory: {agent.memory.all()}")
