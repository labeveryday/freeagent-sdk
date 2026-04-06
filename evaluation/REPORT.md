# FreeAgent SDK — Baseline Evaluation Report

Pre-framework baseline comparing raw Ollama API vs Strands Agents SDK.
These results establish the performance floor that FreeAgent must beat.

**Models tested:** qwen3:8b, qwen3:4b, llama3.1:latest

## Baseline Chat (No Tools)

| Framework / Model | Success Rate | Accuracy | Avg Latency | Avg TPS |
|---|---|---|---|---|
| ollama_raw / qwen3:8b | 5/5 (100%) | 5/5 (100%) | 12291.2ms | 28.7 |
| ollama_raw / qwen3:4b | 5/5 (100%) | 5/5 (100%) | 26040.9ms | 48.4 |
| ollama_raw / llama3.1:latest | 5/5 (100%) | 4/5 (80%) | 2484.5ms | 33.2 |
| strands / qwen3:8b | 5/5 (100%) | 5/5 (100%) | 13544.0ms | N/A |
| strands / qwen3:4b | 5/5 (100%) | 5/5 (100%) | 12841.1ms | N/A |
| strands / llama3.1:latest | 5/5 (100%) | 4/5 (80%) | 2448.4ms | N/A |

<details>
<summary>Detailed Results (30 cases)</summary>

| Case | Framework | Model | Pass | Latency | TPS | Error |
|---|---|---|---|---|---|---|
| factual_simple | ollama_raw | qwen3:8b | PASS | 9358ms | 28.0 |  |
| factual_reasoning | ollama_raw | qwen3:8b | PASS | 10861ms | 28.7 |  |
| code_generation | ollama_raw | qwen3:8b | PASS | 22070ms | 28.9 |  |
| multi_step_reasoning | ollama_raw | qwen3:8b | PASS | 13028ms | 29.0 |  |
| instruction_following | ollama_raw | qwen3:8b | PASS | 6139ms | 29.0 |  |
| factual_simple | ollama_raw | qwen3:4b | PASS | 7448ms | 49.4 |  |
| factual_reasoning | ollama_raw | qwen3:4b | PASS | 7575ms | 49.3 |  |
| code_generation | ollama_raw | qwen3:4b | PASS | 67451ms | 46.2 |  |
| multi_step_reasoning | ollama_raw | qwen3:4b | PASS | 10984ms | 49.2 |  |
| instruction_following | ollama_raw | qwen3:4b | PASS | 36746ms | 48.0 |  |
| factual_simple | ollama_raw | llama3.1:latest | PASS | 7686ms | 35.0 |  |
| factual_reasoning | ollama_raw | llama3.1:latest | PASS | 919ms | 32.7 |  |
| code_generation | ollama_raw | llama3.1:latest | PASS | 949ms | 32.8 |  |
| multi_step_reasoning | ollama_raw | llama3.1:latest | FAIL | 1622ms | 32.6 |  |
| instruction_following | ollama_raw | llama3.1:latest | PASS | 1247ms | 33.0 |  |
| factual_simple | strands | qwen3:8b | PASS | 17931ms | - |  |
| factual_reasoning | strands | qwen3:8b | PASS | 11338ms | - |  |
| code_generation | strands | qwen3:8b | PASS | 19433ms | - |  |
| multi_step_reasoning | strands | qwen3:8b | PASS | 12413ms | - |  |
| instruction_following | strands | qwen3:8b | PASS | 6605ms | - |  |
| factual_simple | strands | qwen3:4b | PASS | 6735ms | - |  |
| factual_reasoning | strands | qwen3:4b | PASS | 7765ms | - |  |
| code_generation | strands | qwen3:4b | PASS | 9704ms | - |  |
| multi_step_reasoning | strands | qwen3:4b | PASS | 12604ms | - |  |
| instruction_following | strands | qwen3:4b | PASS | 27397ms | - |  |
| factual_simple | strands | llama3.1:latest | PASS | 7857ms | - |  |
| factual_reasoning | strands | llama3.1:latest | PASS | 974ms | - |  |
| code_generation | strands | llama3.1:latest | PASS | 957ms | - |  |
| multi_step_reasoning | strands | llama3.1:latest | FAIL | 1182ms | - |  |
| instruction_following | strands | llama3.1:latest | PASS | 1273ms | - |  |

</details>

## Tool Calling Baseline

| Framework / Model | Success Rate | Accuracy | Avg Latency | Avg TPS |
|---|---|---|---|---|
| ollama_raw / qwen3:8b | 7/8 (88%) | 6/8 (75%) | 21182.7ms | 28.9 |
| ollama_raw / qwen3:4b | 8/8 (100%) | 6/8 (75%) | 30198.5ms | 48.1 |
| ollama_raw / llama3.1:latest | 8/8 (100%) | 6/8 (75%) | 5223.9ms | 32.5 |
| strands / qwen3:8b | 8/8 (100%) | 7/8 (88%) | 24404.2ms | N/A |
| strands / qwen3:4b | 8/8 (100%) | 7/8 (88%) | 33477.2ms | N/A |
| strands / llama3.1:latest | 8/8 (100%) | 6/8 (75%) | 5015.1ms | N/A |

**Errors (ollama_raw / qwen3:8b):**
- `timed out`

<details>
<summary>Detailed Results (48 cases)</summary>

| Case | Framework | Model | Pass | Latency | TPS | Error |
|---|---|---|---|---|---|---|
| single_weather | ollama_raw | qwen3:8b | PASS | 26729ms | 29.0 |  |
| single_calc | ollama_raw | qwen3:8b | FAIL | 10709ms | 29.1 |  |
| single_convert | ollama_raw | qwen3:8b | PASS | 13101ms | 28.9 |  |
| tool_selection | ollama_raw | qwen3:8b | PASS | 20838ms | 28.9 |  |
| multi_step_convert | ollama_raw | qwen3:8b | ERR | 0ms | - | timed out |
| multi_tool_compare | ollama_raw | qwen3:8b | PASS | 40229ms | 28.8 |  |
| tool_plus_calc | ollama_raw | qwen3:8b | PASS | 11682ms | 29.2 |  |
| chained_reasoning | ollama_raw | qwen3:8b | PASS | 46173ms | 28.7 |  |
| single_weather | ollama_raw | qwen3:4b | PASS | 11536ms | 49.4 |  |
| single_calc | ollama_raw | qwen3:4b | FAIL | 11850ms | 49.1 |  |
| single_convert | ollama_raw | qwen3:4b | PASS | 13544ms | 48.9 |  |
| tool_selection | ollama_raw | qwen3:4b | PASS | 13195ms | 48.7 |  |
| multi_step_convert | ollama_raw | qwen3:4b | PASS | 55198ms | 46.5 |  |
| multi_tool_compare | ollama_raw | qwen3:4b | PASS | 18159ms | 48.5 |  |
| tool_plus_calc | ollama_raw | qwen3:4b | PASS | 13692ms | 48.7 |  |
| chained_reasoning | ollama_raw | qwen3:4b | FAIL | 104415ms | 45.0 |  |
| single_weather | ollama_raw | llama3.1:latest | PASS | 9951ms | 32.4 |  |
| single_calc | ollama_raw | llama3.1:latest | FAIL | 2424ms | 32.8 |  |
| single_convert | ollama_raw | llama3.1:latest | PASS | 2857ms | 32.9 |  |
| tool_selection | ollama_raw | llama3.1:latest | PASS | 6721ms | 31.8 |  |
| multi_step_convert | ollama_raw | llama3.1:latest | PASS | 4325ms | 32.4 |  |
| multi_tool_compare | ollama_raw | llama3.1:latest | FAIL | 8301ms | 32.0 |  |
| tool_plus_calc | ollama_raw | llama3.1:latest | PASS | 2674ms | 33.4 |  |
| chained_reasoning | ollama_raw | llama3.1:latest | PASS | 4539ms | 32.3 |  |
| single_weather | strands | qwen3:8b | PASS | 32030ms | - |  |
| single_calc | strands | qwen3:8b | FAIL | 11035ms | - |  |
| single_convert | strands | qwen3:8b | PASS | 12010ms | - |  |
| tool_selection | strands | qwen3:8b | PASS | 16594ms | - |  |
| multi_step_convert | strands | qwen3:8b | PASS | 22714ms | - |  |
| multi_tool_compare | strands | qwen3:8b | PASS | 28660ms | - |  |
| tool_plus_calc | strands | qwen3:8b | PASS | 17177ms | - |  |
| chained_reasoning | strands | qwen3:8b | PASS | 55014ms | - |  |
| single_weather | strands | qwen3:4b | PASS | 13100ms | - |  |
| single_calc | strands | qwen3:4b | PASS | 12273ms | - |  |
| single_convert | strands | qwen3:4b | PASS | 15587ms | - |  |
| tool_selection | strands | qwen3:4b | PASS | 15712ms | - |  |
| multi_step_convert | strands | qwen3:4b | PASS | 49853ms | - |  |
| multi_tool_compare | strands | qwen3:4b | PASS | 29258ms | - |  |
| tool_plus_calc | strands | qwen3:4b | PASS | 11762ms | - |  |
| chained_reasoning | strands | qwen3:4b | FAIL | 120273ms | - |  |
| single_weather | strands | llama3.1:latest | PASS | 9354ms | - |  |
| single_calc | strands | llama3.1:latest | FAIL | 2383ms | - |  |
| single_convert | strands | llama3.1:latest | PASS | 2883ms | - |  |
| tool_selection | strands | llama3.1:latest | PASS | 7478ms | - |  |
| multi_step_convert | strands | llama3.1:latest | FAIL | 4317ms | - |  |
| multi_tool_compare | strands | llama3.1:latest | PASS | 6599ms | - |  |
| tool_plus_calc | strands | llama3.1:latest | PASS | 2708ms | - |  |
| chained_reasoning | strands | llama3.1:latest | PASS | 4399ms | - |  |

</details>

## Multi-Turn Tool Calling

| Framework / Model | Success Rate | Accuracy | Avg Latency | Avg TPS |
|---|---|---|---|---|
| ollama_raw / qwen3:8b | 15/15 (100%) | 14/15 (93%) | 13872.5ms | 29.0 |
| ollama_raw / qwen3:4b | 15/15 (100%) | 14/15 (93%) | 17692.3ms | 48.4 |
| ollama_raw / llama3.1:latest | 15/15 (100%) | 13/15 (87%) | 3601.2ms | 33.2 |
| strands / qwen3:8b | 15/15 (100%) | 14/15 (93%) | 14617.3ms | N/A |
| strands / qwen3:4b | 15/15 (100%) | 15/15 (100%) | 15035.5ms | N/A |
| strands / llama3.1:latest | 15/15 (100%) | 13/15 (87%) | 3571.6ms | N/A |

<details>
<summary>Detailed Results (90 cases)</summary>

| Case | Framework | Model | Pass | Latency | TPS | Error |
|---|---|---|---|---|---|---|
| weather_then_convert_turn1 | ollama_raw | qwen3:8b | PASS | 15350ms | 29.2 |  |
| weather_then_convert_turn2 | ollama_raw | qwen3:8b | PASS | 20535ms | 28.9 |  |
| compare_two_cities_turn1 | ollama_raw | qwen3:8b | PASS | 12131ms | 29.0 |  |
| compare_two_cities_turn2 | ollama_raw | qwen3:8b | PASS | 14743ms | 29.0 |  |
| compare_two_cities_turn3 | ollama_raw | qwen3:8b | PASS | 5445ms | 29.1 |  |
| chained_conversion_and_calc_turn1 | ollama_raw | qwen3:8b | PASS | 11759ms | 29.2 |  |
| chained_conversion_and_calc_turn2 | ollama_raw | qwen3:8b | PASS | 16502ms | 28.8 |  |
| context_retention_no_tools_turn1 | ollama_raw | qwen3:8b | PASS | 9105ms | 29.2 |  |
| context_retention_no_tools_turn2 | ollama_raw | qwen3:8b | FAIL | 9886ms | 28.8 |  |
| three_city_itinerary_turn1 | ollama_raw | qwen3:8b | PASS | 8887ms | 28.9 |  |
| three_city_itinerary_turn2 | ollama_raw | qwen3:8b | PASS | 12611ms | 28.9 |  |
| three_city_itinerary_turn3 | ollama_raw | qwen3:8b | PASS | 12246ms | 28.9 |  |
| three_city_itinerary_turn4 | ollama_raw | qwen3:8b | PASS | 11866ms | 28.7 |  |
| correction_handling_turn1 | ollama_raw | qwen3:8b | PASS | 27297ms | 28.8 |  |
| correction_handling_turn2 | ollama_raw | qwen3:8b | PASS | 19723ms | 28.8 |  |
| weather_then_convert_turn1 | ollama_raw | qwen3:4b | PASS | 17931ms | 48.8 |  |
| weather_then_convert_turn2 | ollama_raw | qwen3:4b | PASS | 18884ms | 48.3 |  |
| compare_two_cities_turn1 | ollama_raw | qwen3:4b | PASS | 9093ms | 49.2 |  |
| compare_two_cities_turn2 | ollama_raw | qwen3:4b | PASS | 13090ms | 48.8 |  |
| compare_two_cities_turn3 | ollama_raw | qwen3:4b | PASS | 6811ms | 48.8 |  |
| chained_conversion_and_calc_turn1 | ollama_raw | qwen3:4b | PASS | 38202ms | 47.6 |  |
| chained_conversion_and_calc_turn2 | ollama_raw | qwen3:4b | PASS | 16596ms | 48.5 |  |
| context_retention_no_tools_turn1 | ollama_raw | qwen3:4b | PASS | 7719ms | 49.0 |  |
| context_retention_no_tools_turn2 | ollama_raw | qwen3:4b | FAIL | 36682ms | 47.3 |  |
| three_city_itinerary_turn1 | ollama_raw | qwen3:4b | PASS | 14526ms | 48.7 |  |
| three_city_itinerary_turn2 | ollama_raw | qwen3:4b | PASS | 17346ms | 48.4 |  |
| three_city_itinerary_turn3 | ollama_raw | qwen3:4b | PASS | 15468ms | 48.1 |  |
| three_city_itinerary_turn4 | ollama_raw | qwen3:4b | PASS | 9126ms | 48.2 |  |
| correction_handling_turn1 | ollama_raw | qwen3:4b | PASS | 24657ms | 48.2 |  |
| correction_handling_turn2 | ollama_raw | qwen3:4b | PASS | 19255ms | 48.2 |  |
| weather_then_convert_turn1 | ollama_raw | llama3.1:latest | PASS | 9789ms | 33.1 |  |
| weather_then_convert_turn2 | ollama_raw | llama3.1:latest | PASS | 2890ms | 32.8 |  |
| compare_two_cities_turn1 | ollama_raw | llama3.1:latest | PASS | 2598ms | 33.7 |  |
| compare_two_cities_turn2 | ollama_raw | llama3.1:latest | PASS | 2420ms | 33.4 |  |
| compare_two_cities_turn3 | ollama_raw | llama3.1:latest | PASS | 3532ms | 32.7 |  |
| chained_conversion_and_calc_turn1 | ollama_raw | llama3.1:latest | FAIL | 3564ms | 32.5 |  |
| chained_conversion_and_calc_turn2 | ollama_raw | llama3.1:latest | FAIL | 3278ms | 33.2 |  |
| context_retention_no_tools_turn1 | ollama_raw | llama3.1:latest | PASS | 2608ms | 33.2 |  |
| context_retention_no_tools_turn2 | ollama_raw | llama3.1:latest | PASS | 2734ms | 32.4 |  |
| three_city_itinerary_turn1 | ollama_raw | llama3.1:latest | PASS | 3571ms | 33.3 |  |
| three_city_itinerary_turn2 | ollama_raw | llama3.1:latest | PASS | 2667ms | 33.4 |  |
| three_city_itinerary_turn3 | ollama_raw | llama3.1:latest | PASS | 2651ms | 33.2 |  |
| three_city_itinerary_turn4 | ollama_raw | llama3.1:latest | PASS | 6733ms | 32.1 |  |
| correction_handling_turn1 | ollama_raw | llama3.1:latest | PASS | 2196ms | 34.6 |  |
| correction_handling_turn2 | ollama_raw | llama3.1:latest | PASS | 2788ms | 33.7 |  |
| weather_then_convert_turn1 | strands | qwen3:8b | PASS | 16246ms | - |  |
| weather_then_convert_turn2 | strands | qwen3:8b | PASS | 14804ms | - |  |
| compare_two_cities_turn1 | strands | qwen3:8b | PASS | 10353ms | - |  |
| compare_two_cities_turn2 | strands | qwen3:8b | PASS | 16847ms | - |  |
| compare_two_cities_turn3 | strands | qwen3:8b | PASS | 5755ms | - |  |
| chained_conversion_and_calc_turn1 | strands | qwen3:8b | PASS | 10850ms | - |  |
| chained_conversion_and_calc_turn2 | strands | qwen3:8b | PASS | 21978ms | - |  |
| context_retention_no_tools_turn1 | strands | qwen3:8b | PASS | 10660ms | - |  |
| context_retention_no_tools_turn2 | strands | qwen3:8b | FAIL | 6380ms | - |  |
| three_city_itinerary_turn1 | strands | qwen3:8b | PASS | 13828ms | - |  |
| three_city_itinerary_turn2 | strands | qwen3:8b | PASS | 14067ms | - |  |
| three_city_itinerary_turn3 | strands | qwen3:8b | PASS | 11530ms | - |  |
| three_city_itinerary_turn4 | strands | qwen3:8b | PASS | 15759ms | - |  |
| correction_handling_turn1 | strands | qwen3:8b | PASS | 30482ms | - |  |
| correction_handling_turn2 | strands | qwen3:8b | PASS | 19720ms | - |  |
| weather_then_convert_turn1 | strands | qwen3:4b | PASS | 16682ms | - |  |
| weather_then_convert_turn2 | strands | qwen3:4b | PASS | 13450ms | - |  |
| compare_two_cities_turn1 | strands | qwen3:4b | PASS | 7229ms | - |  |
| compare_two_cities_turn2 | strands | qwen3:4b | PASS | 12284ms | - |  |
| compare_two_cities_turn3 | strands | qwen3:4b | PASS | 15751ms | - |  |
| chained_conversion_and_calc_turn1 | strands | qwen3:4b | PASS | 29030ms | - |  |
| chained_conversion_and_calc_turn2 | strands | qwen3:4b | PASS | 22146ms | - |  |
| context_retention_no_tools_turn1 | strands | qwen3:4b | PASS | 9156ms | - |  |
| context_retention_no_tools_turn2 | strands | qwen3:4b | PASS | 11471ms | - |  |
| three_city_itinerary_turn1 | strands | qwen3:4b | PASS | 8559ms | - |  |
| three_city_itinerary_turn2 | strands | qwen3:4b | PASS | 16905ms | - |  |
| three_city_itinerary_turn3 | strands | qwen3:4b | PASS | 18720ms | - |  |
| three_city_itinerary_turn4 | strands | qwen3:4b | PASS | 5600ms | - |  |
| correction_handling_turn1 | strands | qwen3:4b | PASS | 24168ms | - |  |
| correction_handling_turn2 | strands | qwen3:4b | PASS | 14381ms | - |  |
| weather_then_convert_turn1 | strands | llama3.1:latest | PASS | 10070ms | - |  |
| weather_then_convert_turn2 | strands | llama3.1:latest | PASS | 2950ms | - |  |
| compare_two_cities_turn1 | strands | llama3.1:latest | PASS | 2651ms | - |  |
| compare_two_cities_turn2 | strands | llama3.1:latest | PASS | 2447ms | - |  |
| compare_two_cities_turn3 | strands | llama3.1:latest | PASS | 3450ms | - |  |
| chained_conversion_and_calc_turn1 | strands | llama3.1:latest | FAIL | 3444ms | - |  |
| chained_conversion_and_calc_turn2 | strands | llama3.1:latest | FAIL | 3328ms | - |  |
| context_retention_no_tools_turn1 | strands | llama3.1:latest | PASS | 2642ms | - |  |
| context_retention_no_tools_turn2 | strands | llama3.1:latest | PASS | 2718ms | - |  |
| three_city_itinerary_turn1 | strands | llama3.1:latest | PASS | 2822ms | - |  |
| three_city_itinerary_turn2 | strands | llama3.1:latest | PASS | 2683ms | - |  |
| three_city_itinerary_turn3 | strands | llama3.1:latest | PASS | 2697ms | - |  |
| three_city_itinerary_turn4 | strands | llama3.1:latest | PASS | 6596ms | - |  |
| correction_handling_turn1 | strands | llama3.1:latest | PASS | 2229ms | - |  |
| correction_handling_turn2 | strands | llama3.1:latest | PASS | 2845ms | - |  |

</details>

---

## Key Takeaways

*To be filled in after reviewing results.*

### What FreeAgent needs to beat:
- Raw Ollama API latency (the floor — no framework overhead)
- Strands accuracy on tool calling (the comparison point)
- MCP integration reliability with real-world tools
