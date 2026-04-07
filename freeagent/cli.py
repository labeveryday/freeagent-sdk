"""
CLI — freeagent from the terminal.

    freeagent ask qwen3:8b "What's 2+2?"
    freeagent chat qwen3:8b
    freeagent models
    freeagent version
"""

from __future__ import annotations

import argparse
import sys

from . import __version__


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        prog="freeagent",
        description="FreeAgent SDK — local-first AI agent framework",
    )
    sub = parser.add_subparsers(dest="cmd")

    # ask: one-shot query
    p_ask = sub.add_parser("ask", help="Ask a one-shot question")
    p_ask.add_argument("model", help="Model name (e.g. qwen3:8b)")
    p_ask.add_argument("prompt", help="The question to ask")
    p_ask.add_argument("--no-stream", action="store_true", help="Disable streaming")
    p_ask.add_argument("--system", help="Custom system prompt")

    # chat: interactive REPL
    p_chat = sub.add_parser("chat", help="Interactive chat session")
    p_chat.add_argument("model", help="Model name (e.g. qwen3:8b)")
    p_chat.add_argument("--session", help="Persistent session name")
    p_chat.add_argument("--system", help="Custom system prompt")

    # trace: show last run trace
    sub.add_parser("trace", help="Show last run trace (use after chat)")

    # models: list available
    sub.add_parser("models", help="List available Ollama models")

    # version
    sub.add_parser("version", help="Show version")

    args = parser.parse_args(argv)

    if args.cmd == "ask":
        _cmd_ask(args)
    elif args.cmd == "chat":
        _cmd_chat(args)
    elif args.cmd == "models":
        _cmd_models()
    elif args.cmd == "version":
        _cmd_version()
    elif args.cmd == "trace":
        print("Use /trace within a chat session, or inspect agent.trace() in Python.")
    else:
        parser.print_help()


def _cmd_ask(args):
    """One-shot query with streaming."""
    from .agent import Agent
    from .events import TokenEvent, RunCompleteEvent

    kwargs = {}
    if args.system:
        kwargs["system_prompt"] = args.system

    agent = Agent(model=args.model, conversation=None, **kwargs)

    if args.no_stream:
        result = agent.run(args.prompt)
        print(result)
    else:
        for event in agent.run_stream(args.prompt):
            if isinstance(event, TokenEvent):
                print(event.text, end="", flush=True)
            elif isinstance(event, RunCompleteEvent):
                print()  # newline after streaming


def _cmd_chat(args):
    """Interactive REPL with conversation."""
    from .agent import Agent
    from .conversation import SlidingWindow
    from .events import TokenEvent, RunCompleteEvent

    kwargs = {}
    if args.system:
        kwargs["system_prompt"] = args.system

    agent = Agent(
        model=args.model,
        conversation=SlidingWindow(max_turns=50),
        session=args.session,
        **kwargs,
    )

    info = agent.model_info
    if info:
        print(f"Model: {args.model} ({info.parameter_size}, {info.quantization})")
    else:
        print(f"Model: {args.model}")
    print("Type /exit to quit, /clear to clear history, /trace to show last trace.\n")

    try:
        _setup_readline()
    except Exception:
        pass

    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue

        if user_input == "/exit":
            print("Bye!")
            break
        elif user_input == "/clear":
            if agent.conversation:
                agent.conversation.clear()
            print("Conversation cleared.")
            continue
        elif user_input == "/trace":
            print(agent.trace())
            continue
        elif user_input == "/save":
            if agent._session:
                agent._session.save(agent.conversation)
                print("Session saved.")
            else:
                print("No session configured. Use --session <name>.")
            continue

        for event in agent.run_stream(user_input):
            if isinstance(event, TokenEvent):
                print(event.text, end="", flush=True)
            elif isinstance(event, RunCompleteEvent):
                print()  # newline


def _cmd_models():
    """List available Ollama models."""
    import httpx

    try:
        resp = httpx.get("http://localhost:11434/api/tags", timeout=5)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, httpx.ConnectError) as e:
        print(f"Cannot connect to Ollama: {e}")
        sys.exit(1)

    models = data.get("models", [])
    if not models:
        print("No models found.")
        return

    print(f"{'Name':<30} {'Size':<10} {'Modified'}")
    print("-" * 60)
    for m in models:
        name = m.get("name", "?")
        size_bytes = m.get("size", 0)
        size_gb = f"{size_bytes / 1e9:.1f}GB"
        modified = m.get("modified_at", "?")[:10]
        print(f"{name:<30} {size_gb:<10} {modified}")


def _cmd_version():
    print(f"freeagent {__version__}")


def _setup_readline():
    """Set up readline for history in chat mode."""
    try:
        import readline  # noqa: F401
    except ImportError:
        pass


if __name__ == "__main__":
    main()
