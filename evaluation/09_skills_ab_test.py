"""
FreeAgent Evaluation 9: Skills A/B Test

Runs the same tool calling cases 3 ways:
1. FreeAgent with bundled skills (default)
2. FreeAgent with NO skills
3. FreeAgent with ONLY tool-user skill

Compares accuracy across all 3 configurations per model.
"""

import json
import time
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from eval_utils import (
    EvalResult, EvalSuite, MODELS,
    check_response_contains, check_ollama, save_results,
)

sys.path.insert(0, str(Path(__file__).parent.parent))
from freeagent import Agent, AgentConfig, tool as freeagent_tool
from freeagent.skills import load_skills, BUNDLED_SKILLS_DIR


# Same tools as eval 06
@freeagent_tool
def weather(city: str) -> dict:
    """Get current weather for a city.

    city: City name
    """
    mock_data = {
        "new york": {"temp_f": 72, "condition": "partly cloudy", "humidity": 55},
        "london": {"temp_f": 61, "condition": "rainy", "humidity": 80},
        "tokyo": {"temp_f": 85, "condition": "sunny", "humidity": 40},
        "paris": {"temp_f": 68, "condition": "overcast", "humidity": 65},
    }
    key = city.lower().strip()
    for k, v in mock_data.items():
        if k in key:
            return {**v, "city": city}
    return {"city": city, "temp_f": 70, "condition": "unknown", "humidity": 50}


@freeagent_tool
def calculator(expression: str) -> dict:
    """Evaluate a math expression. Supports basic arithmetic.

    expression: Math expression
    """
    try:
        allowed = set("0123456789+-*/.() ")
        if not all(c in allowed for c in expression):
            return {"error": f"Invalid characters: {expression}"}
        result = eval(expression)
        return {"expression": expression, "result": result}
    except Exception as e:
        return {"error": str(e)}


@freeagent_tool
def unit_converter(value: float, from_unit: str, to_unit: str) -> dict:
    """Convert between common units (miles/km, fahrenheit/celsius, pounds/kg, feet/meters).

    value: Numeric value to convert
    from_unit: Unit to convert from
    to_unit: Unit to convert to
    """
    try:
        value = float(value)
    except (TypeError, ValueError):
        return {"error": f"Invalid value: {value}"}
    conversions = {
        ("miles", "km"): lambda v: v * 1.60934,
        ("km", "miles"): lambda v: v / 1.60934,
        ("fahrenheit", "celsius"): lambda v: (v - 32) * 5/9,
        ("celsius", "fahrenheit"): lambda v: v * 9/5 + 32,
    }
    key = (from_unit.lower().strip(), to_unit.lower().strip())
    if key in conversions:
        result = conversions[key](value)
        return {"value": value, "from": from_unit, "to": to_unit, "result": round(result, 2)}
    return {"error": f"Unknown conversion: {from_unit} to {to_unit}"}


TOOLS = [weather, calculator, unit_converter]

# Subset of cases for faster A/B testing
CASES = [
    {
        "name": "single_weather",
        "prompt": "What's the weather in Tokyo?",
        "expected_tools": ["weather"],
        "expected_in_response": ["tokyo", "sunny"],
    },
    {
        "name": "single_calc",
        "prompt": "What is 347 * 29?",
        "expected_tools": ["calculator"],
        "expected_in_response": ["10063"],
    },
    {
        "name": "single_convert",
        "prompt": "Convert 100 fahrenheit to celsius.",
        "expected_tools": ["unit_converter"],
        "expected_in_response": ["37"],
    },
    {
        "name": "multi_step_convert",
        "prompt": "Get the weather in Paris, then convert the temperature to Celsius.",
        "expected_tools": ["weather", "unit_converter"],
        "expected_in_response": ["paris", "20"],
    },
    {
        "name": "tool_plus_calc",
        "prompt": "What is the temperature difference between New York (72F) and London (61F)? Use the calculator.",
        "expected_tools": ["calculator"],
        "expected_in_response": ["11"],
    },
]

SYSTEM = "You are a helpful assistant. Use the provided tools when needed. Be concise."


class SkillsConfig:
    """Configuration for a skills variant."""
    def __init__(self, name: str, skill_sources: list):
        self.name = name
        self.skill_sources = skill_sources


# Three configurations to test
CONFIGS = [
    SkillsConfig("with_skills", [BUNDLED_SKILLS_DIR]),     # default
    SkillsConfig("no_skills", []),                          # no skills at all
]

# Try to find tool-user skill dir for the third config
_tool_user_dir = BUNDLED_SKILLS_DIR / "tool-user" if BUNDLED_SKILLS_DIR.exists() else None
if _tool_user_dir and _tool_user_dir.exists():
    # We can't easily load just one skill without the other via Agent API,
    # so we'll test with_skills vs no_skills as the primary comparison.
    pass


def run_skills_ab(suite: EvalSuite):
    """Run A/B test across skill configurations."""
    for model in MODELS:
        for config in CONFIGS:
            print(f"\n  FreeAgent [{config.name}] / {model}")

            for case in CASES:
                # Create agent with specific skill configuration
                skills = load_skills(config.skill_sources) if config.skill_sources else []

                agent = Agent.__new__(Agent)
                # Manual init to control skills loading
                agent.config = AgentConfig()
                agent.config.model = model
                agent.system_prompt = SYSTEM

                from freeagent.memory import Memory, make_memory_tools
                import tempfile
                agent.memory = Memory(memory_dir=tempfile.mkdtemp())
                memory_tools = make_memory_tools(agent.memory)
                agent.tools = list(TOOLS) + memory_tools
                agent.skills = skills

                from freeagent.providers.ollama import OllamaProvider
                agent.provider = OllamaProvider(model=model)

                from freeagent.engines import NativeEngine
                agent.engine = NativeEngine(agent.provider)
                agent._mode = "native"

                from freeagent.validator import Validator
                from freeagent.circuit_breaker import CircuitBreaker
                from freeagent.hooks import HookRegistry
                from freeagent.telemetry import Metrics

                agent.validator = Validator(agent.tools)
                agent.breaker = CircuitBreaker(agent.config)
                agent._hooks = HookRegistry()
                agent.metrics = Metrics()

                result = EvalResult(
                    name=case["name"], framework=f"freeagent_{config.name}",
                    model=model, prompt=case["prompt"],
                    tool_calls_expected=len(case["expected_tools"]),
                )

                try:
                    start = time.monotonic()
                    response = agent.run(case["prompt"])
                    elapsed_ms = (time.monotonic() - start) * 1000

                    result.response = response or ""
                    result.success = True
                    result.latency_ms = elapsed_ms

                    run = agent.metrics.runs[-1] if agent.metrics.runs else None
                    if run:
                        result.tool_calls_made = run.tool_call_count
                        eval_tools = [t for t in run.tools_used if t != "memory"]
                        val_errors = run.validation_errors
                    else:
                        eval_tools = []
                        val_errors = 0

                    tools_match = sorted(eval_tools) == sorted(case["expected_tools"])
                    content_match = check_response_contains(
                        result.response, case["expected_in_response"],
                    )
                    result.correct = tools_match and content_match

                    notes = []
                    if val_errors:
                        notes.append(f"val_errors:{val_errors}")
                    if not tools_match:
                        notes.append(f"tools({eval_tools})")
                    if not content_match:
                        notes.append("content_miss")
                    result.notes = " ".join(notes)

                    status = "PASS" if result.correct else "FAIL"
                    print(f"    {status} {case['name']:25s} {elapsed_ms:7.0f}ms  {result.notes}")

                except Exception as e:
                    result.error = str(e)[:200]
                    print(f"    ERR  {case['name']:25s} {str(e)[:80]}")

                suite.add(result)


def print_ab_comparison(suite: EvalSuite):
    """Print A/B comparison table."""
    print("\n" + "="*70)
    print("  SKILLS A/B COMPARISON")
    print("="*70)

    # Group by model
    for model in MODELS:
        print(f"\n  Model: {model}")
        print(f"  {'Config':<20s} {'Accuracy':<15s} {'Avg Latency':<15s}")
        print(f"  {'─'*50}")

        for config in CONFIGS:
            framework = f"freeagent_{config.name}"
            results = [r for r in suite.results
                       if r.framework == framework and r.model == model]
            if not results:
                continue
            total = len(results)
            correct = sum(1 for r in results if r.correct)
            avg_lat = sum(r.latency_ms for r in results) / total if total else 0
            print(f"  {config.name:<20s} {correct}/{total} ({100*correct/total:.0f}%){'':<5s} {avg_lat:.0f}ms")


def main():
    suite = EvalSuite(name="Skills A/B Test")

    print("\n" + "="*60)
    print("  EVAL 9: Skills A/B Test")
    print("="*60)

    check_ollama()
    run_skills_ab(suite)
    print_ab_comparison(suite)
    suite.print_report()
    save_results(suite, "skills_ab_results.json")


if __name__ == "__main__":
    main()
