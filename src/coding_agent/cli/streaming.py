"""Streaming response handling and the real AnthropicStream client."""

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Protocol

from coding_agent.cli.protocols import OutputWriter, StreamingClient
from coding_agent.cli.session import Session

if TYPE_CHECKING:
    from collections.abc import Generator

    import anthropic


class _StreamData(Protocol):
    """Extended handle exposing token/tool data alongside the cancel control."""

    tokens: list[str]
    tool_uses: list[dict[str, Any]]
    cancelled: bool

    def cancel(self) -> None:
        """Cancel the stream."""
        ...


def stream_response(
    client: StreamingClient,
    session: Session,
    out: OutputWriter,
    on_tool: Any = None,  # noqa: ANN401
) -> None:
    """Stream one inference turn: spinner → tokens → assistant message → tool calls."""
    out.show_spinner()
    accumulated: list[str] = []

    with client.stream(
        model=session.model,
        system=session.system_prompt,
        tools=session.tools,
        messages=session.conversation,
    ) as raw_handle:
        handle: _StreamData = raw_handle  # type: ignore[assignment]

        for token in handle.tokens:
            out.hide_spinner()
            out.print_token(token)
            accumulated.append(token)

        out.hide_spinner()

        full_text = "".join(accumulated)
        if full_text:
            session.conversation.append({"role": "assistant", "content": full_text})

        if not handle.cancelled:
            for tool_use in handle.tool_uses:
                if on_tool is not None:
                    on_tool(tool_use)


class _AnthropicStreamHandle:
    """Wraps an Anthropic SDK stream; populated during iteration."""

    def __init__(self) -> None:
        """Initialise an empty handle."""
        self.tokens: list[str] = []
        self.tool_uses: list[dict[str, Any]] = []
        self.cancelled: bool = False

    def cancel(self) -> None:
        """Request cancellation of the active stream."""
        self.cancelled = True


class AnthropicStream:
    """Real StreamingClient backed by the Anthropic SDK."""

    def __init__(self, client: anthropic.Anthropic) -> None:
        """Initialise with an Anthropic client."""
        self._client = client

    @contextmanager
    def stream(
        self,
        model: str,
        system: str,
        tools: list[dict[str, Any]],
        messages: list[anthropic.types.MessageParam],
    ) -> Generator[_AnthropicStreamHandle]:
        """Collect tokens and tool uses, then yield the populated handle."""
        handle = _AnthropicStreamHandle()

        with self._client.messages.stream(
            model=model,
            max_tokens=8096,
            system=system,
            tools=tools,  # type: ignore[arg-type]
            messages=messages,
        ) as sdk_stream:
            for event in sdk_stream:
                if handle.cancelled:
                    break
                if (
                    hasattr(event, "type")
                    and event.type == "content_block_delta"
                    and hasattr(event, "delta")
                    and hasattr(event.delta, "text")
                ):
                    handle.tokens.append(event.delta.text)

            if not handle.cancelled:
                final = sdk_stream.get_final_message()
                for block in final.content:
                    if block.type == "tool_use":
                        handle.tool_uses.append({
                            "name": block.name,
                            "id": block.id,
                            "input": dict(block.input),  # type: ignore[arg-type]
                        })

        yield handle
