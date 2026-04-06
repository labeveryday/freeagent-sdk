"""Tests for context window management."""

from freeagent.context import estimate_tokens, estimate_messages_tokens, check_context_window
from freeagent.config import AgentConfig
from freeagent.messages import Message


class TestEstimateTokens:
    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_rough_estimation(self):
        # ~4 chars per token
        text = "a" * 400
        assert estimate_tokens(text) == 100

    def test_short_text(self):
        assert estimate_tokens("hi") == 0  # 2/4 = 0 (int division)


class TestEstimateMessagesTokens:
    def test_empty_list(self):
        assert estimate_messages_tokens([]) == 0

    def test_single_message(self):
        msgs = [Message.user("hello world")]  # 11 chars -> ~2 tokens
        assert estimate_messages_tokens(msgs) == 2

    def test_multiple_messages(self):
        msgs = [
            Message.system("a" * 100),  # 25 tokens
            Message.user("b" * 200),    # 50 tokens
        ]
        assert estimate_messages_tokens(msgs) == 75


class TestCheckContextWindow:
    def _make_config(self, window=1000, threshold=0.8):
        config = AgentConfig()
        config.context_window = window
        config.context_soft_threshold = threshold
        return config

    def test_under_threshold_no_change(self):
        config = self._make_config(window=10000)
        msgs = [
            Message.system("system prompt"),
            Message.user("question"),
        ]
        result = check_context_window(msgs, config)
        assert len(result) == 2

    def test_prunes_old_tool_results_first(self):
        config = self._make_config(window=200, threshold=0.5)
        msgs = [
            Message.system("sys"),
            Message.user("q"),
            Message.tool_result("tool1", "x" * 400),  # big tool result
            Message.assistant("thinking..."),
            Message.tool_result("tool2", "y" * 400),  # big tool result
            Message.user("follow up"),
        ]
        result = check_context_window(msgs, config)
        # Should have pruned some tool results
        assert len(result) < len(msgs)
        # System and first user message should be preserved
        assert result[0].role == "system"
        assert result[1].role == "user"

    def test_never_drops_system_prompt(self):
        config = self._make_config(window=100, threshold=0.1)
        msgs = [
            Message.system("x" * 200),
            Message.user("q"),
            Message.tool_result("t", "y" * 200),
        ]
        result = check_context_window(msgs, config)
        assert any(m.role == "system" for m in result)

    def test_never_drops_first_user_message(self):
        config = self._make_config(window=100, threshold=0.1)
        msgs = [
            Message.system("sys"),
            Message.user("q" * 200),
            Message.tool_result("t", "y" * 200),
        ]
        result = check_context_window(msgs, config)
        # First user message (index 1) should remain
        assert result[1].role == "user"

    def test_protects_last_two_messages(self):
        config = self._make_config(window=100, threshold=0.1)
        msgs = [
            Message.system("sys"),
            Message.user("q"),
            Message.tool_result("old", "x" * 200),
            Message.assistant("recent assistant"),
            Message.user("recent user"),
        ]
        result = check_context_window(msgs, config)
        # Last two messages should be preserved
        assert result[-1].content == "recent user"
        assert result[-2].content == "recent assistant"
