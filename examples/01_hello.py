"""
FreeAgent — Hello World

The simplest possible agent. No tools, just chat.
Requires: ollama running locally with a model pulled.

    ollama pull llama3.1:8b
    python examples/01_hello.py
"""

from src import Agent

agent = Agent(
    model="llama3.1:8b",
    system_prompt="You are a helpful assistant. Be concise.",
)

response = agent.run("Hello! What is Python in one sentence?")
print(response)
