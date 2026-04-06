"""Tests for the validator — fuzzy matching, type coercion, error feedback."""

from freeagent.validator import Validator, ValidationOk, ValidationError
from freeagent.tool import Tool, ToolParam


def _make_tool(name="weather", params=None):
    if params is None:
        params = [ToolParam(name="city", type="string", required=True)]
    return Tool(name=name, description="test tool", params=params, fn=lambda **kw: kw)


class TestFuzzyMatching:
    def test_exact_match(self):
        v = Validator([_make_tool("weather")])
        result = v.validate("weather", {"city": "NYC"})
        assert isinstance(result, ValidationOk)

    def test_close_misspelling_suggests(self):
        v = Validator([_make_tool("weather")])
        result = v.validate("weathr", {"city": "NYC"})
        assert isinstance(result, ValidationError)
        assert "Did you mean" in result.errors[0]
        assert "weather" in result.errors[0]

    def test_totally_wrong_name_lists_available(self):
        v = Validator([_make_tool("weather"), _make_tool("calculator")])
        result = v.validate("foobar", {})
        assert isinstance(result, ValidationError)
        assert "Available tools" in result.errors[0]

    def test_unknown_tool_no_tools(self):
        v = Validator([])
        result = v.validate("anything", {})
        assert isinstance(result, ValidationError)


class TestRequiredFields:
    def test_missing_required_field(self):
        v = Validator([_make_tool("weather")])
        result = v.validate("weather", {})
        assert isinstance(result, ValidationError)
        assert any("city" in e for e in result.errors)

    def test_all_required_present(self):
        v = Validator([_make_tool("weather")])
        result = v.validate("weather", {"city": "NYC"})
        assert isinstance(result, ValidationOk)


class TestTypeCoercion:
    def test_string_to_integer(self):
        tool = _make_tool("calc", [ToolParam(name="n", type="integer", required=True)])
        v = Validator([tool])
        result = v.validate("calc", {"n": "42"})
        assert isinstance(result, ValidationOk)
        assert result.args["n"] == 42

    def test_string_to_float(self):
        tool = _make_tool("calc", [ToolParam(name="n", type="number", required=True)])
        v = Validator([tool])
        result = v.validate("calc", {"n": "3.14"})
        assert isinstance(result, ValidationOk)
        assert result.args["n"] == 3.14

    def test_string_to_boolean_true(self):
        tool = _make_tool("toggle", [ToolParam(name="on", type="boolean", required=True)])
        v = Validator([tool])
        for val in ["true", "1", "yes"]:
            result = v.validate("toggle", {"on": val})
            assert isinstance(result, ValidationOk)
            assert result.args["on"] is True

    def test_string_to_boolean_false(self):
        tool = _make_tool("toggle", [ToolParam(name="on", type="boolean", required=True)])
        v = Validator([tool])
        for val in ["false", "0", "no"]:
            result = v.validate("toggle", {"on": val})
            assert isinstance(result, ValidationOk)
            assert result.args["on"] is False

    def test_invalid_coercion_left_as_is(self):
        tool = _make_tool("calc", [ToolParam(name="n", type="integer", required=True)])
        v = Validator([tool])
        result = v.validate("calc", {"n": "not_a_number"})
        assert isinstance(result, ValidationOk)
        assert result.args["n"] == "not_a_number"  # left unchanged


class TestStringArgs:
    def test_json_string_parsed(self):
        v = Validator([_make_tool("weather")])
        result = v.validate("weather", '{"city": "NYC"}')
        assert isinstance(result, ValidationOk)
        assert result.args["city"] == "NYC"

    def test_invalid_json_string(self):
        v = Validator([_make_tool("weather")])
        result = v.validate("weather", "not json")
        assert isinstance(result, ValidationError)


class TestDefaults:
    def test_optional_field_gets_default(self):
        tool = _make_tool("search", [
            ToolParam(name="q", type="string", required=True),
            ToolParam(name="limit", type="integer", required=False, default=10),
        ])
        v = Validator([tool])
        result = v.validate("search", {"q": "test"})
        assert isinstance(result, ValidationOk)
        assert result.args["limit"] == 10

    def test_schema_returned_on_error(self):
        v = Validator([_make_tool("weather")])
        result = v.validate("weather", {})
        assert isinstance(result, ValidationError)
        assert result.schema is not None
        assert "properties" in result.schema
