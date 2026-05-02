"""Tests for the sliding window conversation trimmer."""

from typing import Any

import pytest

from claude_agent.cli.streaming import _trim_to_turns


def _user(text: str) -> dict[str, Any]:
    return {"role": "user", "content": text}


def _assistant(text: str) -> dict[str, Any]:
    return {"role": "assistant", "content": text}


def _tool_use(tool_id: str, name: str) -> dict[str, Any]:
    return {"role": "assistant", "content": [{"type": "tool_use", "id": tool_id, "name": name}]}


def _tool_result(tool_id: str, result: str) -> dict[str, Any]:
    return {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_id, "content": result}]}


# --- basic trimming ---

def test_short_conversation_returned_unchanged() -> None:
    conv = [_user("q1"), _assistant("a1"), _user("q2"), _assistant("a2")]
    assert _trim_to_turns(conv, max_turns=5) == conv


def test_exact_length_returned_unchanged() -> None:
    conv = [_user("q1"), _assistant("a1"), _user("q2"), _assistant("a2")]
    assert _trim_to_turns(conv, max_turns=2) == conv


def test_long_conversation_trimmed_to_last_n_turns() -> None:
    conv = [
        _user("q1"), _assistant("a1"),
        _user("q2"), _assistant("a2"),
        _user("q3"), _assistant("a3"),
    ]
    trimmed = _trim_to_turns(conv, max_turns=2)
    assert trimmed == [_user("q2"), _assistant("a2"), _user("q3"), _assistant("a3")]


def test_trimmed_result_always_starts_with_user_string_message() -> None:
    conv = [_user("q1"), _assistant("a1"), _user("q2"), _assistant("a2"), _user("q3")]
    trimmed = _trim_to_turns(conv, max_turns=1)
    assert trimmed[0]["role"] == "user"
    assert isinstance(trimmed[0]["content"], str)


# --- tool_use / tool_result pairs are never split ---

def test_tool_result_message_not_counted_as_turn_start() -> None:
    """A user message containing tool_results is not a turn boundary."""
    conv = [
        _user("q1"),
        _tool_use("tu_1", "bash"),
        _tool_result("tu_1", "output"),
        _assistant("a1"),
        _user("q2"),
        _assistant("a2"),
    ]
    # Only 2 real turns (q1 and q2); max_turns=1 should give just q2 onwards
    trimmed = _trim_to_turns(conv, max_turns=1)
    assert trimmed == [_user("q2"), _assistant("a2")]


def test_tool_use_and_result_kept_together() -> None:
    """Trimming must never produce a conversation that starts mid-tool-loop."""
    conv = [
        _user("q1"),
        _tool_use("tu_1", "bash"),
        _tool_result("tu_1", "output"),
        _assistant("a1"),
        _user("q2"),
        _assistant("a2"),
    ]
    trimmed = _trim_to_turns(conv, max_turns=2)
    # Both turns fit — full conversation returned
    assert trimmed == conv


# --- session.conversation is not mutated ---

def test_original_conversation_not_mutated() -> None:
    conv = [_user("q1"), _assistant("a1"), _user("q2"), _assistant("a2")]
    original = list(conv)
    _trim_to_turns(conv, max_turns=1)
    assert conv == original
