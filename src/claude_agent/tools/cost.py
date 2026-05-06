"""cost tool — report session token usage and estimated API cost."""

from typing import Any

from claude_agent.cli.pricing import estimate_cost
from claude_agent.tools import Tool, ToolContext


def check_cost(_tool_input: dict[str, Any], context: ToolContext) -> str:
    """Report the current estimated API cost and token usage for this session."""
    session = context.session
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


CHECK_COST_TOOL = Tool(
    name="check_cost",
    description=(
        "Report the current estimated API cost and token usage for this session. "
        "Call this to monitor spending before performing expensive operations."
    ),
    input_schema={"type": "object", "properties": {}},
    function=check_cost,
)

TOOLS: list[Tool] = [CHECK_COST_TOOL]
