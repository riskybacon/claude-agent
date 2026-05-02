"""Tests for cost estimation."""

import pytest

from claude_agent.cli.pricing import estimate_cost


def test_sonnet_input_tokens() -> None:
    """$3/M input tokens for Sonnet."""
    cost = estimate_cost(model="claude-sonnet-4-6", input_tokens=1_000_000, output_tokens=0)
    assert cost == pytest.approx(3.0)


def test_sonnet_output_tokens() -> None:
    """$15/M output tokens for Sonnet."""
    cost = estimate_cost(model="claude-sonnet-4-6", input_tokens=0, output_tokens=1_000_000)
    assert cost == pytest.approx(15.0)


def test_sonnet_cache_read_cheaper_than_input() -> None:
    """Cache read tokens cost less than regular input tokens."""
    cache_read = estimate_cost(
        model="claude-sonnet-4-6", input_tokens=0, output_tokens=0, cache_read_tokens=1_000_000
    )
    full_input = estimate_cost(model="claude-sonnet-4-6", input_tokens=1_000_000, output_tokens=0)
    assert cache_read < full_input


def test_sonnet_cache_creation_tokens() -> None:
    """$3.75/M cache creation tokens for Sonnet."""
    cost = estimate_cost(
        model="claude-sonnet-4-6", input_tokens=0, output_tokens=0, cache_creation_tokens=1_000_000
    )
    assert cost == pytest.approx(3.75)


def test_zero_tokens_returns_zero() -> None:
    """All-zero token counts produce zero cost."""
    cost = estimate_cost(model="claude-sonnet-4-6", input_tokens=0, output_tokens=0)
    assert cost == 0.0


def test_unknown_model_falls_back_to_sonnet_rates() -> None:
    """Unknown model IDs use Sonnet pricing as a safe fallback."""
    known = estimate_cost(
        model="claude-sonnet-4-6", input_tokens=500_000, output_tokens=500_000
    )
    unknown = estimate_cost(
        model="claude-unknown-model", input_tokens=500_000, output_tokens=500_000
    )
    assert known == pytest.approx(unknown)


def test_haiku_input_cheaper_than_sonnet() -> None:
    """Haiku input tokens are cheaper than Sonnet."""
    haiku = estimate_cost(
        model="claude-haiku-4-5-20251001", input_tokens=1_000_000, output_tokens=0
    )
    sonnet = estimate_cost(model="claude-sonnet-4-6", input_tokens=1_000_000, output_tokens=0)
    assert haiku < sonnet


def test_opus_input_more_expensive_than_sonnet() -> None:
    """Opus input tokens are more expensive than Sonnet."""
    opus = estimate_cost(model="claude-opus-4-7", input_tokens=1_000_000, output_tokens=0)
    sonnet = estimate_cost(model="claude-sonnet-4-6", input_tokens=1_000_000, output_tokens=0)
    assert opus > sonnet


def test_all_token_types_sum_correctly() -> None:
    """Cost is the sum of all four token-type costs."""
    cost = estimate_cost(
        model="claude-sonnet-4-6",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cache_read_tokens=1_000_000,
        cache_creation_tokens=1_000_000,
    )
    expected = 3.0 + 15.0 + 0.30 + 3.75
    assert cost == pytest.approx(expected)
