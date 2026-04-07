# Multi-Turn Conversation Evaluation Report

Comparison of multi-turn conversation performance across frameworks.

## Setup

- **Test cases**: 6 multi-turn conversations (15 total turns)
- **Frameworks**: Raw Ollama API, Strands Agents, FreeAgent (old, no state), FreeAgent (conversation manager)
- **Models**: qwen3:8b, qwen3:4b, llama3.1:latest, gemma4:e2b (FreeAgent only)
- **FreeAgent conversation strategy**: SlidingWindow(max_turns=20) (default)
- **gemma4:e2b**: Uses ReactEngine (text-based ReAct) — not in native_tool_models

## Overall Accuracy (turn-level)

| Model | Raw Ollama | Strands | FreeAgent (old) | FreeAgent (conversation) | Delta vs Raw |
|-------|-----------|---------|-----------------|-------------------------|-------------|
| qwen3:8b | 93% | 73% | 78% | 87% | -6% |
| qwen3:4b | 93% | 80% | 78% | 87% | -6% |
| llama3.1:latest | 87% | 73% | 78% | 80% | -7% |
| gemma4:e2b | N/A | N/A | N/A | 80% | (new) |

## Per-Conversation Results

| Conversation | Model | Raw Ollama | Strands | FA (old) | FA (conversation) |
|-------------|-------|-----------|---------|----------|-------------------|
| weather_then_convert | qwen3:8b | PASS | FAIL | PASS | PASS |
|  | qwen3:4b | PASS | FAIL | PASS | PASS |
|  | llama3.1:latest | PASS | FAIL | PASS | PASS |
| compare_two_cities | qwen3:8b | PASS | PASS | FAIL | FAIL |
|  | qwen3:4b | PASS | PASS | PASS | PASS |
|  | llama3.1:latest | PASS | PASS | FAIL | FAIL |
| chained_conversion_and_calc | qwen3:8b | PASS | FAIL | PASS | PASS |
|  | qwen3:4b | PASS | FAIL | FAIL | FAIL |
|  | llama3.1:latest | FAIL | FAIL | PASS | PASS |
| context_retention_no_tools | qwen3:8b | FAIL | FAIL | FAIL | FAIL |
|  | qwen3:4b | FAIL | PASS | FAIL | FAIL |
|  | llama3.1:latest | PASS | PASS | FAIL | FAIL |
| three_city_itinerary | qwen3:8b | PASS | PASS | N/A | PASS |
|  | qwen3:4b | PASS | PASS | N/A | PASS |
|  | llama3.1:latest | PASS | PASS | N/A | FAIL |
| correction_handling | qwen3:8b | PASS | FAIL | N/A | PASS |
|  | qwen3:4b | PASS | FAIL | N/A | PASS |
|  | llama3.1:latest | PASS | FAIL | N/A | PASS |

## gemma4:e2b (ReactEngine)

First evaluation of ReactEngine with a real ReAct-only model (2B params).

| Conversation | Result |
|-------------|--------|
| weather_then_convert | PASS |
| compare_two_cities | PASS |
| chained_conversion_and_calc | PASS |
| context_retention_no_tools | FAIL |
| three_city_itinerary | FAIL |
| correction_handling | PASS |

## Failure Analysis

| Model | Turn | Notes |
|-------|------|-------|
| qwen3:8b | compare_two_cities_turn2 | tools_expected:['weather'] got:['weather', 'weather'] turns:2 |
| qwen3:8b | context_retention_no_tools_turn2 | content_miss turns:2 |
| qwen3:4b | chained_conversion_and_calc_turn1 | tools_expected:['unit_converter'] got:['unit_converter', 'unit_converter'] turns:1 |
| qwen3:4b | context_retention_no_tools_turn2 | content_miss turns:2 |
| llama3.1:latest | compare_two_cities_turn3 | tools_expected:[] got:['calculator'] turns:3 |
| llama3.1:latest | context_retention_no_tools_turn2 | tools_expected:[] got:['weather'] turns:2 |
| llama3.1:latest | three_city_itinerary_turn4 | tools_expected:[] got:['calculator'] turns:4 |
| gemma4:e2b | context_retention_no_tools_turn2 | react content_miss turns:2 |
| gemma4:e2b | three_city_itinerary_turn3 | react tools_expected:['weather'] got:[] content_miss turns:3 |
| gemma4:e2b | three_city_itinerary_turn4 | react content_miss turns:4 |

## Key Findings

1. **Conversation manager improves multi-turn accuracy** — FreeAgent with conversation manager (87% qwen3:8b, 87% qwen3:4b) vs old FreeAgent without state (78% both). The conversation context allows later turns to reference earlier results without restating them.

2. **FreeAgent now matches or beats Strands on multi-turn** — 87% vs 73% (qwen3:8b), 87% vs 80% (qwen3:4b), 80% vs 73% (llama3.1). Strands had the advantage of built-in conversation state; now FreeAgent does too.

3. **Raw Ollama still edges out on qwen models** (93% vs 87%) — the raw API has zero framework overhead in the system prompt, while FreeAgent adds ~300 tokens of skills+memory context that can confuse multi-turn reasoning on some cases.

4. **gemma4:e2b (ReactEngine) performs well at 80%** — matching llama3.1 accuracy despite being a 2B model using text-based ReAct instead of native tool calling. ReactEngine successfully parses tool calls from text output.

5. **Common failure mode: `context_retention_no_tools`** — all 4 models struggle with the umbrella question. Models either re-call the weather tool unnecessarily or don't include 'yes' in their response about overcast weather.

6. **llama3.1 quirk: unnecessary tool calls** — when asked to compare or rank without tools, llama3.1 sometimes calls calculator or weather anyway. This was also observed in Phase 8 integration tests.
