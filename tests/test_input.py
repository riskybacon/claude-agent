"""Tests for PromptToolkitInput setup (non-interactive parts)."""

from coding_agent.cli.input import _make_bindings


def test_make_bindings_does_not_raise() -> None:
    bindings = _make_bindings()
    assert bindings is not None
