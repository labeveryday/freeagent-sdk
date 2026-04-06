"""
FreeAgent Evaluation 10: Memory Tool Usability Test

Tests whether each model can correctly use the single memory tool
with its action parameter pattern.

Tests:
1. "Remember X" → model calls memory(action="write", ...)
2. "What is X?" → model calls memory(action="read", ...) or memory(action="search", ...)
3. "Save a note" → model calls memory(action="write", ...)
4. "What notes do I have?" → model calls memory(action="list")

Records: did the model use the memory tool? Right action? Valid args?
"""

import json
import time
import tempfile
import shutil
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from eval_utils import (
    EvalResult, EvalSuite, MODELS,
    check_ollama, save_results,
)

sys.path.insert(0, str(Path(__file__).parent.parent))
from freeagent import Agent


CASES = [
    {
        "name": "write_favorite_team",
        "prompt": "Remember that my favorite team is the Lakers. Save this to memory.",
        "expected_action": "write",
        "verify_fn": "check_write_lakers",
        "pre_populate": False,
    },
    {
        "name": "read_favorite_team",
        "prompt": "What's my favorite team? Check your memory.",
        "expected_action": "read",  # or search
        "verify_fn": "check_response_lakers",
        "pre_populate": True,
        "pre_populate_file": "favorites.md",
        "pre_populate_content": "Favorite team: Lakers",
    },
    {
        "name": "write_note",
        "prompt": "Save a note that I need to check the Celtics schedule tomorrow.",
        "expected_action": "write",
        "verify_fn": "check_write_celtics",
        "pre_populate": False,
    },
    {
        "name": "list_notes",
        "prompt": "What memory files do I have? List everything.",
        "expected_action": "list",
        "verify_fn": "check_list_response",
        "pre_populate": True,
        "pre_populate_file": "tasks.md",
        "pre_populate_content": "Check Celtics schedule",
    },
    {
        "name": "search_memory",
        "prompt": "Search my memory for anything about the Celtics.",
        "expected_action": "search",
        "verify_fn": "check_search_celtics",
        "pre_populate": True,
        "pre_populate_file": "notes.md",
        "pre_populate_content": "Need to check the Celtics schedule\nAlso check Lakers game times",
    },
]

SYSTEM = "You are a helpful assistant with memory capabilities. Use the memory tool to store and retrieve information."


def check_write_lakers(agent, response):
    """Verify that 'lakers' was written to memory."""
    for path in Path(agent.memory._dir).glob("*.md"):
        if path.name == "MEMORY.md":
            continue
        content = path.read_text().lower()
        if "lakers" in content:
            return True, "lakers found in memory"
    return False, "lakers NOT found in any memory file"


def check_response_lakers(agent, response):
    """Verify response mentions Lakers."""
    if "lakers" in response.lower():
        return True, "response mentions lakers"
    return False, f"response doesn't mention lakers: {response[:100]}"


def check_write_celtics(agent, response):
    """Verify that celtics/schedule was written to memory."""
    for path in Path(agent.memory._dir).glob("*.md"):
        if path.name == "MEMORY.md":
            continue
        content = path.read_text().lower()
        if "celtics" in content:
            return True, "celtics found in memory"
    return False, "celtics NOT found in any memory file"


def check_list_response(agent, response):
    """Verify the model listed memory files."""
    # Response should mention at least one file name
    if any(w in response.lower() for w in ["tasks", "memory", ".md", "files"]):
        return True, "listed files"
    return False, f"no file listing detected: {response[:100]}"


def check_search_celtics(agent, response):
    """Verify the model searched and found celtics."""
    if "celtics" in response.lower():
        return True, "search found celtics"
    return False, f"search didn't find celtics: {response[:100]}"


VERIFY_FNS = {
    "check_write_lakers": check_write_lakers,
    "check_response_lakers": check_response_lakers,
    "check_write_celtics": check_write_celtics,
    "check_list_response": check_list_response,
    "check_search_celtics": check_search_celtics,
}


def run_memory_usability(suite: EvalSuite):
    """Run memory usability tests across all models."""
    for model in MODELS:
        print(f"\n  FreeAgent Memory / {model}")

        for case in CASES:
            # Fresh temp dir per case
            temp_dir = tempfile.mkdtemp(prefix="freeagent_eval_mem_")

            try:
                agent = Agent(
                    model=model,
                    system_prompt=SYSTEM,
                    tools=[],  # memory tool auto-added
                    memory_dir=temp_dir,
                )

                # Pre-populate memory if needed
                if case.get("pre_populate"):
                    agent.memory.write(
                        case["pre_populate_file"],
                        case["pre_populate_content"],
                        meta={
                            "name": Path(case["pre_populate_file"]).stem,
                            "type": "custom",
                            "description": case["pre_populate_content"][:50],
                        },
                    )

                result = EvalResult(
                    name=case["name"], framework="freeagent_memory",
                    model=model, prompt=case["prompt"],
                )

                start = time.monotonic()
                response = agent.run(case["prompt"])
                elapsed_ms = (time.monotonic() - start) * 1000

                result.response = response or ""
                result.success = True
                result.latency_ms = elapsed_ms

                run = agent.metrics.runs[-1] if agent.metrics.runs else None

                # Check if memory tool was called
                memory_calls = []
                if run:
                    memory_calls = [tc for tc in run.tool_calls if tc.name == "memory"]
                    result.tool_calls_made = len(memory_calls)

                used_memory = len(memory_calls) > 0

                # Check action correctness
                correct_action = False
                actual_actions = []
                for mc in memory_calls:
                    action = mc.args.get("action", "unknown")
                    actual_actions.append(action)
                    if action == case["expected_action"]:
                        correct_action = True
                    # read/search are interchangeable for retrieval
                    if case["expected_action"] in ("read", "search") and action in ("read", "search"):
                        correct_action = True

                # Run verification function
                verify_fn = VERIFY_FNS[case["verify_fn"]]
                verified, verify_msg = verify_fn(agent, response)

                result.correct = used_memory and verified

                # Build detailed notes for failure analysis
                notes = []
                if not used_memory:
                    notes.append("NO_MEMORY_CALL")
                elif not correct_action:
                    notes.append(f"wrong_action({actual_actions})")
                if not verified:
                    notes.append(f"verify_fail({verify_msg})")
                if run and run.validation_errors:
                    notes.append(f"val_errors:{run.validation_errors}")
                result.notes = " ".join(notes)

                status = "PASS" if result.correct else "FAIL"
                print(f"    {status} {case['name']:25s} {elapsed_ms:7.0f}ms  "
                      f"memory_called:{used_memory}  actions:{actual_actions}  "
                      f"{result.notes}")

            except Exception as e:
                result.error = str(e)[:200]
                print(f"    ERR  {case['name']:25s} {str(e)[:80]}")
                suite.add(result)
                continue
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

            suite.add(result)


def print_memory_summary(suite: EvalSuite):
    """Print memory usability summary."""
    print("\n" + "="*70)
    print("  MEMORY TOOL USABILITY SUMMARY")
    print("="*70)

    for model in MODELS:
        results = [r for r in suite.results if r.model == model]
        if not results:
            continue
        total = len(results)
        correct = sum(1 for r in results if r.correct)
        used_tool = sum(1 for r in results if r.tool_calls_made > 0)

        print(f"\n  {model}")
        print(f"    Used memory tool: {used_tool}/{total}")
        print(f"    Correct result:   {correct}/{total}")

        # Show failure modes
        failures = [r for r in results if not r.correct]
        for f in failures:
            print(f"    FAIL: {f.name} — {f.notes}")


def main():
    suite = EvalSuite(name="Memory Tool Usability")

    print("\n" + "="*60)
    print("  EVAL 10: Memory Tool Usability")
    print("="*60)

    check_ollama()
    run_memory_usability(suite)
    print_memory_summary(suite)
    suite.print_report()
    save_results(suite, "memory_usability_results.json")


if __name__ == "__main__":
    main()
