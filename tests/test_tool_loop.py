"""Tests for tool execution within the input loop.

These expose the missing tool-execution loop in run_loop: when Claude
returns a tool_use block, the tool must actually be called, its result
appended to the conversation, and a second inference turn triggered.
"""

from contextlib import contextmanager
from typing import Any

import pytest

from coding_agent.cli.session import Session
from tests.fakes import FakeInput, FakeOutput, FakeStreamHandle


class _SequentialStreamingClient:
    """Yields a different FakeStreamHandle on each successive stream() call."""

    def __init__(self, handles: list[FakeStreamHandle]) -> None:
        self._handles = list(handles)

    @contextmanager
    def stream(
        self,
        model: str,  # noqa: ARG002
        system: str,  # noqa: ARG002
        tools: list[dict[str, Any]],  # noqa: ARG002
        messages: list[Any],  # noqa: ARG002
    ) -> Any:  # noqa: ANN202
        yield self._handles.pop(0) if self._handles else FakeStreamHandle()


@pytest.fixture()
def session() -> Session:
    return Session(model="opus", system_prompt="system", tools=[])


def test_tool_is_executed_and_result_appended(session: Session) -> None:
    """run_loop must execute the tool Claude calls and feed the result back."""
    from coding_agent.cli.loop import run_loop

    first = FakeStreamHandle(tool_uses=[{"name": "bash", "id": "tu_1", "input": {"command": "ls"}}])
    second = FakeStreamHandle(tokens=["Done!"])
    client = _SequentialStreamingClient([first, second])

    executed: list[tuple[str, dict[str, Any]]] = []

    def executor(name: str, tool_input: dict[str, Any]) -> tuple[str, bool]:
        executed.append((name, tool_input))
        return "file.py\n", False

    run_loop(FakeInput(["list files", None]), FakeOutput(), client, session, tool_executor=executor)

    assert len(executed) == 1
    assert executed[0] == ("bash", {"command": "ls"})


def test_tool_result_added_to_conversation(session: Session) -> None:
    """Tool results must appear in the conversation so Claude sees them."""
    from coding_agent.cli.loop import run_loop

    first = FakeStreamHandle(tool_uses=[{"name": "bash", "id": "tu_1", "input": {"command": "ls"}}])
    second = FakeStreamHandle(tokens=["Done!"])
    client = _SequentialStreamingClient([first, second])

    run_loop(
        FakeInput(["list files", None]),
        FakeOutput(),
        client,
        session,
        tool_executor=lambda n, i: ("file.py\n", False),
    )

    # conversation: user, assistant (tool_use), user (tool_result), assistant (text)
    roles = [m["role"] for m in session.conversation]
    assert roles == ["user", "assistant", "user", "assistant"]


def test_large_tool_result_is_truncated_in_conversation(session: Session) -> None:
    """Tool results over 1000 chars must be truncated before storing in conversation."""
    from coding_agent.cli.loop import run_loop, _MAX_TOOL_RESULT_IN_HISTORY

    big_result = "x" * 5000
    first = FakeStreamHandle(tool_uses=[{"name": "read_file", "id": "tu_1", "input": {"path": "big.py"}}])
    second = FakeStreamHandle(tokens=["Done!"])
    client = _SequentialStreamingClient([first, second])

    run_loop(
        FakeInput(["read big file", None]),
        FakeOutput(),
        client,
        session,
        tool_executor=lambda n, i: (big_result, False),
    )

    # Find the tool_result message (role="user" with list content)
    tool_result_msg = next(
        m for m in session.conversation
        if m["role"] == "user" and isinstance(m["content"], list)
    )
    content = tool_result_msg["content"]
    assert isinstance(content, list)
    stored = content[0]["content"]  # type: ignore[index]
    assert isinstance(stored, str)
    assert len(stored) <= _MAX_TOOL_RESULT_IN_HISTORY + 100  # allow for truncation suffix
    assert "truncated" in stored


def test_small_tool_result_is_stored_in_full(session: Session) -> None:
    """Tool results under 1000 chars must be stored verbatim."""
    from coding_agent.cli.loop import run_loop, _MAX_TOOL_RESULT_IN_HISTORY

    small_result = "file.py\nother.py\n"
    first = FakeStreamHandle(tool_uses=[{"name": "bash", "id": "tu_1", "input": {"command": "ls"}}])
    second = FakeStreamHandle(tokens=["Done!"])
    client = _SequentialStreamingClient([first, second])

    run_loop(
        FakeInput(["list files", None]),
        FakeOutput(),
        client,
        session,
        tool_executor=lambda n, i: (small_result, False),
    )

    tool_result_msg = next(
        m for m in session.conversation
        if m["role"] == "user" and isinstance(m["content"], list)
    )
    content = tool_result_msg["content"]
    assert isinstance(content, list)
    stored = content[0]["content"]  # type: ignore[index]
    assert stored == small_result


def test_full_result_still_available_for_expand(session: Session) -> None:
    """session.last_tool_result must hold the full result even when conversation is truncated."""
    from coding_agent.cli.loop import run_loop

    big_result = "y" * 5000
    first = FakeStreamHandle(tool_uses=[{"name": "read_file", "id": "tu_1", "input": {"path": "f.py"}}])
    second = FakeStreamHandle(tokens=["Done!"])
    client = _SequentialStreamingClient([first, second])

    run_loop(
        FakeInput(["read file", None]),
        FakeOutput(),
        client,
        session,
        tool_executor=lambda n, i: (big_result, False),
    )

    assert session.last_tool_result == big_result


def test_newlines_printed_around_tool_calls(session: Session) -> None:
    """Newlines should separate streamed tokens from tool output."""
    from coding_agent.cli.loop import run_loop

    first = FakeStreamHandle(
        tokens=["thinking..."],
        tool_uses=[{"name": "bash", "id": "tu_1", "input": {"command": "ls"}}],
    )
    second = FakeStreamHandle(tokens=["Done!"])
    client = _SequentialStreamingClient([first, second])
    out = FakeOutput()

    run_loop(
        FakeInput(["list files", None]),
        out,
        client,
        session,
        tool_executor=lambda n, i: ("file.py", False),
    )

    # Should have newlines: after first tokens, after tool lines, after final tokens
    assert out.newline_count >= 2
