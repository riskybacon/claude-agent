"""Tests for AnthropicStream against a mocked SDK client.

These tests expose bugs in AnthropicStream.stream() that only surface
when the real SDK client is involved.
"""

from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock

import pytest

from coding_agent.cli.session import Session
from coding_agent.cli.streaming import AnthropicStream, stream_response
from tests.fakes import FakeOutput


def _make_session() -> Session:
    s = Session(model="opus", system_prompt="system", tools=[])
    s.conversation.append({"role": "user", "content": "hi"})
    return s


def _make_sdk_stream(text_chunks: list[str], tool_uses: list[dict[str, Any]] | None = None) -> Any:
    """Return a mock MessageStream that behaves like the real Anthropic SDK stream.

    The real SDK stream:
    - Iterated directly yields MessageStreamEvent objects whose .type is "text",
      NOT "content_block_delta". The raw event type "content_block_delta" only
      appears in the lower-level wire protocol.
    - .text_stream yields text string chunks directly.
    - .get_final_message() returns the assembled Message.
    """
    # Simulate real SDK events — type is "text", not "content_block_delta"
    raw_events = []
    for chunk in text_chunks:
        evt = MagicMock()
        evt.type = "text"   # <-- real SDK MessageStreamEvent type, not "content_block_delta"
        evt.text = chunk
        raw_events.append(evt)

    final_content_blocks = []
    for tu in (tool_uses or []):
        block = MagicMock()
        block.type = "tool_use"
        block.name = tu["name"]
        block.id = tu["id"]
        block.input = tu["input"]
        final_content_blocks.append(block)

    mock_stream = MagicMock()
    mock_stream.__iter__ = MagicMock(return_value=iter(raw_events))
    mock_stream.text_stream = iter(text_chunks)
    mock_stream.get_final_message.return_value = MagicMock(content=final_content_blocks)
    return mock_stream


def _make_anthropic_client(sdk_stream: Any) -> tuple[Any, list[dict[str, Any]]]:
    """Return (mock client, captured_calls) where each call appends its kwargs."""
    captured: list[dict[str, Any]] = []

    @contextmanager
    def fake_stream_cm(*args: Any, **kwargs: Any):  # noqa: ANN202
        captured.append(kwargs)
        yield sdk_stream

    mock_client = MagicMock()
    mock_client.messages.stream = fake_stream_cm
    return mock_client, captured


def test_tokens_printed_when_sdk_streams_text() -> None:
    sdk_stream = _make_sdk_stream(text_chunks=["hello", " world"])
    mock_client, _ = _make_anthropic_client(sdk_stream)
    out = FakeOutput()

    stream_response(AnthropicStream(mock_client), _make_session(), out)

    assert out.tokens == ["hello", " world"]


def test_tool_uses_collected_from_final_message() -> None:
    tool_use = {"name": "read_file", "id": "tu_1", "input": {"path": "foo.py"}}
    sdk_stream = _make_sdk_stream(text_chunks=[], tool_uses=[tool_use])
    mock_client, _ = _make_anthropic_client(sdk_stream)
    executed: list[dict] = []

    stream_response(AnthropicStream(mock_client), _make_session(), FakeOutput(), on_tool=executed.append)

    assert len(executed) == 1
    assert executed[0]["name"] == "read_file"


# --- prompt caching ---

def test_system_prompt_sent_with_cache_control() -> None:
    sdk_stream = _make_sdk_stream(text_chunks=[])
    mock_client, captured = _make_anthropic_client(sdk_stream)
    session = _make_session()
    session.system_prompt = "Be helpful."

    stream_response(AnthropicStream(mock_client), session, FakeOutput())

    system = captured[0]["system"]
    assert isinstance(system, list), "system must be a list of content blocks for cache_control"
    assert system[0]["type"] == "text"
    assert system[0]["text"] == "Be helpful."
    assert system[0]["cache_control"] == {"type": "ephemeral"}


def test_last_tool_sent_with_cache_control() -> None:
    sdk_stream = _make_sdk_stream(text_chunks=[])
    mock_client, captured = _make_anthropic_client(sdk_stream)
    session = _make_session()
    session.tools = [
        {"name": "read_file", "description": "reads", "input_schema": {}},
        {"name": "bash", "description": "runs", "input_schema": {}},
    ]

    stream_response(AnthropicStream(mock_client), session, FakeOutput())

    tools = captured[0]["tools"]
    assert "cache_control" not in tools[0], "only the last tool should have cache_control"
    assert tools[-1]["cache_control"] == {"type": "ephemeral"}
    assert tools[-1]["name"] == "bash"


def test_empty_tool_list_has_no_cache_control() -> None:
    sdk_stream = _make_sdk_stream(text_chunks=[])
    mock_client, captured = _make_anthropic_client(sdk_stream)
    session = _make_session()
    session.tools = []

    stream_response(AnthropicStream(mock_client), session, FakeOutput())

    assert captured[0]["tools"] == []
