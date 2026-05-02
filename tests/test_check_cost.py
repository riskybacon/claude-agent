"""Tests for the check_cost tool factory."""

import re

import pytest

from claude_agent.cli.session import Session


def _session(model: str = "claude-sonnet-4-6") -> Session:
    return Session(model=model, system_prompt="s", tools=[])


def _extract_dollar(text: str) -> float:
    """Pull the first $X.XXXX amount from text."""
    m = re.search(r"\$(\d+\.\d+)", text)
    return float(m.group(1)) if m else 0.0


def test_check_cost_tool_has_correct_name() -> None:
    """Tool name must be 'check_cost' so Claude can call it by name."""
    from claude_agent.cli.cost_tool import make_check_cost_tool

    tool = make_check_cost_tool(_session())
    assert tool.name == "check_cost"


def test_check_cost_returns_string() -> None:
    """Tool function must return a plain string."""
    from claude_agent.cli.cost_tool import make_check_cost_tool

    tool = make_check_cost_tool(_session())
    result = tool.function({})
    assert isinstance(result, str)


def test_check_cost_zero_when_no_tokens() -> None:
    """Zero tokens → $0.0000 reported."""
    from claude_agent.cli.cost_tool import make_check_cost_tool

    tool = make_check_cost_tool(_session())
    result = tool.function({})
    assert _extract_dollar(result) == pytest.approx(0.0)


def test_check_cost_reports_input_token_cost() -> None:
    """1M Sonnet input tokens → $3.00 reported."""
    from claude_agent.cli.cost_tool import make_check_cost_tool

    s = _session()
    s.input_tokens = 1_000_000
    tool = make_check_cost_tool(s)
    result = tool.function({})
    assert _extract_dollar(result) == pytest.approx(3.0)


def test_check_cost_reports_token_counts() -> None:
    """Token counts appear in the output."""
    from claude_agent.cli.cost_tool import make_check_cost_tool

    s = _session()
    s.input_tokens = 500
    s.output_tokens = 100
    tool = make_check_cost_tool(s)
    result = tool.function({})
    assert "500" in result
    assert "100" in result


def test_check_cost_reflects_session_model() -> None:
    """Opus costs more than Haiku for the same token counts."""
    from claude_agent.cli.cost_tool import make_check_cost_tool

    haiku = _session(model="claude-haiku-4-5-20251001")
    opus = _session(model="claude-opus-4-7")
    haiku.input_tokens = opus.input_tokens = 1_000_000
    r_haiku = make_check_cost_tool(haiku).function({})
    r_opus = make_check_cost_tool(opus).function({})
    assert _extract_dollar(r_haiku) < _extract_dollar(r_opus)


def test_check_cost_reads_live_session_state() -> None:
    """Tool sees token counts added after the tool was created."""
    from claude_agent.cli.cost_tool import make_check_cost_tool

    s = _session()
    tool = make_check_cost_tool(s)
    s.input_tokens = 1_000_000  # add tokens after tool creation
    result = tool.function({})
    assert _extract_dollar(result) == pytest.approx(3.0)
