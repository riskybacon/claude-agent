"""Tests for stream_response."""

from typing import Any

import pytest

from claude_agent.cli.session import Session
from claude_agent.cli.streaming import stream_response
from tests.fakes import FakeOutput, FakeStreamHandle, FakeStreamingClient


@pytest.fixture()
def session() -> Session:
    """Session with one user message already appended."""
    s = Session(model="opus", system_prompt="system", tools=[])
    s.conversation.append({"role": "user", "content": "hi"})
    return s


def test_tokens_printed_as_they_arrive(session: Session) -> None:
    out = FakeOutput()
    client = FakeStreamingClient(tokens=["hello", " world"])
    stream_response(client, session, out)
    assert out.tokens == ["hello", " world"]


def test_spinner_shown_before_first_token(session: Session) -> None:
    out = FakeOutput()
    client = FakeStreamingClient(tokens=["hi"])
    stream_response(client, session, out)
    assert out.spinner_shown_before_first_token


def test_spinner_hidden_after_streaming_ends(session: Session) -> None:
    out = FakeOutput()
    client = FakeStreamingClient(tokens=["hi"])
    stream_response(client, session, out)
    assert not out.spinner_visible


def test_final_message_appended_to_conversation(session: Session) -> None:
    client = FakeStreamingClient(tokens=["hi"])
    stream_response(client, session, FakeOutput())
    assert len(session.conversation) == 2  # user + assistant


def test_tool_use_triggers_tool_execution(session: Session) -> None:
    tool_use = {"name": "read_file", "id": "tu_1", "input": {"path": "foo.py"}}
    client = FakeStreamingClient(tokens=[], tool_uses=[tool_use])
    executed: list[dict[str, Any]] = []
    stream_response(client, session, FakeOutput(), on_tool=executed.append)
    assert executed[0]["name"] == "read_file"


def test_on_handle_callback_is_called_with_live_handle(session: Session) -> None:
    handle = FakeStreamHandle(tokens=["hi"])
    client = FakeStreamingClient(tokens=[], handle=handle)
    received: list[object] = []
    stream_response(client, session, FakeOutput(), on_handle=received.append)
    assert len(received) == 1
    assert received[0] is handle


def test_token_usage_accumulated_into_session(session: Session) -> None:
    handle = FakeStreamHandle(
        tokens=["hi"],
        input_tokens=100,
        output_tokens=20,
        cache_read_tokens=50,
        cache_creation_tokens=10,
    )
    client = FakeStreamingClient(tokens=[], handle=handle)
    stream_response(client, session, FakeOutput())
    assert session.input_tokens == 100
    assert session.output_tokens == 20
    assert session.cache_read_tokens == 50
    assert session.cache_creation_tokens == 10


def test_token_usage_accumulates_across_calls(session: Session) -> None:
    handle1 = FakeStreamHandle(tokens=["a"], input_tokens=100, output_tokens=10)
    handle2 = FakeStreamHandle(tokens=["b"], input_tokens=200, output_tokens=30)
    for handle in [handle1, handle2]:
        client = FakeStreamingClient(tokens=[], handle=handle)
        stream_response(client, session, FakeOutput())
    assert session.input_tokens == 300
    assert session.output_tokens == 40
