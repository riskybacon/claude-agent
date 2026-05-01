"""Tests for the main input loop."""

import pytest

from coding_agent.cli.loop import run_loop
from coding_agent.cli.session import Session
from tests.fakes import FakeInput, FakeOutput, FakeStreamingClient


@pytest.fixture()
def session() -> Session:
    """Fresh session for each test."""
    return Session(model="opus", system_prompt="system", tools=[])


def test_plain_message_sent_to_agent(session: Session) -> None:
    inp = FakeInput(["what files are here?", None])
    client = FakeStreamingClient(tokens=["here are your files"])
    calls = run_loop(inp, FakeOutput(), client, session)
    assert calls[0] == "what files are here?"


def test_slash_clear_resets_conversation(session: Session) -> None:
    session.conversation.append({"role": "user", "content": "hi"})
    inp = FakeInput(["/clear", None])
    run_loop(inp, FakeOutput(), FakeStreamingClient(tokens=[]), session)
    assert session.conversation == []


def test_slash_model_switches_model(session: Session) -> None:
    inp = FakeInput(["/model haiku", None])
    run_loop(inp, FakeOutput(), FakeStreamingClient(tokens=[]), session)
    assert session.model == "haiku"


def test_slash_expand_prints_last_tool_result(session: Session) -> None:
    session.last_tool_result = "file contents"
    out = FakeOutput()
    inp = FakeInput(["/expand", None])
    run_loop(inp, out, FakeStreamingClient(tokens=[]), session)
    assert "file contents" in out.expand_calls[0]


def test_empty_input_is_skipped(session: Session) -> None:
    inp = FakeInput(["", "hello", None])
    client = FakeStreamingClient(tokens=["hi"])
    calls = run_loop(inp, FakeOutput(), client, session)
    assert calls == ["hello"]


def test_none_input_exits_loop(session: Session) -> None:
    inp = FakeInput([None])
    run_loop(inp, FakeOutput(), FakeStreamingClient(tokens=[]), session)
