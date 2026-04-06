"""Tests for Message factory methods and to_ollama() format."""

from freeagent.messages import Message


class TestFactoryMethods:
    def test_system(self):
        m = Message.system("You are helpful.")
        assert m.role == "system"
        assert m.content == "You are helpful."

    def test_user(self):
        m = Message.user("Hello")
        assert m.role == "user"
        assert m.content == "Hello"

    def test_assistant(self):
        m = Message.assistant("Hi there")
        assert m.role == "assistant"
        assert m.content == "Hi there"
        assert m.tool_calls is None

    def test_assistant_with_tool_calls(self):
        calls = [{"function": {"name": "weather", "arguments": {"city": "NYC"}}}]
        m = Message.assistant("Calling weather...", tool_calls=calls)
        assert m.tool_calls == calls

    def test_tool_result(self):
        m = Message.tool_result("weather", '{"temp": 72}')
        assert m.role == "tool"
        assert m.name == "weather"
        assert m.content == '{"temp": 72}'

    def test_tool_error(self):
        m = Message.tool_error("weather", ["Missing field 'city'"], {"type": "object"})
        assert m.role == "tool"
        assert "Missing field 'city'" in m.content
        assert "Expected schema" in m.content
        assert "try again" in m.content.lower()

    def test_tool_error_no_schema(self):
        m = Message.tool_error("weather", ["Bad args"])
        assert "Bad args" in m.content
        assert "schema" not in m.content.lower()


class TestToOllama:
    def test_basic_message(self):
        m = Message.user("Hello")
        d = m.to_ollama()
        assert d == {"role": "user", "content": "Hello"}

    def test_message_with_tool_calls(self):
        calls = [{"function": {"name": "calc", "arguments": {"n": 1}}}]
        m = Message.assistant("Calling calc...", tool_calls=calls)
        d = m.to_ollama()
        assert d["tool_calls"] == calls

    def test_message_without_tool_calls(self):
        m = Message.assistant("No tools")
        d = m.to_ollama()
        assert "tool_calls" not in d
