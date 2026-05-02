"""Factory for the check_cost tool — a session-aware closure."""

from typing import TYPE_CHECKING, Any

from claude_agent.cli.pricing import estimate_cost
from claude_agent.tools import Tool

if TYPE_CHECKING:
    from claude_agent.cli.session import Session


def make_check_cost_tool(session: Session) -> Tool:
    """Return a Tool that reports the session's current token usage and estimated cost."""

    def check_cost(_tool_input: dict[str, Any]) -> str:
        cost = estimate_cost(
            model=session.model,
            input_tokens=session.input_tokens,
            output_tokens=session.output_tokens,
            cache_read_tokens=session.cache_read_tokens,
            cache_creation_tokens=session.cache_creation_tokens,
        )
        return (
            f"Session cost estimate: ${cost:.4f}\n"
            f"  Input tokens: {session.input_tokens:,}\n"
            f"  Output tokens: {session.output_tokens:,}\n"
            f"  Cache read tokens: {session.cache_read_tokens:,}\n"
            f"  Cache creation tokens: {session.cache_creation_tokens:,}\n"
            f"  Tool calls: {session.tool_calls_made}"
        )

    return Tool(
        name="check_cost",
        description=(
            "Report the current estimated API cost and token usage for this session. "
            "Call this to monitor spending before performing expensive operations."
        ),
        input_schema={"type": "object", "properties": {}},
        function=check_cost,
    )
