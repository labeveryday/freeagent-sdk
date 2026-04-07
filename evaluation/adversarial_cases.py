"""
Adversarial test cases — designed to expose specific failure modes.

Each case targets ONE guardrail. The point is to construct prompts where:
1. A model is likely to produce malformed output
2. Raw Ollama (no framework) hits the failure mode and fails or hallucinates
3. FreeAgent's guardrail catches the failure and the model recovers

For each case we measure:
- Did raw Ollama get the right answer?
- Did FreeAgent get the right answer?
- Which guardrails fired in FreeAgent? (validation_errors, retries, loop, etc.)
- If FreeAgent succeeded where raw failed, was it because of a guardrail (real rescue)
  or just noise (lucky)?

This is the thesis test: "Framework catches what the model can't."
"""

from __future__ import annotations


# ── Tool definitions used by adversarial cases ──────────

# Note: tool function bodies are mocks — the test is about whether
# the framework rescues malformed CALLS to these tools.

WEATHER_TOOL_SPEC = {
    "type": "function",
    "function": {
        "name": "weather",
        "description": "Get current weather for a city.",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "City name"}},
            "required": ["city"],
        },
    },
}

CALC_TOOL_SPEC = {
    "type": "function",
    "function": {
        "name": "calculator",
        "description": "Evaluate a math expression.",
        "parameters": {
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
        },
    },
}

CONVERTER_TOOL_SPEC = {
    "type": "function",
    "function": {
        "name": "unit_converter",
        "description": "Convert between units (miles/km, F/C, lbs/kg).",
        "parameters": {
            "type": "object",
            "properties": {
                "value": {"type": "number"},
                "from_unit": {"type": "string"},
                "to_unit": {"type": "string"},
            },
            "required": ["value", "from_unit", "to_unit"],
        },
    },
}


# ── Mock tool implementations ────────────────────────────

WEATHER_DATA = {
    "tokyo": {"temp_f": 85, "condition": "sunny"},
    "london": {"temp_f": 61, "condition": "rainy"},
    "new york": {"temp_f": 72, "condition": "partly cloudy"},
    "paris": {"temp_f": 68, "condition": "overcast"},
}

def weather_fn(city: str) -> dict:
    key = city.lower().strip()
    for k, v in WEATHER_DATA.items():
        if k in key:
            return {**v, "city": city}
    return {"city": city, "temp_f": 70, "condition": "unknown"}

def calculator_fn(expression: str) -> dict:
    try:
        if not all(c in "0123456789+-*/.() " for c in expression):
            return {"error": "invalid characters"}
        return {"expression": expression, "result": eval(expression)}  # noqa
    except Exception as e:
        return {"error": str(e)}

def unit_converter_fn(value, from_unit: str, to_unit: str) -> dict:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return {"error": f"invalid value: {value}"}
    conversions = {
        ("fahrenheit", "celsius"): lambda v: round((v - 32) * 5/9, 2),
        ("celsius", "fahrenheit"): lambda v: round(v * 9/5 + 32, 2),
        ("miles", "km"): lambda v: round(v * 1.60934, 2),
        ("km", "miles"): lambda v: round(v / 1.60934, 2),
    }
    key = (from_unit.lower().strip(), to_unit.lower().strip())
    if key in conversions:
        return {"value": value, "result": conversions[key](value)}
    return {"error": f"unknown conversion: {from_unit} to {to_unit}"}


TOOL_FNS = {
    "weather": weather_fn,
    "calculator": calculator_fn,
    "unit_converter": unit_converter_fn,
}


# ── Adversarial cases ────────────────────────────────────
#
# Each case has:
#   name: identifier
#   target: which guardrail should rescue this case
#   tools: tool specs the model has access to
#   prompt: user prompt designed to trigger the failure mode
#   expected_in_response: substrings the final answer must contain
#   notes: explanation of the failure mode

ADVERSARIAL_CASES = [

    # ── Fuzzy tool name matching ──────────────────────
    {
        "name": "fuzzy_get_weather",
        "target": "fuzzy_match",
        "tools": [WEATHER_TOOL_SPEC],
        "prompt": "Use the get_weather tool to look up the weather in Tokyo.",
        "expected_in_response": ["85", "sunny"],
        "notes": (
            "Tool is named 'weather' but prompt explicitly says 'get_weather'. "
            "Small models often follow the prompt literally and emit 'get_weather'. "
            "Raw Ollama: tool not found error → model gives bad answer or hallucinates. "
            "FreeAgent: validator fuzzy-matches → suggests 'weather' → model retries → success."
        ),
    },

    {
        "name": "fuzzy_check_weather",
        "target": "fuzzy_match",
        "tools": [WEATHER_TOOL_SPEC],
        "prompt": "Please call check_weather for London.",
        "expected_in_response": ["61", "rainy"],
        "notes": "Same as above but with check_weather as the wrong name.",
    },

    {
        "name": "fuzzy_weather_lookup",
        "target": "fuzzy_match",
        "tools": [WEATHER_TOOL_SPEC],
        "prompt": "Use weather_lookup to find conditions in Paris.",
        "expected_in_response": ["68", "overcast"],
        "notes": "Yet another wrong tool name pattern.",
    },

    # ── Missing required field (validator + retry) ────
    {
        "name": "missing_city_field",
        "target": "validation_retry",
        "tools": [WEATHER_TOOL_SPEC],
        "prompt": (
            "Check the weather for the most popular city in Japan. "
            "Use the weather tool."
        ),
        "expected_in_response": ["tokyo", "85"],
        "notes": (
            "Model has to figure out 'Tokyo' from 'most popular city in Japan'. "
            "Some small models call weather() with no args. "
            "FreeAgent: validator catches missing 'city', model retries with city='Tokyo'."
        ),
    },

    # ── Wrong arg name (validator + retry) ────────────
    {
        "name": "wrong_arg_name",
        "target": "validation_retry",
        "tools": [WEATHER_TOOL_SPEC],
        "prompt": (
            "Look up weather using the location 'New York'. "
            "Make sure to use the weather tool."
        ),
        "expected_in_response": ["72", "partly cloudy"],
        "notes": (
            "Prompt says 'location' which may make the model emit weather(location='NYC') "
            "instead of weather(city='NYC'). Validator catches missing 'city'."
        ),
    },

    # ── Tool output truncation (sanitization) ─────────
    {
        "name": "huge_tool_output",
        "target": "truncation",
        "tools": [WEATHER_TOOL_SPEC],
        "prompt": (
            "Get the weather in London and tell me the temperature."
        ),
        "expected_in_response": ["61"],
        "notes": (
            "We'll inject a giant payload via a wrapped tool. "
            "FreeAgent should truncate to max_tool_result_chars (2000 default). "
            "Raw Ollama: full payload eats context, model loses focus."
        ),
        "use_huge_output": True,
    },

    # ── Loop trap (circuit breaker) ───────────────────
    {
        "name": "loop_trap",
        "target": "circuit_breaker",
        "tools": [WEATHER_TOOL_SPEC],
        "prompt": (
            "Check the weather in NowhereCity. If it fails, try again with the same input. "
            "Keep trying until you get a result."
        ),
        "expected_in_response": ["nowhere", "unknown"],
        "notes": (
            "Prompt explicitly tells the model to retry. "
            "FreeAgent: circuit breaker fires after 3 identical calls, forces final answer. "
            "Raw Ollama: may loop until iteration limit."
        ),
    },

    # ── Type coercion (string number) ─────────────────
    {
        "name": "type_coercion_temp",
        "target": "type_coercion",
        "tools": [CONVERTER_TOOL_SPEC],
        "prompt": (
            "Convert eighty-five degrees Fahrenheit to Celsius using the unit_converter tool."
        ),
        "expected_in_response": ["29"],
        "notes": (
            "Model has to parse 'eighty-five' as 85. Some models pass it as a string. "
            "FreeAgent: type coercion converts string '85' to int 85. "
            "Raw Ollama: may pass string and tool errors out."
        ),
    },

    # ── Numeric precision in answer ───────────────────
    {
        "name": "precision_calc",
        "target": "validation_retry",
        "tools": [CALC_TOOL_SPEC],
        "prompt": "Calculate 347 multiplied by 29 using the calculator tool. Report the exact number.",
        "expected_in_response": ["10063"],
        "notes": (
            "Model should call calculator and return 10063. "
            "Some models paraphrase or round the result. "
            "Both raw and FreeAgent get this — but FreeAgent's tool-user skill may help."
        ),
    },

    # ── Hallucinated tool ──────────────────────────────
    {
        "name": "hallucinate_tool",
        "target": "fuzzy_match",
        "tools": [WEATHER_TOOL_SPEC],
        "prompt": (
            "Get the temperature in Tokyo. You can use the get_temperature tool, "
            "the weather_api tool, or the weather tool — whichever works."
        ),
        "expected_in_response": ["85"],
        "notes": (
            "Prompt offers 3 tool names but only 'weather' exists. "
            "Model picks one of the wrong ones first. "
            "FreeAgent: fuzzy match suggests 'weather' on each error."
        ),
    },
]


def get_case_by_name(name: str) -> dict | None:
    for c in ADVERSARIAL_CASES:
        if c["name"] == name:
            return c
    return None


def cases_by_target(target: str) -> list[dict]:
    return [c for c in ADVERSARIAL_CASES if c["target"] == target]


# Targets summary
TARGETS = {
    "fuzzy_match": "Validator fuzzy-matches wrong tool names",
    "validation_retry": "Validator catches missing/wrong fields, retries with feedback",
    "truncation": "Sanitization truncates huge tool outputs",
    "circuit_breaker": "Circuit breaker stops infinite loops",
    "type_coercion": "Validator coerces string numbers to actual numbers",
}
