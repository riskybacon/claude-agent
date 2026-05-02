"""Tests for slash command parsing."""

from coding_agent.cli.commands import parse_command


def test_parse_clear() -> None:
    cmd = parse_command("/clear")
    assert cmd is not None
    assert cmd.name == "clear"


def test_parse_model_with_arg() -> None:
    cmd = parse_command("/model haiku")
    assert cmd is not None
    assert cmd.name == "model"
    assert cmd.args == ["haiku"]


def test_plain_text_returns_none() -> None:
    assert parse_command("hello world") is None


def test_empty_string_returns_none() -> None:
    assert parse_command("") is None


def test_unknown_slash_command_is_parsed_not_dropped() -> None:
    cmd = parse_command("/unknown")
    assert cmd is not None
    assert cmd.name == "unknown"
