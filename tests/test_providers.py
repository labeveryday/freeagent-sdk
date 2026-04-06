"""Tests for OpenAICompatProvider parsing — thinking tags, code fences, malformed JSON."""

from freeagent.providers.openai_compat import OpenAICompatProvider
from freeagent.messages import Message


class TestParseArguments:
    def test_dict_passthrough(self):
        assert OpenAICompatProvider._parse_arguments({"city": "NYC"}) == {"city": "NYC"}

    def test_json_string(self):
        assert OpenAICompatProvider._parse_arguments('{"city": "NYC"}') == {"city": "NYC"}

    def test_non_dict_json(self):
        # A non-dict JSON value should return empty
        assert OpenAICompatProvider._parse_arguments('"just a string"') == {}

    def test_strips_thinking_tags(self):
        raw = '<think>Let me think about this...</think>{"city": "NYC"}'
        assert OpenAICompatProvider._parse_arguments(raw) == {"city": "NYC"}

    def test_strips_code_fences(self):
        raw = '```json\n{"city": "NYC"}\n```'
        assert OpenAICompatProvider._parse_arguments(raw) == {"city": "NYC"}

    def test_code_fence_no_lang(self):
        raw = '```\n{"city": "NYC"}\n```'
        assert OpenAICompatProvider._parse_arguments(raw) == {"city": "NYC"}

    def test_json_embedded_in_text(self):
        raw = 'Here is the arguments: {"city": "NYC"} end'
        assert OpenAICompatProvider._parse_arguments(raw) == {"city": "NYC"}

    def test_non_string_non_dict(self):
        assert OpenAICompatProvider._parse_arguments(42) == {}
        assert OpenAICompatProvider._parse_arguments(None) == {}

    def test_completely_malformed(self):
        assert OpenAICompatProvider._parse_arguments("not json at all") == {}

    def test_empty_string(self):
        assert OpenAICompatProvider._parse_arguments("") == {}


class TestCleanContent:
    def test_strips_thinking_tags(self):
        content = "<think>hmm</think>The answer is 42."
        assert OpenAICompatProvider._clean_content(content) == "The answer is 42."

    def test_multiline_thinking(self):
        content = "<think>\nstep 1\nstep 2\n</think>\nFinal answer."
        assert OpenAICompatProvider._clean_content(content) == "Final answer."

    def test_empty_content(self):
        assert OpenAICompatProvider._clean_content("") == ""
        assert OpenAICompatProvider._clean_content(None) == ""

    def test_no_thinking_tags(self):
        assert OpenAICompatProvider._clean_content("Hello") == "Hello"


class TestToOpenAIMessages:
    def _provider(self):
        return OpenAICompatProvider(model="test", base_url="http://localhost:8000")

    def test_basic_messages(self):
        p = self._provider()
        msgs = [Message.system("sys"), Message.user("hi")]
        result = p._to_openai_messages(msgs)
        assert result[0] == {"role": "system", "content": "sys"}
        assert result[1] == {"role": "user", "content": "hi"}

    def test_tool_calls_converted(self):
        p = self._provider()
        calls = [{"function": {"name": "calc", "arguments": {"n": 1}}}]
        msgs = [Message.assistant("", tool_calls=calls)]
        result = p._to_openai_messages(msgs)
        assert result[0]["tool_calls"][0]["id"] == "call_0"
        assert result[0]["tool_calls"][0]["type"] == "function"
        assert result[0]["content"] is None  # null when tool_calls present

    def test_tool_result_has_call_id(self):
        p = self._provider()
        msgs = [Message.tool_result("calc", "42")]
        result = p._to_openai_messages(msgs)
        assert result[0]["tool_call_id"] == "call_0"


class TestParseToolCalls:
    def _provider(self):
        return OpenAICompatProvider(model="test", base_url="http://localhost:8000")

    def test_empty_tool_calls(self):
        p = self._provider()
        assert p._parse_tool_calls(None) == []
        assert p._parse_tool_calls([]) == []

    def test_valid_tool_calls(self):
        p = self._provider()
        calls = [{
            "function": {
                "name": "weather",
                "arguments": '{"city": "NYC"}',
            }
        }]
        result = p._parse_tool_calls(calls)
        assert len(result) == 1
        assert result[0]["function"]["name"] == "weather"
        assert result[0]["function"]["arguments"] == {"city": "NYC"}

    def test_malformed_arguments_recovered(self):
        p = self._provider()
        calls = [{
            "function": {
                "name": "weather",
                "arguments": '<think>thinking</think>{"city": "NYC"}',
            }
        }]
        result = p._parse_tool_calls(calls)
        assert result[0]["function"]["arguments"] == {"city": "NYC"}
