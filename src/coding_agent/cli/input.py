"""PromptToolkitInput — real InputReader using prompt_toolkit."""

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings


def _make_bindings() -> KeyBindings:
    kb = KeyBindings()

    # Most terminals can't distinguish Shift+Enter from Enter at the byte level.
    # "escape", "enter" (Alt/Meta+Enter) is the portable alternative.
    @kb.add("escape", "enter")
    def _insert_newline(event: object) -> None:  # type: ignore[type-arg]
        """Insert a newline instead of submitting."""
        event.current_buffer.insert_text("\n")  # type: ignore[attr-defined]

    @kb.add("enter")
    def _submit(event: object) -> None:  # type: ignore[type-arg]
        """Submit the current input."""
        event.current_buffer.validate_and_handle()  # type: ignore[attr-defined]

    return kb


class PromptToolkitInput:
    """InputReader backed by prompt_toolkit with history and Alt+Enter multi-line support."""

    def __init__(self) -> None:
        """Initialise the prompt session."""
        self._session: PromptSession[str] = PromptSession(
            history=InMemoryHistory(),
            key_bindings=_make_bindings(),
            multiline=True,
        )

    def read(self) -> str | None:
        """Prompt the user for input; return None on Ctrl+D (EOF)."""
        try:
            return self._session.prompt("You: ")
        except EOFError:
            return None
        except KeyboardInterrupt:
            return ""
