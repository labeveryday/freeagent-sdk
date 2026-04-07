"""
Shared evaluation utilities — timing, metrics, reporting, and mock tools.
"""

import json
import os
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

# Ollama base URL — override with OLLAMA_HOST env var
OLLAMA_BASE_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# Models to evaluate
MODELS = ["qwen3:8b", "qwen3:4b", "llama3.1:latest", "gemma4:e2b"]


def check_ollama():
    """Verify Ollama is running. Exit early with a clear message if not."""
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            names = [m["name"] for m in data.get("models", [])]
            print(f"  Ollama OK — {len(names)} models: {', '.join(names[:5])}")
    except Exception as e:
        print(f"  ERROR: Cannot connect to Ollama at {OLLAMA_BASE_URL}")
        print(f"  {e}")
        print(f"  Make sure Ollama is running: ollama serve")
        sys.exit(1)


# ── Eval Data Structures ──────────────────────────────────

@dataclass
class EvalResult:
    """Result of a single evaluation case."""
    name: str
    framework: str
    model: str
    prompt: str
    response: str = ""
    success: bool = False
    error: str = ""
    latency_ms: float = 0
    tokens_generated: int = 0
    tokens_per_second: float = 0
    tool_calls_made: int = 0
    tool_calls_expected: int = 0
    correct: bool = False
    notes: str = ""


@dataclass
class EvalSuite:
    """Collection of evaluation results."""
    name: str
    results: list[EvalResult] = field(default_factory=list)

    def add(self, result: EvalResult):
        self.results.append(result)

    def summary(self) -> dict:
        if not self.results:
            return {}

        by_framework = {}
        for r in self.results:
            key = f"{r.framework} / {r.model}"
            if key not in by_framework:
                by_framework[key] = []
            by_framework[key].append(r)

        summary = {}
        for key, results in by_framework.items():
            total = len(results)
            successes = sum(1 for r in results if r.success)
            correct = sum(1 for r in results if r.correct)
            avg_latency = sum(r.latency_ms for r in results) / total if total else 0
            # Only average TPS across results that have it (skip Strands zeros)
            tps_results = [r.tokens_per_second for r in results if r.tokens_per_second > 0]
            avg_tps = sum(tps_results) / len(tps_results) if tps_results else 0
            errors = [r.error for r in results if r.error]

            summary[key] = {
                "total": total,
                "success_rate": f"{successes}/{total} ({100*successes/total:.0f}%)",
                "accuracy": f"{correct}/{total} ({100*correct/total:.0f}%)",
                "avg_latency_ms": round(avg_latency, 1),
                "avg_tokens_per_second": round(avg_tps, 1),
                "errors": errors[:3],
            }
        return summary

    def print_report(self):
        print(f"\n{'='*70}")
        print(f"  EVALUATION: {self.name}")
        print(f"{'='*70}")

        for key, stats in self.summary().items():
            print(f"\n  {key}")
            print(f"  {'─'*50}")
            print(f"  Success Rate:       {stats['success_rate']}")
            print(f"  Accuracy:           {stats['accuracy']}")
            print(f"  Avg Latency:        {stats['avg_latency_ms']}ms")
            print(f"  Avg Tokens/sec:     {stats['avg_tokens_per_second']}")
            if stats['errors']:
                print(f"  Errors:             {stats['errors'][0][:80]}")

        print(f"\n{'='*70}\n")

    def to_dict(self) -> dict:
        return {
            "suite": self.name,
            "summary": self.summary(),
            "results": [
                {
                    "name": r.name,
                    "framework": r.framework,
                    "model": r.model,
                    "prompt": r.prompt,
                    "response": r.response[:500],
                    "success": r.success,
                    "correct": r.correct,
                    "error": r.error,
                    "latency_ms": r.latency_ms,
                    "tokens_generated": r.tokens_generated,
                    "tokens_per_second": r.tokens_per_second,
                    "tool_calls_made": r.tool_calls_made,
                    "tool_calls_expected": r.tool_calls_expected,
                    "notes": r.notes,
                }
                for r in self.results
            ],
        }


# ── Ollama API ────────────────────────────────────────────

def ollama_chat(model: str, messages: list[dict], tools: list[dict] | None = None,
                temperature: float = 0.1) -> dict:
    """Raw Ollama API call. Returns full response dict."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if tools:
        payload["tools"] = tools

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_tps(result: dict) -> tuple[int, float]:
    """Extract tokens generated and tokens/sec from Ollama response."""
    eval_count = result.get("eval_count", 0)
    eval_duration_ns = result.get("eval_duration", 0)
    tps = (eval_count / eval_duration_ns * 1e9) if eval_duration_ns > 0 else 0
    return eval_count, tps


def timed_ollama_chat(model: str, messages: list[dict], tools: list[dict] | None = None,
                      temperature: float = 0.1) -> tuple[dict, float, float]:
    """Ollama chat with timing. Returns (response, latency_ms, tokens_per_second)."""
    start = time.monotonic()
    result = ollama_chat(model, messages, tools, temperature)
    elapsed_ms = (time.monotonic() - start) * 1000
    _, tps = extract_tps(result)
    return result, elapsed_ms, tps


def ollama_tool_loop(model: str, messages: list[dict], tools: list[dict],
                     tool_fns: dict, max_iterations: int = 5) -> dict:
    """
    Run a full tool-calling loop with raw Ollama API.
    Keeps calling until the model returns text (no tool_calls) or max iterations.

    Returns dict with: response, tool_calls, latency_ms, tokens, tps
    """
    total_latency = 0
    total_tokens = 0
    total_eval_duration = 0
    tool_calls_made = []

    for _ in range(max_iterations):
        start = time.monotonic()
        resp = ollama_chat(model, messages, tools)
        elapsed = (time.monotonic() - start) * 1000
        total_latency += elapsed
        total_tokens += resp.get("eval_count", 0)
        total_eval_duration += resp.get("eval_duration", 0)

        msg = resp.get("message", {})
        tool_calls = msg.get("tool_calls", [])

        if not tool_calls:
            tps = (total_tokens / total_eval_duration * 1e9) if total_eval_duration > 0 else 0
            return {
                "response": msg.get("content", ""),
                "tool_calls": tool_calls_made,
                "latency_ms": total_latency,
                "tokens": total_tokens,
                "tps": tps,
            }

        messages.append(msg)

        for tc in tool_calls:
            fn_name = tc.get("function", {}).get("name", "")
            fn_args = tc.get("function", {}).get("arguments", {})
            tool_calls_made.append({"name": fn_name, "args": fn_args})

            fn = tool_fns.get(fn_name)
            if fn:
                try:
                    result = fn(**fn_args)
                except Exception as e:
                    result = {"error": str(e)}
            else:
                result = {"error": f"Unknown tool: {fn_name}"}

            messages.append({"role": "tool", "content": json.dumps(result)})

    tps = (total_tokens / total_eval_duration * 1e9) if total_eval_duration > 0 else 0
    return {
        "response": "[Max iterations reached]",
        "tool_calls": tool_calls_made,
        "latency_ms": total_latency,
        "tokens": total_tokens,
        "tps": tps,
    }


# ── Shared Mock Tools ─────────────────────────────────────

def weather(city: str) -> dict:
    """Get current weather for a city."""
    mock_data = {
        "new york": {"temp_f": 72, "condition": "partly cloudy", "humidity": 55},
        "london": {"temp_f": 61, "condition": "rainy", "humidity": 80},
        "tokyo": {"temp_f": 85, "condition": "sunny", "humidity": 40},
        "paris": {"temp_f": 68, "condition": "overcast", "humidity": 65},
        "sydney": {"temp_f": 58, "condition": "clear", "humidity": 45},
    }
    key = city.lower().strip()
    for k, v in mock_data.items():
        if k in key:
            return {**v, "city": city}
    return {"city": city, "temp_f": 70, "condition": "unknown", "humidity": 50}


def calculator(expression: str) -> dict:
    """Evaluate a math expression. Supports basic arithmetic (+, -, *, /, parentheses)."""
    try:
        allowed = set("0123456789+-*/.() ")
        if not all(c in allowed for c in expression):
            return {"error": f"Invalid characters in expression: {expression}"}
        if len(expression) > 100:
            return {"error": "Expression too long"}
        result = eval(expression)  # noqa: S307 — limited charset
        return {"expression": expression, "result": result}
    except ZeroDivisionError:
        return {"error": "Division by zero"}
    except Exception as e:
        return {"error": str(e)}


def unit_converter(value: float, from_unit: str, to_unit: str) -> dict:
    """Convert between common units."""
    # Coerce value to float (small models sometimes pass strings)
    try:
        value = float(value)
    except (TypeError, ValueError):
        return {"error": f"Invalid value: {value}"}

    conversions = {
        ("miles", "km"): lambda v: v * 1.60934,
        ("km", "miles"): lambda v: v / 1.60934,
        ("fahrenheit", "celsius"): lambda v: (v - 32) * 5/9,
        ("celsius", "fahrenheit"): lambda v: v * 9/5 + 32,
        ("pounds", "kg"): lambda v: v * 0.453592,
        ("kg", "pounds"): lambda v: v / 0.453592,
        ("feet", "meters"): lambda v: v * 0.3048,
        ("meters", "feet"): lambda v: v / 0.3048,
    }
    key = (from_unit.lower().strip(), to_unit.lower().strip())
    if key in conversions:
        result = conversions[key](value)
        return {"value": value, "from": from_unit, "to": to_unit, "result": round(result, 2)}
    return {"error": f"Unknown conversion: {from_unit} to {to_unit}"}


TOOL_FNS = {"weather": weather, "calculator": calculator, "unit_converter": unit_converter}

OLLAMA_TOOL_SPECS = [
    {
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
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluate a math expression. Supports basic arithmetic.",
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string", "description": "Math expression"}},
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "unit_converter",
            "description": "Convert between common units (miles/km, fahrenheit/celsius, pounds/kg, feet/meters).",
            "parameters": {
                "type": "object",
                "properties": {
                    "value": {"type": "number", "description": "Numeric value to convert"},
                    "from_unit": {"type": "string", "description": "Unit to convert from"},
                    "to_unit": {"type": "string", "description": "Unit to convert to"},
                },
                "required": ["value", "from_unit", "to_unit"],
            },
        },
    },
]


def make_strands_tools():
    """Create Strands tool wrappers. Names match the Ollama tool specs exactly."""
    import strands

    @strands.tool(name="weather")
    def weather_tool(city: str) -> dict:
        """Get current weather for a city."""
        return weather(city)

    @strands.tool(name="calculator")
    def calculator_tool(expression: str) -> dict:
        """Evaluate a math expression. Supports basic arithmetic."""
        return calculator(expression)

    @strands.tool(name="unit_converter")
    def unit_converter_tool(value: float, from_unit: str, to_unit: str) -> dict:
        """Convert between common units (miles/km, fahrenheit/celsius, pounds/kg, feet/meters)."""
        return unit_converter(value, from_unit, to_unit)

    return [weather_tool, calculator_tool, unit_converter_tool]


# ── Helpers ───────────────────────────────────────────────

def check_response_contains(response_text: str, expected: list[str]) -> bool:
    """Check if response contains all expected substrings (case-insensitive)."""
    if not expected:
        return True
    lower = response_text.lower()
    return all(e.lower() in lower for e in expected)


def eval_dir() -> Path:
    """Return the evaluation/ directory path regardless of cwd."""
    return Path(__file__).parent


def save_results(suite: EvalSuite, filename: str):
    """Save results JSON to the evaluation/ directory."""
    path = eval_dir() / filename
    with open(path, "w") as f:
        json.dump(suite.to_dict(), f, indent=2)
    print(f"Results saved to {path}")


# ── Strands Metrics Extraction ────────────────────────────

def extract_strands_metrics(agent) -> dict:
    """
    Extract tool calls, cycles, timing, and token usage from a Strands agent
    after a run. Works with agent.event_loop_metrics.

    Returns dict with:
        cycles, total_duration, avg_cycle_time,
        tools_called (list of names), tool_details (per-tool stats),
        total_tool_calls, accumulated_usage (tokens)
    """
    m = agent.event_loop_metrics
    summary = m.get_summary()

    tools_called = []
    tool_details = {}
    for tool_name, info in summary.get("tool_usage", {}).items():
        stats = info.get("execution_stats", {})
        tools_called.append(tool_name)
        tool_details[tool_name] = {
            "count": stats.get("call_count", 0),
            "success": stats.get("success_count", 0),
            "errors": stats.get("error_count", 0),
            "avg_time": round(stats.get("average_time", 0), 3),
            "success_rate": round(stats.get("success_rate", 0), 3),
        }

    usage = summary.get("accumulated_usage", {})

    return {
        "cycles": summary.get("total_cycles", 0),
        "total_duration": summary.get("total_duration", 0),
        "avg_cycle_time": summary.get("average_cycle_time", 0),
        "tools_called": tools_called,
        "tool_details": tool_details,
        "total_tool_calls": sum(d["count"] for d in tool_details.values()),
        "input_tokens": usage.get("inputTokens", 0),
        "output_tokens": usage.get("outputTokens", 0),
        "total_tokens": usage.get("totalTokens", 0),
    }


def format_strands_metrics(sm: dict) -> str:
    """Format strands metrics dict into a compact log string."""
    tools_str = ", ".join(sm["tools_called"]) if sm["tools_called"] else "none"
    tokens = f"  tokens:{sm['total_tokens']}" if sm["total_tokens"] else ""
    return (
        f"{sm['cycles']} cycles  "
        f"calls:{sm['total_tool_calls']}  "
        f"tools:[{tools_str}]"
        f"{tokens}"
    )
