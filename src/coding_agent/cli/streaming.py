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

        # Prefer the full content block list (preserves tool_use blocks for multi-turn).
        # Fall back to building content from tokens + tool_uses (covers fake handles in tests).
        final_content: list[Any] = getattr(handle, "final_content", [])
        if final_content:
            session.conversation.append({"role": "assistant", "content": final_content})
        else:
            content: list[Any] = []
            if accumulated:
                content.append({"type": "text", "text": "".join(accumulated)})
            content.extend(
                {"type": "tool_use", "id": tu["id"], "name": tu["name"], "input": tu["input"]}
                for tu in handle.tool_uses
            )
            if content:
                session.conversation.append({"role": "assistant", "content": content})

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
        self.final_content: list[Any] = []

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

        cached_system: list[dict[str, Any]] = [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
        ]
        cached_tools: list[dict[str, Any]] = (
            [*tools[:-1], {**tools[-1], "cache_control": {"type": "ephemeral"}}]
            if tools
            else []
        )

        with self._client.messages.stream(
            model=model,
            max_tokens=8096,
            system=cached_system,  # type: ignore[arg-type]
            tools=cached_tools,  # type: ignore[arg-type]
            messages=messages,
        ) as sdk_stream:
            for text_chunk in sdk_stream.text_stream:
                if handle.cancelled:
                    break
                handle.tokens.append(text_chunk)

            if not handle.cancelled:
                final = sdk_stream.get_final_message()
                handle.final_content = list(final.content)  # type: ignore[assignment]
                for block in final.content:
                    if block.type == "tool_use":
                        handle.tool_uses.append({
                            "name": block.name,
                            "id": block.id,
                            "input": dict(block.input),  # type: ignore[arg-type]
                        })

        yield handle
