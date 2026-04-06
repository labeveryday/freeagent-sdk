"""
Baseline Evaluation 1: Raw Chat — Ollama API vs Strands Agents

No tools, just pure chat completion. Measures:
- Latency
- Tokens per second
- Response quality/accuracy

Tests across: qwen3:8b, qwen3:4b, llama3.1:latest
"""

import json
import time
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from eval_utils import (
    EvalResult, EvalSuite, MODELS, OLLAMA_BASE_URL,
    timed_ollama_chat, extract_tps, check_response_contains,
    check_ollama, save_results, extract_strands_metrics, format_strands_metrics,
)

CASES = [
    {
        "name": "factual_simple",
        "prompt": "What is the capital of France? Answer in one sentence.",
        "expected": ["paris"],
    },
    {
        "name": "factual_reasoning",
        "prompt": "If a train travels 60 mph for 2.5 hours, how far does it travel? Show your work briefly.",
        "expected": ["150"],
    },
    {
        "name": "code_generation",
        "prompt": "Write a Python function called `is_palindrome` that checks if a string is a palindrome. Return only the code.",
        "expected": ["def is_palindrome", "return"],
    },
    {
        "name": "multi_step_reasoning",
        "prompt": "I have 3 boxes. Box A has 2 red balls. Box B has 3 blue balls. Box C has 1 red and 2 blue balls. How many total balls are there, and how many are red?",
        "expected": ["8", "3"],
    },
    {
        "name": "instruction_following",
        "prompt": "List exactly 5 programming languages that start with the letter P. Format as a numbered list.",
        "expected": ["python", "perl"],
    },
]


def run_ollama_raw(suite: EvalSuite):
    """Run cases against raw Ollama API."""
    for model in MODELS:
        print(f"\n  Raw Ollama API / {model}")
        for case in CASES:
            messages = [
                {"role": "system", "content": "You are a helpful assistant. Be concise."},
                {"role": "user", "content": case["prompt"]},
            ]

            result = EvalResult(
                name=case["name"], framework="ollama_raw",
                model=model, prompt=case["prompt"],
            )

            try:
                resp, latency_ms, tps = timed_ollama_chat(model, messages)
                content = resp.get("message", {}).get("content", "")
                eval_count, _ = extract_tps(resp)

                result.response = content
                result.success = True
                result.latency_ms = latency_ms
                result.tokens_generated = eval_count
                result.tokens_per_second = tps
                result.correct = check_response_contains(content, case["expected"])

                status = "PASS" if result.correct else "FAIL"
                print(f"    {status} {case['name']:30s} {latency_ms:7.0f}ms  {tps:5.1f} t/s  {eval_count:4d} tokens")
            except Exception as e:
                result.error = str(e)[:200]
                print(f"    ERR  {case['name']:30s} {str(e)[:80]}")

            suite.add(result)


def run_strands(suite: EvalSuite):
    """Run cases against Strands Agents with Ollama."""
    from strands import Agent
    from strands.models.ollama import OllamaModel

    for model in MODELS:
        print(f"\n  Strands Agents / {model}")

        for case in CASES:
            # Fresh agent per case — no conversation bleed
            ollama_model = OllamaModel(
                host=OLLAMA_BASE_URL,
                model_id=model,
                temperature=0.1,
            )
            agent = Agent(
                model=ollama_model,
                system_prompt="You are a helpful assistant. Be concise.",
            )

            result = EvalResult(
                name=case["name"], framework="strands",
                model=model, prompt=case["prompt"],
            )

            try:
                start = time.monotonic()
                response = agent(case["prompt"])
                elapsed_ms = (time.monotonic() - start) * 1000

                content = str(response)
                result.response = content
                result.success = True
                result.latency_ms = elapsed_ms
                result.correct = check_response_contains(content, case["expected"])

                sm = extract_strands_metrics(agent)
                result.tokens_generated = sm["total_tokens"]
                result.notes = f"cycles:{sm['cycles']} tokens:{sm['total_tokens']} in:{sm['input_tokens']} out:{sm['output_tokens']}"

                status = "PASS" if result.correct else "FAIL"
                print(f"    {status} {case['name']:30s} {elapsed_ms:7.0f}ms  {sm['cycles']} cycles  tokens:{sm['total_tokens']}")
            except Exception as e:
                result.error = str(e)[:200]
                print(f"    ERR  {case['name']:30s} {str(e)[:80]}")

            suite.add(result)


def main():
    suite = EvalSuite(name="Baseline Chat (No Tools)")

    print("\n" + "="*60)
    print("  EVAL 1: Baseline Chat — Raw Ollama vs Strands")
    print("="*60)

    check_ollama()

    print("\n-- Raw Ollama API --")
    run_ollama_raw(suite)

    print("\n-- Strands Agents --")
    run_strands(suite)

    suite.print_report()
    save_results(suite, "baseline_chat_results.json")


if __name__ == "__main__":
    main()
