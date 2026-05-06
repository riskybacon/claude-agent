"""Fake implementations of CLI protocols for testing."""

from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Generator

    import anthropic


@dataclass
class FakeSession:
    """Minimal SessionInfo-compatible object for tests that need a ToolContext."""

    model: str = "claude-sonnet-4-6"
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    tool_calls_made: int = 0


class FakeInput:
    """Fake InputReader that pops from a pre-set list of lines."""

    def __init__(self, lines: list[str | None]) -> None:
        """Initialise with the lines to return in order."""
        self._lines = list(lines)

    def read(self) -> str | None:
        """Return the next line, or None when exhausted."""
        if not self._lines:
            return None
        return self._lines.pop(0)


class FakeOutput:
    """Fake OutputWriter that captures all calls for assertions."""

    def __init__(self) -> None:
        """Initialise with empty capture buffers."""
        self.tokens: list[str] = []
        self.tool_lines: list[str] = []
        self.markdown_calls: list[str] = []
        self.errors: list[str] = []
        self.expand_calls: list[str] = []
        self.spinner_visible: bool = False
        self.spinner_shown_before_first_token: bool = False
        self._first_token_received: bool = False
        # Ordered log of all output events for interleaving assertions.
        # Each entry is a tuple whose first element is the event kind:
        #   ("token", text), ("newline",), ("tool_line", name, args, result)  # noqa: ERA001
        self.events: list[tuple[Any, ...]] = []

    def print_token(self, text: str) -> None:
        """Capture a token."""
        self._first_token_received = True
        self.tokens.append(text)
        self.events.append(("token", text))

    def print_newline(self) -> None:
        """Capture a newline event."""
        self.events.append(("newline",))

    def print_tool_line(self, name: str, args: dict[str, Any], result: str) -> None:
        """Capture a tool line with byte count."""
        byte_count = len(result.encode())
        self.tool_lines.append(f"▶ {name}({args})  [{byte_count} bytes]")
        self.events.append(("tool_line", name, args, result))

    def print_markdown(self, text: str) -> None:
        """Capture a markdown call."""
        self.markdown_calls.append(text)

    def print_error(self, message: str) -> None:
        """Capture an error message."""
        self.errors.append(message)

    def print_expand(self, result: str) -> None:
        """Capture an expand call."""
        self.expand_calls.append(result)

    def show_spinner(self) -> None:
        """Show spinner and note if no token has been received yet."""
        self.spinner_visible = True
        if not self._first_token_received:
            self.spinner_shown_before_first_token = True

    def hide_spinner(self) -> None:
        """Hide spinner."""
        self.spinner_visible = False

    def event_kinds(self) -> list[str]:
        """Return the kind field of every recorded event, in order."""
        return [e[0] for e in self.events]


class FakeStreamHandle:
    """Fake stream handle with pre-set tokens and tool uses."""

    def __init__(  # noqa: PLR0913
        self,
        tokens: list[str] | None = None,
        tool_uses: list[dict[str, Any]] | None = None,
        *,
        cancelled: bool = False,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_creation_tokens: int = 0,
    ) -> None:
        """Initialise with optional tokens, tool uses, cancelled state, and usage counts."""
        self.tokens: list[str] = tokens if tokens is not None else []
        self.tool_uses: list[dict[str, Any]] = tool_uses if tool_uses is not None else []
        self.cancelled: bool = cancelled
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_read_tokens = cache_read_tokens
        self.cache_creation_tokens = cache_creation_tokens

    def cancel(self) -> None:
        """Mark the stream as cancelled."""
        self.cancelled = True


class FakeStreamingClient:
    """Fake StreamingClient that yields a pre-configured FakeStreamHandle."""

    def __init__(
        self,
        tokens: list[str],
        tool_uses: list[dict[str, Any]] | None = None,
        handle: FakeStreamHandle | None = None,
    ) -> None:
        """Initialise with tokens and optional tool uses or a pre-made handle."""
        self._tokens = tokens
        self._tool_uses = tool_uses or []
        self._handle = handle

    @contextmanager
    def stream(
        self,
        model: str,  # noqa: ARG002
        system: str,  # noqa: ARG002
        tools: list[dict[str, Any]],  # noqa: ARG002
        messages: list[anthropic.types.MessageParam],  # noqa: ARG002
        on_handle: Any = None,  # noqa: ANN401
    ) -> Generator[FakeStreamHandle]:
        """Yield a FakeStreamHandle pre-populated with configured tokens and tool uses."""
        handle = self._handle if self._handle is not None else FakeStreamHandle(
            tokens=list(self._tokens),
            tool_uses=list(self._tool_uses),
        )
        if on_handle is not None:
            on_handle(handle)
        yield handle
