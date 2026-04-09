"""
Model info — auto-detect model capabilities from Ollama /api/show.

Used by Agent for auto-tuning: small models get stripped defaults,
context window is set from the model's actual limit, and engine
selection uses real capabilities instead of a hardcoded list.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx


@dataclass
class ModelInfo:
    """Detected model metadata from Ollama."""
    name: str
    parameter_count: int = 0
    parameter_size: str = ""
    context_length: int = 0
    capabilities: list[str] = field(default_factory=list)
    family: str = ""
    quantization: str = ""

    @property
    def is_small(self) -> bool:
        """
        Models that need stripped defaults to perform well.

        Includes:
        - Actual parameter count under 4B (e.g., phi3, tinyllama, qwen3:4b variants)
        - Google's "effective" models (gemma3n, gemma4:eXb) which advertise as 2B/4B
          but have 5B+ actual params and behave like the smaller variant
        - Any model in the gemma3n or gemma4 family (MoE with limited active params)

        These models are hurt by bundled skills and memory tool overhead
        (validated by eval data: gemma4:e2b 25% default vs 50% stripped).
        """
        if self.parameter_count and self.parameter_count < 4_000_000_000:
            return True
        # Google "effective" models: gemma3n:e2b, gemma4:e2b, etc.
        # These use MoE and behave like their "effective" size, not actual.
        name_lower = self.name.lower()
        if "gemma3n" in name_lower or "gemma4" in name_lower:
            # Check for :eXb pattern (e2b, e4b)
            if ":e" in name_lower and "b" in name_lower.split(":e", 1)[1][:3]:
                return True
        family_lower = self.family.lower()
        if family_lower in ("gemma3n", "gemma4"):
            # Conservative: strip for all gemma3n/4 until we have data otherwise
            return True
        return False

    @property
    def is_medium(self) -> bool:
        """Models 4B-14B — sweet spot for defaults."""
        if self.is_small:
            return False
        return 4_000_000_000 <= self.parameter_count < 14_000_000_000

    @property
    def supports_native_tools(self) -> bool:
        """Whether the model advertises tool calling support."""
        return "tools" in self.capabilities


async def fetch_model_info(model: str, base_url: str = "http://localhost:11434") -> ModelInfo | None:
    """
    Query Ollama /api/show for model metadata.

    Returns None if the model isn't found, Ollama isn't running,
    or the endpoint isn't Ollama.
    """
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(
                f"{base_url.rstrip('/')}/api/show",
                json={"name": model},
            )
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, httpx.ConnectError, ValueError):
        return None

    details = data.get("details", {})
    model_info_data = data.get("model_info", {})
    capabilities = data.get("capabilities", [])
    family = details.get("family", "")

    # Extract context length — key varies by model family
    context_length = 0
    for key, value in model_info_data.items():
        if key.endswith(".context_length") and isinstance(value, int):
            context_length = value
            break

    return ModelInfo(
        name=model,
        parameter_count=model_info_data.get("general.parameter_count", 0),
        parameter_size=details.get("parameter_size", ""),
        context_length=context_length,
        capabilities=capabilities or [],
        family=family,
        quantization=details.get("quantization_level", ""),
    )
