"""Protocol definitions for terminal-dependent CLI components."""

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from contextlib import AbstractContextManager

    import anthropic


class InputReader(Protocol):
    """Source of user input lines; None signals EOF."""

    def read(self) -> str | None:
        """Return the next line of input, or None on EOF."""
        ...


class OutputWriter(Protocol):
    """Sink for all CLI output."""

    def print_token(self, text: str) -> None:
        """Print a streaming token fragment."""
        ...

    def print_tool_line(self, name: str, args: dict[str, Any], result: str) -> None:
        """Print a collapsed tool-call summary line."""
        ...

    def print_markdown(self, text: str) -> None:
        """Render text as markdown."""
        ...

    def print_error(self, message: str) -> None:
        """Print an error message."""
        ...

    def print_expand(self, result: str) -> None:
        """Print the full result of the most recent tool call."""
        ...

    def show_spinner(self) -> None:
        """Show the thinking spinner."""
        ...

    def hide_spinner(self) -> None:
        """Hide the thinking spinner."""
        ...


class StreamHandle(Protocol):
    """Handle to an active inference stream."""

    def cancel(self) -> None:
        """Cancel the active stream."""
        ...


class StreamingClient(Protocol):
    """Client that streams inference responses."""

    def stream(
        self,
        model: str,
        system: str,
        tools: list[dict[str, Any]],
        messages: list[anthropic.types.MessageParam],
        on_handle: Any = None,  # noqa: ANN401
    ) -> AbstractContextManager[StreamHandle]:
        """Return a context manager that streams tokens and yields a StreamHandle."""
        ...
