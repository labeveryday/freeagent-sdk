# Thesis Analysis: Does FreeAgent Rescue Real Failures?

**Date:** 2026-04-07
**Thesis:** "The framework catches what the model can't" — FreeAgent's guardrails (validator, fuzzy matching, circuit breaker, type coercion) should rescue failures that raw Ollama API cannot.

---

## Eval 12: Adversarial Rescue Test

**Setup:** 10 adversarial cases × 4 models = 40 total. Each case targets a specific guardrail (fuzzy match, type coercion, validation retry, circuit breaker, truncation). Both raw Ollama and FreeAgent run the same case.

### Results

| Outcome | Count | % |
|---------|-------|---|
| Both pass | 36 | 90% |
| Rescue (raw fails, FA passes) | 1 | 2.5% |
| Regression (raw passes, FA fails) | 1 | 2.5% |
| Both fail | 2 | 5% |

**Total rescues: 1** — qwen3:4b `loop_trap` case. Raw Ollama looped; FreeAgent passed.
**Real rescues (guardrail demonstrably fired): 0** — The one rescue had `guardrails=[]`. FreeAgent passed, but not because a guardrail intervened — the model just happened to behave differently.

**Regression: 1** — llama3.1 `type_coercion_temp`. Raw Ollama correctly converted "eighty-five degrees" to a number and called the tool. FreeAgent's llama3.1 did the math in-text instead of using the tool. The skills instruction "When you have what you need, stop calling tools" may have discouraged tool use here.

**Both fail: 2** — `precision_calc` on qwen3:8b and llama3.1. Both frameworks return "10,063" for 347×29 (correct is 10,063, but the eval expected exact match and the models paraphrase).

### Per-Model Adversarial Accuracy

| Model | Raw Ollama | FreeAgent | Delta |
|-------|-----------|-----------|-------|
| qwen3:8b | 9/10 | 9/10 | 0 |
| qwen3:4b | 9/10 | 10/10 | +1 |
| llama3.1 | 8/10 | 8/10 | 0 |
| gemma4:e2b | 10/10 | 10/10 | 0 |

### Per-Target Guardrail Analysis

| Target | Cases | Both Pass | Rescue | Regression |
|--------|-------|-----------|--------|------------|
| fuzzy_match | 12 | 12 | 0 | 0 |
| type_coercion | 4 | 3 | 0 | 1 |
| validation_retry | 4 | 2 | 0 | 0 |
| circuit_breaker | 4 | 3 | 1 | 0 |
| truncation | 4 | 4 | 0 | 0 |
| missing_field | 4 | 4 | 0 | 0 |
| wrong_arg | 4 | 4 | 0 | 0 |
| hallucinate_tool | 4 | 4 | 0 | 0 |

**Key finding:** Fuzzy matching was never needed — all 4 models correctly mapped misspelled tool names to the right tool natively. The models are smarter than expected.

---

## Eval 13: Component A/B Test

**Setup:** 4 multi-turn conversations × 4 models × 4 variants = 64 runs. Variants:
- **default** — full FreeAgent (skills + memory tool)
- **no_skills** — memory tool but no skill instructions
- **no_memory_tool** — skills but no memory tool in tool list
- **stripped** — no skills, no memory tool (bare agent)

### Per-Model Accuracy (cases passed / 4)

| Model | default | no_skills | no_memory_tool | stripped |
|-------|---------|-----------|----------------|---------|
| qwen3:8b | 75% (3/4) | 75% (3/4) | 75% (3/4) | 75% (3/4) |
| qwen3:4b | **100% (4/4)** | 75% (3/4) | **100% (4/4)** | 75% (3/4) |
| llama3.1 | **100% (4/4)** | **100% (4/4)** | 75% (3/4) | **100% (4/4)** |
| gemma4:e2b | 25% (1/4) | 50% (2/4) | 50% (2/4) | 50% (2/4) |
| **Average** | **75%** | **75%** | **75%** | **75%** |

### Which Component Hurts?

**Neither, definitively.** The averages are identical across all 4 variants (75%). The differences are per-model noise:

- **qwen3:4b:** Skills help (+25% vs no_skills). Default = best.
- **llama3.1:** Memory tool hurts (-25% vs no_memory_tool). But removing skills doesn't help.
- **gemma4:e2b:** Default is worst (25%). All other variants tie at 50%. Both skills AND memory tool hurt this tiny model.
- **qwen3:8b:** All variants identical. Framework overhead is irrelevant.

### Case-Level Failure Analysis

**`context_retention_no_tools`** — the umbrella question — fails across ALL variants for qwen3:8b and gemma4:e2b. This is a model-level failure, not framework-caused. The models can't infer "overcast → bring umbrella" regardless of framework configuration.

**`three_city_itinerary`** — fails for gemma4:e2b across ALL variants. The 2B model can't maintain state across 4 turns of tool-calling.

**`compare_two_cities`** — fails for gemma4:e2b default only. The model struggles with multi-tool comparison when skills + memory tool are both present (4 tools total overwhelm the 2B model).

---

## Eval 14: Failure Diagnostic

**Setup:** Re-ran 5 specific cases where FreeAgent previously lost to raw Ollama, with full trace capture.

### Results: All 5 Cases Passed This Time

| Case | Model | Passed | Tools Used | Guardrails Fired |
|------|-------|--------|-----------|-----------------|
| compare_two_cities_turn2 | qwen3:8b | Yes | weather×2 | None |
| compare_two_cities_turn3 | llama3.1 | Yes | calculator | None |
| context_retention_no_tools_turn2 | llama3.1 | Yes | weather | None |
| three_city_itinerary_turn4 | llama3.1 | Yes | calculator | None |
| chained_conversion_and_calc_turn1 | qwen3:4b | Yes | unit_converter | None |

**Key finding:** The failures are **non-deterministic**. Small models have inherent randomness in tool-calling and reasoning. The 6% gap between FreeAgent and raw Ollama in the Phase 14 multi-turn eval was within the noise band, not a systematic framework penalty.

### System Prompt Overhead

- System prompt: 661 chars, ~165 tokens
- Tools: 4 (3 user + 1 memory)
- Skills: 2 (general-assistant, tool-user)

At ~165 tokens, framework overhead is minimal (~4% of a 4K context). This is consistent with the design goal of <300 tokens.

### Unnecessary Tool Calls

- **llama3.1 `context_retention_no_tools_turn2`:** Called `weather` again instead of reasoning from conversation context. This is a known llama3.1 quirk — it's "tool-happy" when tools are available.
- **qwen3:8b `compare_two_cities_turn2`:** Called `weather` twice (London twice). Redundant but not harmful — got correct answer.

---

## Verdict: Does the Framework Rescue Real Failures?

### Honest Assessment

**The guardrails don't fire in practice.** Across 40 adversarial cases specifically designed to trigger them:
- Fuzzy matching: 0/12 activations (models spell tool names correctly)
- Type coercion: 0/4 activations (models handle type conversion natively)
- Validation retry: 0/4 activations
- Circuit breaker: 0/4 activations (1 rescue but no guardrail logged)
- Truncation: 0/4 activations (models handle large outputs fine)

**Zero guardrail-driven rescues in 40 adversarial cases.**

### Why?

The models tested (qwen3:8b, qwen3:4b, llama3.1:8b, gemma4:e2b) are better at tool calling than expected. Even the 2B gemma4:e2b handles fuzzy tool names, type coercion, and argument validation correctly. The guardrails were designed for a worst-case that these models don't hit.

### What FreeAgent Actually Provides

The framework's value is NOT in runtime rescue. It's in:

1. **Conversation management** — +9% multi-turn accuracy from SlidingWindow (Phase 14 data)
2. **Skills for small models** — +25% accuracy for qwen3:4b with skills enabled (Phase 10 + Phase 17 data)
3. **Consistent tool-calling interface** — same code works across 4 different models/architectures
4. **Memory persistence** — markdown-backed, human-readable agent memory
5. **Telemetry** — built-in metrics for every run, no instrumentation needed
6. **Multi-provider abstraction** — Ollama, vLLM, OpenAI-compat all work identically

### Recommendations

1. **Don't market guardrails as the primary value prop.** The data doesn't support "catches what models can't."
2. **Lead with conversation management and multi-model support.** These have measurable impact.
3. **Skills matter for small models.** Keep them but consider making them opt-out for >8B models.
4. **Memory tool adds 1 extra tool to every agent.** For tiny models (2B), this can hurt. Consider lazy-loading it only when the user asks for memory.
5. **The 87% vs 93% gap is noise, not penalty.** The failure diagnostic shows these cases are non-deterministic.
