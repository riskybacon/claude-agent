"""Tests for the check_cost tool."""

import re

import pytest

from claude_agent.tools import ToolContext
from claude_agent.tools.cost import CHECK_COST_TOOL
from tests.fakes import FakeSession


def _ctx(model: str = "claude-sonnet-4-6") -> ToolContext:
    """Return a ToolContext wrapping a fresh FakeSession."""
    return ToolContext(session=FakeSession(model=model))


def _extract_dollar(text: str) -> float:
    """Pull the first $X.XXXX amount from text."""
    m = re.search(r"\$(\d+\.\d+)", text)
    return float(m.group(1)) if m else 0.0


def test_check_cost_tool_has_correct_name() -> None:
    """Tool name must be 'check_cost' so Claude can call it by name."""
    assert CHECK_COST_TOOL.name == "check_cost"


def test_check_cost_returns_string() -> None:
    """Tool function must return a plain string."""
    result = CHECK_COST_TOOL.function({}, _ctx())
    assert isinstance(result, str)


def test_check_cost_zero_when_no_tokens() -> None:
    """Zero tokens → $0.0000 reported."""
    result = CHECK_COST_TOOL.function({}, _ctx())
    assert _extract_dollar(result) == pytest.approx(0.0)


def test_check_cost_reports_input_token_cost() -> None:
    """1M Sonnet input tokens → $3.00 reported."""
    ctx = _ctx()
    ctx.session.input_tokens = 1_000_000
    result = CHECK_COST_TOOL.function({}, ctx)
    assert _extract_dollar(result) == pytest.approx(3.0)


def test_check_cost_reports_token_counts() -> None:
    """Token counts appear in the output."""
    ctx = _ctx()
    ctx.session.input_tokens = 500
    ctx.session.output_tokens = 100
    result = CHECK_COST_TOOL.function({}, ctx)
    assert "500" in result
    assert "100" in result


def test_check_cost_reflects_session_model() -> None:
    """Opus costs more than Haiku for the same token count."""
    haiku_ctx = _ctx(model="claude-haiku-4-5-20251001")
    opus_ctx = _ctx(model="claude-opus-4-7")
    haiku_ctx.session.input_tokens = 1_000_000
    opus_ctx.session.input_tokens = 1_000_000
    r_haiku = CHECK_COST_TOOL.function({}, haiku_ctx)
    r_opus = CHECK_COST_TOOL.function({}, opus_ctx)
    assert _extract_dollar(r_haiku) < _extract_dollar(r_opus)


def test_check_cost_reads_live_session_state() -> None:
    """Tool sees token counts mutated after the context was created."""
    ctx = _ctx()
    ctx.session.input_tokens = 1_000_000
    result = CHECK_COST_TOOL.function({}, ctx)
    assert _extract_dollar(result) == pytest.approx(3.0)
