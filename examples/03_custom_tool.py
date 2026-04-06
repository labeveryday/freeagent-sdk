"""
FreeAgent — Custom Tool

Define your own tools with the @tool decorator.
Just write a function with type hints and a docstring.
FreeAgent builds the JSON schema automatically.

    ollama pull qwen3:8b
    python examples/03_custom_tool.py
"""

from freeagent import Agent, tool


@tool
def lookup_user(username: str) -> dict:
    """Look up a user by their username and return their profile.

    username: The username to look up
    """
    # In a real app, this would hit a database
    users = {
        "alice": {"name": "Alice Chen", "role": "engineer", "team": "platform"},
        "bob": {"name": "Bob Smith", "role": "designer", "team": "product"},
        "carol": {"name": "Carol Jones", "role": "manager", "team": "platform"},
    }
    user = users.get(username.lower())
    if user:
        return {"found": True, **user}
    return {"found": False, "error": f"No user '{username}'"}


@tool
def list_team(team: str) -> dict:
    """List all members of a team.

    team: The team name, e.g. "platform" or "product"
    """
    teams = {
        "platform": ["alice", "carol"],
        "product": ["bob"],
    }
    members = teams.get(team.lower(), [])
    return {"team": team, "members": members, "count": len(members)}


agent = Agent(
    model="qwen3:8b",
    system_prompt=(
        "You are an HR assistant. Use the tools to look up "
        "users and teams. Be concise and friendly."
    ),
    tools=[lookup_user, list_team],
    max_retries=3,
    timeout_seconds=60,
)

print(agent.run("Who is on the platform team?"))
print()
print(agent.run("What does alice do?"))
