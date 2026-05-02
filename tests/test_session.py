"""Tests for session state."""

from typing import Any

import pytest

from claude_agent.cli.session import Session


def _make_session(
    *,
    model: str = "opus",
    system_prompt: str = "default",
    tools: list[dict[str, Any]] | None = None,
) -> Session:
    return Session(
        model=model,
        system_prompt=system_prompt,
        tools=tools if tools is not None else [],
    )


def test_clear_resets_conversation() -> None:
    s = _make_session()
    s.conversation.append({"role": "user", "content": "hi"})
    s.clear()
    assert s.conversation == []


def test_clear_preserves_model_and_system_prompt() -> None:
    s = _make_session(model="haiku", system_prompt="custom")
    s.clear()
    assert s.model == "haiku"
    assert s.system_prompt == "custom"


def test_switch_model() -> None:
    s = _make_session(model="opus")
    s.switch_model("haiku")
    assert s.model == "haiku"


def test_last_tool_result_stored() -> None:
    s = _make_session()
    s.last_tool_result = "file contents"
    assert s.last_tool_result == "file contents"


def test_last_tool_result_none_on_init() -> None:
    assert _make_session().last_tool_result is None


def test_token_counts_zero_on_init() -> None:
    s = _make_session()
    assert s.input_tokens == 0
    assert s.output_tokens == 0
    assert s.cache_read_tokens == 0
    assert s.cache_creation_tokens == 0


def test_clear_resets_token_counts() -> None:
    s = _make_session()
    s.input_tokens = 500
    s.output_tokens = 100
    s.cache_read_tokens = 200
    s.cache_creation_tokens = 50
    s.clear()
    assert s.input_tokens == 0
    assert s.output_tokens == 0
    assert s.cache_read_tokens == 0
    assert s.cache_creation_tokens == 0


# --- token_snapshot / cost_since ---

def test_token_snapshot_captures_current_counts() -> None:
    """Snapshot records all four token counters at the moment of the call."""
    in_tok, out_tok, cr_tok, cc_tok = 1000, 500, 200, 50
    s = _make_session()
    s.input_tokens = in_tok
    s.output_tokens = out_tok
    s.cache_read_tokens = cr_tok
    s.cache_creation_tokens = cc_tok
    snap = s.token_snapshot()
    assert snap.input_tokens == in_tok
    assert snap.output_tokens == out_tok
    assert snap.cache_read_tokens == cr_tok
    assert snap.cache_creation_tokens == cc_tok


def test_cost_since_zero_when_no_new_tokens() -> None:
    """cost_since returns 0 when no tokens have been added after the snapshot."""
    s = _make_session()
    snap = s.token_snapshot()
    assert s.cost_since(snap) == 0.0


def test_cost_since_delta_input_tokens() -> None:
    """cost_since measures the delta in input tokens since the snapshot."""
    s = _make_session(model="claude-sonnet-4-6")
    snap = s.token_snapshot()
    s.input_tokens += 1_000_000
    assert s.cost_since(snap) == pytest.approx(3.0)


def test_cost_since_delta_output_tokens() -> None:
    """cost_since measures the delta in output tokens since the snapshot."""
    s = _make_session(model="claude-sonnet-4-6")
    snap = s.token_snapshot()
    s.output_tokens += 1_000_000
    assert s.cost_since(snap) == pytest.approx(15.0)


def test_cost_since_uses_session_model() -> None:
    """cost_since prices the delta at the session's current model rates."""
    haiku = _make_session(model="claude-haiku-4-5-20251001")
    opus = _make_session(model="claude-opus-4-7")
    snap_h = haiku.token_snapshot()
    snap_o = opus.token_snapshot()
    haiku.input_tokens += 1_000_000
    opus.input_tokens += 1_000_000
    assert haiku.cost_since(snap_h) < opus.cost_since(snap_o)


def test_cost_since_all_token_types() -> None:
    """cost_since sums deltas across all four token types."""
    s = _make_session(model="claude-sonnet-4-6")
    snap = s.token_snapshot()
    s.input_tokens += 1_000_000
    s.output_tokens += 1_000_000
    s.cache_read_tokens += 1_000_000
    s.cache_creation_tokens += 1_000_000
    expected = 3.0 + 15.0 + 0.30 + 3.75
    assert s.cost_since(snap) == pytest.approx(expected)
