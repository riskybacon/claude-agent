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


def _make_anthropic_client(sdk_stream: Any) -> Any:
    """Return a mock anthropic.Anthropic whose .messages.stream() yields sdk_stream."""
    @contextmanager
    def fake_stream_cm(*args: Any, **kwargs: Any):  # noqa: ANN202
        yield sdk_stream

    mock_client = MagicMock()
    mock_client.messages.stream = fake_stream_cm
    return mock_client


def test_tokens_printed_when_sdk_streams_text() -> None:
    sdk_stream = _make_sdk_stream(text_chunks=["hello", " world"])
    client = AnthropicStream(_make_anthropic_client(sdk_stream))
    out = FakeOutput()

    stream_response(client, _make_session(), out)

    assert out.tokens == ["hello", " world"]


def test_tool_uses_collected_from_final_message() -> None:
    tool_use = {"name": "read_file", "id": "tu_1", "input": {"path": "foo.py"}}
    sdk_stream = _make_sdk_stream(text_chunks=[], tool_uses=[tool_use])
    client = AnthropicStream(_make_anthropic_client(sdk_stream))
    executed: list[dict] = []

    stream_response(client, _make_session(), FakeOutput(), on_tool=executed.append)

    assert len(executed) == 1
    assert executed[0]["name"] == "read_file"
