"""Tests for output rendering via FakeOutput."""

from tests.fakes import FakeOutput


def test_format_tool_line_contains_name() -> None:
    out = FakeOutput()
    out.print_tool_line("read_file", {"path": "foo.py"}, "contents")
    assert "read_file" in out.tool_lines[0]


def test_format_tool_line_contains_byte_count() -> None:
    out = FakeOutput()
    out.print_tool_line("read_file", {}, "hello")
    assert "5" in out.tool_lines[0]


def test_format_tool_line_starts_with_arrow() -> None:
    out = FakeOutput()
    out.print_tool_line("bash", {"command": "ls"}, "file.py")
    assert out.tool_lines[0].startswith("▶")


def test_tool_line_does_not_include_full_result() -> None:
    out = FakeOutput()
    out.print_tool_line("read_file", {}, "x" * 10_000)
    assert len(out.tool_lines[0]) < 200


def test_expand_prints_full_result() -> None:
    out = FakeOutput()
    out.print_expand("full result here")
    assert "full result here" in out.expand_calls[0]


def test_error_is_captured() -> None:
    out = FakeOutput()
    out.print_error("something went wrong")
    assert out.errors == ["something went wrong"]
