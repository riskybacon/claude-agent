"""Token-based cost estimation for Anthropic models."""

from typing import Final

# Per-million-token prices in USD: (input, output, cache_read, cache_creation)
_PRICES: Final[dict[str, tuple[float, float, float, float]]] = {
    "claude-sonnet-4-6": (3.0, 15.0, 0.30, 3.75),
    "claude-haiku-4-5-20251001": (0.80, 4.0, 0.08, 1.0),
    "claude-opus-4-7": (15.0, 75.0, 1.50, 18.75),
}

_SONNET_FALLBACK: Final = _PRICES["claude-sonnet-4-6"]


def estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
) -> float:
    """Return estimated cost in USD for the given token counts and model."""
    p_in, p_out, p_cr, p_cc = _PRICES.get(model, _SONNET_FALLBACK)
    m = 1_000_000
    return (
        input_tokens * p_in / m
        + output_tokens * p_out / m
        + cache_read_tokens * p_cr / m
        + cache_creation_tokens * p_cc / m
    )
