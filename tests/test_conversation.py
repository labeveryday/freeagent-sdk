"""Tests for conversation management strategies."""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from freeagent.conversation import (
    SlidingWindow,
    TokenWindow,
    UnlimitedHistory,
    Session,
    _msg_to_dict,
    _msg_from_dict,
)
from freeagent.messages import Message


# ── SlidingWindow ─────────────────────────────────────────

class TestSlidingWindow:
    def test_first_turn(self):
        sw = SlidingWindow(max_turns=5)
        msgs = sw.prepare("You are helpful.", "Hello")
        assert len(msgs) == 2
        assert msgs[0].role == "system"
        assert msgs[1].role == "user"
        assert msgs[1].content == "Hello"

    def test_multi_turn_accumulates(self):
        sw = SlidingWindow(max_turns=5)

        # Turn 1
        msgs = sw.prepare("system", "Turn 1")
        msgs.append(Message.assistant("Response 1"))
        sw.commit(msgs)

        # Turn 2
        msgs = sw.prepare("system", "Turn 2")
        assert len(msgs) == 4  # system + user1 + asst1 + user2
        assert msgs[1].content == "Turn 1"
        assert msgs[2].content == "Response 1"
        assert msgs[3].content == "Turn 2"

    def test_system_prompt_refreshes(self):
        sw = SlidingWindow(max_turns=5)

        msgs = sw.prepare("system v1", "Hello")
        msgs.append(Message.assistant("Hi"))
        sw.commit(msgs)

        msgs = sw.prepare("system v2", "Again")
        assert msgs[0].content == "system v2"  # refreshed

    def test_prune_at_max_turns(self):
        sw = SlidingWindow(max_turns=2)

        # Turn 1
        msgs = sw.prepare("sys", "Turn 1")
        msgs.append(Message.assistant("Resp 1"))
        sw.commit(msgs)

        # Turn 2
        msgs = sw.prepare("sys", "Turn 2")
        msgs.append(Message.assistant("Resp 2"))
        sw.commit(msgs)

        # Turn 3 — should prune turn 1
        msgs = sw.prepare("sys", "Turn 3")
        msgs.append(Message.assistant("Resp 3"))
        sw.commit(msgs)

        assert sw.turn_count == 2
        # History should NOT contain Turn 1
        msgs = sw.prepare("sys", "Turn 4")
        contents = [m.content for m in msgs]
        assert "Turn 1" not in contents
        assert "Turn 2" in contents or "Turn 3" in contents

    def test_tool_calls_kept_as_pairs(self):
        sw = SlidingWindow(max_turns=5)

        msgs = sw.prepare("sys", "Use weather tool")
        msgs.append(Message.assistant("Calling weather...", tool_calls=[{
            "function": {"name": "weather", "arguments": {"city": "NYC"}}
        }]))
        msgs.append(Message.tool_result("weather", '{"temp": 72}'))
        msgs.append(Message.assistant("It's 72F in NYC."))
        sw.commit(msgs)

        msgs = sw.prepare("sys", "Next question")
        # Should have: user1, assistant_tool, tool_result, assistant_answer, user2
        assert any(m.role == "tool" for m in msgs)
        assert any(m.tool_calls for m in msgs if m.role == "assistant")

    def test_clear(self):
        sw = SlidingWindow(max_turns=5)

        msgs = sw.prepare("sys", "Hello")
        msgs.append(Message.assistant("Hi"))
        sw.commit(msgs)
        assert sw.turn_count == 1

        sw.clear()
        assert sw.turn_count == 0

        msgs = sw.prepare("sys", "Fresh start")
        assert len(msgs) == 2  # system + user only

    def test_turn_count(self):
        sw = SlidingWindow(max_turns=10)
        assert sw.turn_count == 0

        for i in range(5):
            msgs = sw.prepare("sys", f"Turn {i}")
            msgs.append(Message.assistant(f"Resp {i}"))
            sw.commit(msgs)

        assert sw.turn_count == 5


# ── TokenWindow ───────────────────────────────────────────

class TestTokenWindow:
    def test_first_turn(self):
        tw = TokenWindow(max_tokens=1000)
        msgs = tw.prepare("system", "Hello")
        assert len(msgs) == 2
        assert msgs[0].role == "system"

    def test_multi_turn(self):
        tw = TokenWindow(max_tokens=5000)

        msgs = tw.prepare("sys", "Turn 1")
        msgs.append(Message.assistant("Response 1"))
        tw.commit(msgs)

        msgs = tw.prepare("sys", "Turn 2")
        assert len(msgs) == 4  # system + user1 + asst1 + user2

    def test_drops_old_when_over_budget(self):
        tw = TokenWindow(max_tokens=100)  # very tight

        # Fill with long messages
        msgs = tw.prepare("sys", "Turn 1")
        msgs.append(Message.assistant("A" * 200))  # ~50 tokens
        tw.commit(msgs)

        msgs = tw.prepare("sys", "Turn 2")
        msgs.append(Message.assistant("B" * 200))
        tw.commit(msgs)

        # Prepare turn 3 — old messages should be dropped
        msgs = tw.prepare("sys", "Turn 3")
        # With 100 token budget, can't fit much history
        # Should still have system + user at minimum
        assert msgs[0].role == "system"
        assert msgs[-1].content == "Turn 3"

    def test_recent_messages_preferred(self):
        tw = TokenWindow(max_tokens=200)

        for i in range(10):
            msgs = tw.prepare("sys", f"T{i}")
            msgs.append(Message.assistant(f"R{i}"))
            tw.commit(msgs)

        msgs = tw.prepare("sys", "Latest")
        contents = [m.content for m in msgs if m.role == "user"]
        # Most recent turns should be present, old ones dropped
        assert "Latest" in contents

    def test_turn_count(self):
        tw = TokenWindow(max_tokens=5000)
        assert tw.turn_count == 0

        msgs = tw.prepare("sys", "Hello")
        msgs.append(Message.assistant("Hi"))
        tw.commit(msgs)
        assert tw.turn_count == 1


# ── UnlimitedHistory ──────────────────────────────────────

class TestUnlimitedHistory:
    def test_keeps_everything(self):
        uh = UnlimitedHistory()

        for i in range(50):
            msgs = uh.prepare("sys", f"Turn {i}")
            msgs.append(Message.assistant(f"Resp {i}"))
            uh.commit(msgs)

        assert uh.turn_count == 50

        msgs = uh.prepare("sys", "Turn 50")
        # Should have system + 100 history messages + new user
        assert len(msgs) > 100


# ── Serialization ─────────────────────────────────────────

class TestSerialization:
    def test_msg_roundtrip(self):
        original = Message.assistant("Hello", tool_calls=[{
            "function": {"name": "test", "arguments": {"x": 1}}
        }])
        d = _msg_to_dict(original)
        restored = _msg_from_dict(d)
        assert restored.role == original.role
        assert restored.content == original.content
        assert restored.tool_calls == original.tool_calls

    def test_tool_result_roundtrip(self):
        original = Message.tool_result("weather", '{"temp": 72}')
        d = _msg_to_dict(original)
        restored = _msg_from_dict(d)
        assert restored.role == "tool"
        assert restored.name == "weather"
        assert restored.content == '{"temp": 72}'

    def test_sliding_window_to_dict(self):
        sw = SlidingWindow(max_turns=10)
        msgs = sw.prepare("sys", "Hello")
        msgs.append(Message.assistant("Hi"))
        sw.commit(msgs)

        data = sw.to_dict()
        assert data["type"] == "SlidingWindow"
        assert data["max_turns"] == 10
        assert len(data["history"]) == 2  # user + assistant

    def test_sliding_window_from_dict(self):
        sw = SlidingWindow(max_turns=10)
        msgs = sw.prepare("sys", "Hello")
        msgs.append(Message.assistant("Hi"))
        sw.commit(msgs)

        data = sw.to_dict()

        sw2 = SlidingWindow()
        sw2.from_dict(data)
        assert sw2.max_turns == 10
        assert sw2.turn_count == 1

    def test_token_window_roundtrip(self):
        tw = TokenWindow(max_tokens=3000)
        msgs = tw.prepare("sys", "Test")
        msgs.append(Message.assistant("Response"))
        tw.commit(msgs)

        data = tw.to_dict()
        tw2 = TokenWindow()
        tw2.from_dict(data)
        assert tw2.max_tokens == 3000
        assert tw2.turn_count == 1


# ── Session Persistence ──────────────────────────────────

class TestSession:
    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_save_and_restore(self):
        session = Session("test-chat", session_dir=self._tmpdir)

        sw = SlidingWindow(max_turns=10)
        msgs = sw.prepare("sys", "Hello")
        msgs.append(Message.assistant("Hi"))
        sw.commit(msgs)

        session.save(sw)
        assert session.exists

        # Restore into a fresh manager
        sw2 = SlidingWindow()
        restored = session.restore(sw2)
        assert restored is True
        assert sw2.turn_count == 1

        # Verify conversation works after restore
        msgs = sw2.prepare("sys", "Turn 2")
        assert len(msgs) == 4  # system + user1 + asst1 + user2

    def test_restore_nonexistent(self):
        session = Session("nonexistent", session_dir=self._tmpdir)
        sw = SlidingWindow()
        assert session.restore(sw) is False
        assert sw.turn_count == 0

    def test_delete(self):
        session = Session("deleteme", session_dir=self._tmpdir)
        sw = SlidingWindow()
        msgs = sw.prepare("sys", "Hello")
        sw.commit(msgs)
        session.save(sw)
        assert session.exists

        session.delete()
        assert not session.exists

    def test_multi_turn_persist(self):
        """Simulate multiple turns with persistence."""
        session = Session("multi", session_dir=self._tmpdir)

        # Turn 1
        sw = SlidingWindow(max_turns=10)
        msgs = sw.prepare("sys", "What's the weather?")
        msgs.append(Message.assistant("It's 72F."))
        sw.commit(msgs)
        session.save(sw)

        # "Restart" — new manager, restore from session
        sw2 = SlidingWindow()
        session.restore(sw2)

        # Turn 2
        msgs = sw2.prepare("sys", "Convert to Celsius")
        assert len(msgs) == 4  # system + user1 + asst1 + user2
        assert msgs[1].content == "What's the weather?"
        assert msgs[2].content == "It's 72F."
        assert msgs[3].content == "Convert to Celsius"


# ── Agent Integration (with mock) ─────────────────────────

class TestAgentConversation:
    """Test conversation management through the Agent interface."""

    def test_conversation_none_is_stateless(self):
        """conversation=None means each run is independent."""
        from freeagent import Agent
        agent = Agent(model="test", conversation=None)
        assert agent.conversation is None

    def test_default_is_sliding_window(self):
        from freeagent import Agent
        agent = Agent(model="test")
        assert isinstance(agent.conversation, SlidingWindow)
        assert agent.conversation.max_turns == 20

    def test_custom_conversation(self):
        from freeagent import Agent
        tw = TokenWindow(max_tokens=2000)
        agent = Agent(model="test", conversation=tw)
        assert agent.conversation is tw

    def test_session_creates_session_object(self):
        from freeagent import Agent
        agent = Agent(model="test", session="my-test-session")
        assert agent._session is not None
        assert agent._session.name == "my-test-session"

    def test_repr_shows_turns(self):
        from freeagent import Agent
        agent = Agent(model="test", conversation=SlidingWindow(max_turns=5))
        r = repr(agent)
        assert "turns=0" in r
