"""RichOutput — terminal OutputWriter backed by the rich library."""

from typing import Any

from rich.console import Console
from rich.markdown import Markdown


class RichOutput:
    """Renders CLI output to the terminal using rich."""

    def __init__(self, *, verbose: bool = False) -> None:
        """Initialise with a rich Console."""
        self._console = Console()
        self._verbose = verbose

    def print_token(self, text: str) -> None:
        """Print a streaming token fragment without a newline."""
        self._console.print(text, end="")

    def print_tool_line(self, name: str, args: dict[str, Any], result: str) -> None:
        """Print a collapsed tool-call line."""
        byte_count = len(result.encode())
        if self._verbose:
            self._console.print(f"[cyan]▶ {name}({args})[/cyan]")
            self._console.print(result)
        else:
            self._console.print(f"[cyan]▶ {name}({args})  [{byte_count} bytes][/cyan]")

    def print_markdown(self, text: str) -> None:
        """Render text as markdown."""
        self._console.print(Markdown(text))

    def print_error(self, message: str) -> None:
        """Print an error message in red."""
        self._console.print(f"[red]Error:[/red] {message}")

    def print_expand(self, result: str) -> None:
        """Print the full result of the most recent tool call."""
        self._console.print(result)

    def show_spinner(self) -> None:
        """No-op — spinner is managed by the streaming context manager."""

    def hide_spinner(self) -> None:
        """No-op — spinner is managed by the streaming context manager."""
