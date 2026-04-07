"""Tests for CLI argument parsing and command dispatch."""

import pytest
from unittest.mock import patch, MagicMock
from io import StringIO

from freeagent.cli import main


def test_version(capsys):
    main(["version"])
    out = capsys.readouterr().out
    assert "freeagent" in out
    assert "0." in out  # version number


def test_no_args(capsys):
    """No args should print help."""
    main([])
    out = capsys.readouterr().out
    assert "usage" in out.lower() or "freeagent" in out.lower()


def test_ask_parses():
    """Verify ask command parses model and prompt correctly."""
    with patch("freeagent.cli._cmd_ask") as mock:
        main(["ask", "qwen3:8b", "hello world"])
        args = mock.call_args[0][0]
        assert args.model == "qwen3:8b"
        assert args.prompt == "hello world"
        assert args.no_stream is False


def test_ask_no_stream():
    with patch("freeagent.cli._cmd_ask") as mock:
        main(["ask", "qwen3:8b", "hello", "--no-stream"])
        args = mock.call_args[0][0]
        assert args.no_stream is True


def test_ask_with_system():
    with patch("freeagent.cli._cmd_ask") as mock:
        main(["ask", "qwen3:8b", "hello", "--system", "Be brief."])
        args = mock.call_args[0][0]
        assert args.system == "Be brief."


def test_chat_parses():
    with patch("freeagent.cli._cmd_chat") as mock:
        main(["chat", "qwen3:8b"])
        args = mock.call_args[0][0]
        assert args.model == "qwen3:8b"
        assert args.session is None


def test_chat_with_session():
    with patch("freeagent.cli._cmd_chat") as mock:
        main(["chat", "qwen3:8b", "--session", "my-chat"])
        args = mock.call_args[0][0]
        assert args.session == "my-chat"


def test_models_dispatches():
    with patch("freeagent.cli._cmd_models") as mock:
        main(["models"])
        mock.assert_called_once()


def test_trace_message(capsys):
    main(["trace"])
    out = capsys.readouterr().out
    assert "trace" in out.lower()
