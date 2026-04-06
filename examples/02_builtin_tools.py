"""
FreeAgent — Built-in Tools

Uses the built-in system_info and calculator tools.
The agent auto-detects whether your model supports native
tool calling or needs ReAct text parsing.

    ollama pull llama3.1:8b
    python examples/02_builtin_tools.py
"""

from freeagent import Agent
from freeagent.tools import system_info, calculator

agent = Agent(
    model="llama3.1:8b",
    system_prompt="You are a helpful sysadmin assistant.",
    tools=[system_info, calculator],
)

# The agent will call system_info(check="disk") automatically
print(agent.run("How much disk space do I have left?"))
print()

# The agent will call calculator(expression="...")
print(agent.run("What is 1024 * 768 / 3.14?"))
