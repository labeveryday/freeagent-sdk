"""Tests for tool output sanitization and truncation."""

from freeagent.sanitize import sanitize_tool_output, truncate_tool_output


class TestSanitizeToolOutput:
    def test_strips_ansi_codes(self):
        text = "\x1b[31mError\x1b[0m: something failed"
        result = sanitize_tool_output(text)
        assert "\x1b[" not in result
        assert "Error: something failed" in result

    def test_strips_html_tags(self):
        text = "<div><b>Hello</b> world</div>"
        result = sanitize_tool_output(text)
        assert "<div>" not in result
        assert "<b>" not in result
        assert "Hello world" in result

    def test_normalizes_whitespace(self):
        text = "line1\n\n\n\n\nline2"
        result = sanitize_tool_output(text)
        assert "\n\n\n" not in result
        assert "line1\n\nline2" == result

    def test_normalizes_multiple_spaces(self):
        text = "hello     world"
        result = sanitize_tool_output(text)
        assert "hello world" == result

    def test_flattens_nested_json(self):
        import json
        nested = json.dumps({
            "a": {"b": {"c": {"d": {"e": "deep"}}}}
        })
        result = sanitize_tool_output(nested)
        parsed = json.loads(result)
        # Depth 3+ should be stringified
        assert isinstance(parsed["a"]["b"]["c"], str)

    def test_empty_input(self):
        assert sanitize_tool_output("") == ""
        assert sanitize_tool_output(None) is None

    def test_plain_text_unchanged(self):
        text = "Simple result: 42"
        assert sanitize_tool_output(text) == text

    def test_combined_cleanup(self):
        text = "\x1b[1m<h1>Title</h1>\x1b[0m\n\n\n\nBody    text"
        result = sanitize_tool_output(text)
        assert "\x1b[" not in result
        assert "<h1>" not in result
        assert "\n\n\n" not in result


class TestTruncateToolOutput:
    def test_short_output_unchanged(self):
        text = "short"
        assert truncate_tool_output(text, 100) == text

    def test_truncate_strategy(self):
        text = "x" * 500
        result = truncate_tool_output(text, 100, "truncate")
        assert len(result) <= 100
        assert "[truncated" in result

    def test_summarize_head_tail_strategy(self):
        text = "HEAD" + "x" * 500 + "TAIL"
        result = truncate_tool_output(text, 100, "summarize_head_tail")
        assert len(result) <= 100
        assert "HEAD" in result
        assert "TAIL" in result
        assert "truncated" in result

    def test_empty_input(self):
        assert truncate_tool_output("", 100) == ""

    def test_exact_limit(self):
        text = "x" * 100
        assert truncate_tool_output(text, 100) == text

    def test_truncate_preserves_original_length_info(self):
        text = "x" * 5000
        result = truncate_tool_output(text, 200, "truncate")
        assert "5000" in result
