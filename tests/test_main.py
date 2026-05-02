"""Tests for main.py startup helpers."""

from pathlib import Path

import pytest

from claude_agent.cli.main import _load_claude_md


def test_returns_content_and_path_when_file_in_start_dir(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text("be helpful")
    result = _load_claude_md(tmp_path)
    assert result is not None
    found_path, content = result
    assert content == "be helpful"
    assert found_path == tmp_path / "CLAUDE.md"


def test_walks_up_to_parent_when_not_in_start_dir(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text("parent instructions")
    child = tmp_path / "subdir"
    child.mkdir()
    result = _load_claude_md(child)
    assert result is not None
    _, content = result
    assert content == "parent instructions"


def test_returns_none_when_no_file_found(tmp_path: Path) -> None:
    assert _load_claude_md(tmp_path) is None


def test_prefers_nearest_file_over_parent(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text("parent")
    child = tmp_path / "subdir"
    child.mkdir()
    (child / "CLAUDE.md").write_text("child")
    result = _load_claude_md(child)
    assert result is not None
    _, content = result
    assert content == "child"
