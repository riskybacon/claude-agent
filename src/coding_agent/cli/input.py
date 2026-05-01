"""PromptToolkitInput — real InputReader using prompt_toolkit."""

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings


def _make_bindings() -> KeyBindings:
    kb = KeyBindings()

    @kb.add("shift-enter")
    def _insert_newline(event: object) -> None:  # type: ignore[type-arg]
        """Insert a newline instead of submitting."""
        event.current_buffer.insert_text("\n")  # type: ignore[attr-defined]

    return kb


class PromptToolkitInput:
    """InputReader backed by prompt_toolkit with history and Shift+Enter support."""

    def __init__(self) -> None:
        """Initialise the prompt session."""
        self._session: PromptSession[str] = PromptSession(
            history=InMemoryHistory(),
            key_bindings=_make_bindings(),
            multiline=False,
        )

    def read(self) -> str | None:
        """Prompt the user for input; return None on Ctrl+D (EOF)."""
        try:
            return self._session.prompt("You: ")
        except EOFError:
            return None
        except KeyboardInterrupt:
            return ""
