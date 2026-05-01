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
    ):  # noqa: ANN202
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

    executed: list[tuple[str, dict]] = []

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
