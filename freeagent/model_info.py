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
        """Models under 3B params — skills/memory can overwhelm them."""
        return 0 < self.parameter_count < 3_000_000_000

    @property
    def is_medium(self) -> bool:
        """Models 3B-14B — sweet spot for defaults."""
        return 3_000_000_000 <= self.parameter_count < 14_000_000_000

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
