"""Tests for Ctrl+C cancellation behaviour."""

from coding_agent.cli.session import Session
from coding_agent.cli.streaming import stream_response
from tests.fakes import FakeInput, FakeOutput, FakeStreamHandle, FakeStreamingClient


def _make_session() -> Session:
    s = Session(model="opus", system_prompt="system", tools=[])
    s.conversation.append({"role": "user", "content": "hi"})
    return s


def test_cancel_is_called_on_interrupt() -> None:
    handle = FakeStreamHandle()
    handle.cancel()
    assert handle.cancelled


def test_tool_not_executed_after_cancellation() -> None:
    tool_use = {"name": "bash", "id": "tu_1", "input": {"command": "ls"}}
    handle = FakeStreamHandle(tool_uses=[tool_use], cancelled=True)
    client = FakeStreamingClient(tokens=[], handle=handle)
    executed: list[dict] = []
    stream_response(client, _make_session(), FakeOutput(), on_tool=executed.append)
    assert executed == []


def test_loop_continues_after_cancellation() -> None:
    from coding_agent.cli.loop import run_loop

    session = Session(model="opus", system_prompt="system", tools=[])
    handle = FakeStreamHandle()
    client = FakeStreamingClient(tokens=["answer"], handle=handle)
    inp = FakeInput(["first question", "second question", None])
    out = FakeOutput()

    calls = run_loop(inp, out, client, session)
    assert "first question" in calls
    assert "second question" in calls
