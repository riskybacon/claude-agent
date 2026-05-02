"""Tests for the main input loop."""

from contextlib import contextmanager
from typing import Any

import pytest

from claude_agent.cli.loop import run_loop
from claude_agent.cli.session import Session
from tests.fakes import FakeInput, FakeOutput, FakeStreamingClient


class _RaisingClient:
    """Streaming client that always raises on stream()."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    @contextmanager
    def stream(
        self,
        model: str,  # noqa: ARG002
        system: str,  # noqa: ARG002
        tools: list[dict[str, Any]],  # noqa: ARG002
        messages: list[Any],  # noqa: ARG002
        on_handle: Any = None,  # noqa: ANN401, ARG002
    ) -> Any:
        raise self._exc
        yield  # type: ignore[unreachable]  # makes this a generator so @contextmanager works


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


def test_api_error_is_shown_not_raised(session: Session) -> None:
    out = FakeOutput()
    client = _RaisingClient(RuntimeError("rate limit exceeded"))
    run_loop(FakeInput(["hello", None]), out, client, session)
    assert any("rate limit exceeded" in e for e in out.errors)


def test_loop_continues_after_api_error(session: Session) -> None:
    from tests.fakes import FakeStreamHandle

    out = FakeOutput()
    inp = FakeInput(["bad", "good", None])

    class _MixedClient:
        def __init__(self) -> None:
            self._calls = 0

        @contextmanager
        def stream(self, model: str, system: str, tools: Any, messages: Any, on_handle: Any = None) -> Any:  # noqa: ANN202
            self._calls += 1
            if self._calls == 1:
                raise RuntimeError("rate limit")
                yield  # type: ignore[unreachable]
            else:
                handle = FakeStreamHandle(tokens=["hi"])
                if on_handle is not None:
                    on_handle(handle)
                yield handle

    run_loop(inp, out, _MixedClient(), session)
    assert any("rate limit" in e for e in out.errors)
    assert out.tokens == ["hi"]


def test_failed_turn_does_not_corrupt_conversation(session: Session) -> None:
    client = _RaisingClient(RuntimeError("oops"))
    run_loop(FakeInput(["hello", None]), FakeOutput(), client, session)
    # The user message must be removed — no orphaned turn without an assistant reply
    assert session.conversation == []


# --- slash command UX ---

def test_run_loop_threads_on_handle_to_stream_response(session: Session) -> None:
    """on_handle passed to run_loop must reach the live stream handle."""
    from tests.fakes import FakeStreamHandle

    handle = FakeStreamHandle(tokens=["answer"])
    client = FakeStreamingClient(tokens=[], handle=handle)
    received: list[object] = []

    run_loop(FakeInput(["hello", None]), FakeOutput(), client, session, on_handle=received.append)

    assert len(received) == 1
    assert received[0] is handle


def test_model_command_without_arg_shows_usage_error(session: Session) -> None:
    out = FakeOutput()
    run_loop(FakeInput(["/model", None]), out, FakeStreamingClient(tokens=[]), session)
    assert session.model == "opus"
    assert len(out.errors) > 0
    assert "usage" in out.errors[0].lower()


def test_clear_command_gives_feedback(session: Session) -> None:
    session.conversation.append({"role": "user", "content": "hi"})
    out = FakeOutput()
    run_loop(FakeInput(["/clear", None]), out, FakeStreamingClient(tokens=[]), session)
    assert session.conversation == []
    assert any("clear" in m.lower() for m in out.markdown_calls)


def test_model_switch_gives_feedback(session: Session) -> None:
    out = FakeOutput()
    run_loop(FakeInput(["/model haiku", None]), out, FakeStreamingClient(tokens=[]), session)
    assert session.model == "haiku"
    assert any("haiku" in m.lower() for m in out.markdown_calls)


def test_usage_command_shows_token_counts(session: Session) -> None:
    from tests.fakes import FakeStreamHandle

    session.input_tokens = 1234
    session.output_tokens = 56
    out = FakeOutput()
    run_loop(FakeInput(["/usage", None]), out, FakeStreamingClient(tokens=[]), session)
    assert any("1,234" in m for m in out.markdown_calls)
    assert any("56" in m for m in out.markdown_calls)


def test_high_token_usage_shows_warning(session: Session) -> None:
    from tests.fakes import FakeStreamHandle

    handle = FakeStreamHandle(tokens=["ok"], input_tokens=110_000)
    out = FakeOutput()
    run_loop(
        FakeInput(["hello", None]),
        out,
        FakeStreamingClient(tokens=[], handle=handle),
        session,
    )
    assert any("token" in e.lower() for e in out.errors)
