"""Mutable session state for the CLI."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import anthropic


class Session:
    """Holds all mutable state for one CLI session."""

    def __init__(
        self,
        model: str,
        system_prompt: str,
        tools: list[dict[str, Any]],
    ) -> None:
        """Initialise the session with a model, system prompt, and tool list."""
        self.model = model
        self.system_prompt = system_prompt
        self.tools = tools
        self.conversation: list[anthropic.types.MessageParam] = []
        self.last_tool_result: str | None = None

    def clear(self) -> None:
        """Reset conversation history; keep model and system prompt."""
        self.conversation = []
        self.last_tool_result = None

    def switch_model(self, model: str) -> None:
        """Switch the active model mid-session."""
        self.model = model
