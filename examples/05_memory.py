"""
FreeAgent — Memory Example

Memory persists between runs. The agent remembers facts,
preferences, and context without replaying conversations.

    ollama pull llama3.1:8b
    python examples/05_memory.py
"""

from freeagent import Agent, tool, Memory

# ── Standalone memory usage ──
print("=== Memory API ===")
mem = Memory()  # in-memory only (no path = no persistence)

mem.set("user.name", "Alice", source="user")
mem.set("user.units", "metric", source="user")
mem.set("user.timezone", "US/Pacific", source="user")
mem.set("last_check.disk", "2025-01-15 10:30", source="system")

print(f"Name: {mem.get('user.name')}")
print(f"All user prefs: {mem.search('user.')}")
print(f"Total entries: {len(mem)}")
print(f"System prompt section:\n{mem.to_system_prompt()}")
print()

# ── Memory with persistence ──
print("=== Persistent Memory ===")
mem2 = Memory(path="/tmp/freeagent_test_memory.json")
mem2.set("project.name", "FreeAgent SDK")
mem2.set("project.version", "0.2.0")
print(f"Saved to disk: {mem2}")
print()

# ── Agent with memory ──
print("=== Agent + Memory ===")

@tool
def remember(key: str, value: str) -> dict:
    """Save a fact to the agent's memory.

    key: The key to store under, e.g. "user.name"
    value: The value to remember
    """
    # Tools can access agent.memory through closures
    return {"saved": key, "value": value}

@tool
def recall(key: str) -> dict:
    """Recall a fact from memory.

    key: The key to look up
    """
    return {"key": key, "value": "looked up"}

agent = Agent(
    model="llama3.1:8b",
    system_prompt="You are a personal assistant with memory.",
    tools=[remember, recall],
    memory_path="/tmp/freeagent_agent_memory.json",
)

# Pre-load some memory
agent.memory.set("user.name", "Bob", source="user")
agent.memory.set("user.preference", "concise answers", source="user")

print(f"Agent: {repr(agent)}")
print(f"Memory injected into system prompt:")
print(agent.memory.to_system_prompt())
