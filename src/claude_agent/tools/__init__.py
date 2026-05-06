"""Built-in tool definitions for claude-agent."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from claude_agent.config import AgentConfig


class SessionInfo:
    """Protocol for the session object passed to tools via ToolContext.

    Any object with these attributes satisfies the interface — Session
    is the production implementation; FakeSession is used in tests.
    """

    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    tool_calls_made: int


@dataclass
class ToolContext:
    """Runtime dependencies injected into every tool call.

    Passing context explicitly keeps tool signatures honest — a tool that
    needs session state or config declares it through the type, rather
    than capturing it in a closure.
    """

    session: SessionInfo
    config: AgentConfig | None = field(default=None)


@dataclass
class Tool:
    """Bundles a tool's metadata and its callable implementation."""

    name: str
    description: str
    input_schema: dict[str, Any]
    function: Callable[[dict[str, Any], ToolContext], str]
