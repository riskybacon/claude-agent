"""Mutable session state for the CLI."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from claude_agent.cli.pricing import estimate_cost

if TYPE_CHECKING:
    import anthropic


@dataclass(frozen=True)
class TokenSnapshot:
    """Immutable capture of session token counters at a point in time."""

    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int


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
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0
        self.cache_creation_tokens = 0
        self.tool_calls_made = 0

    def clear(self) -> None:
        """Reset conversation history; keep model and system prompt."""
        self.conversation = []
        self.last_tool_result = None
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0
        self.cache_creation_tokens = 0
        self.tool_calls_made = 0

    def switch_model(self, model: str) -> None:
        """Switch the active model mid-session."""
        self.model = model

    def token_snapshot(self) -> TokenSnapshot:
        """Return a snapshot of the current token counters."""
        return TokenSnapshot(
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cache_read_tokens=self.cache_read_tokens,
            cache_creation_tokens=self.cache_creation_tokens,
        )

    def cost_since(self, snapshot: TokenSnapshot) -> float:
        """Return the estimated cost in USD of tokens accumulated since snapshot."""
        return estimate_cost(
            model=self.model,
            input_tokens=self.input_tokens - snapshot.input_tokens,
            output_tokens=self.output_tokens - snapshot.output_tokens,
            cache_read_tokens=self.cache_read_tokens - snapshot.cache_read_tokens,
            cache_creation_tokens=self.cache_creation_tokens - snapshot.cache_creation_tokens,
        )
