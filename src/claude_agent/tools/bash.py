"""bash tool — execute a shell command and return its output."""

import subprocess
from typing import TYPE_CHECKING, Any

from claude_agent.tools import Tool, ToolContext

if TYPE_CHECKING:
    from claude_agent.config import AgentConfig

_BASH_TIMEOUT_SECONDS = 120


def bash(tool_input: dict[str, Any], context: ToolContext) -> str:
    """Run a bash command and return its output (stdout + stderr combined).

    Command failures are returned as output rather than raised as exceptions
    so Claude can read the error and decide how to proceed.
    """
    config: AgentConfig | None = context.config
    timeout_seconds = config.bash_timeout_seconds if config else _BASH_TIMEOUT_SECONDS
    try:
        result = subprocess.run(  # noqa: S603
            ["bash", "-c", tool_input["command"]],  # noqa: S607
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout_seconds} seconds"
    if result.returncode != 0:
        return f"Command failed (exit {result.returncode}):\n{result.stdout.strip()}"
    return result.stdout.strip()


BASH_TOOL = Tool(
    name="bash",
    description="Execute a bash command and return its output. Use this to run shell commands.",
    input_schema={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The bash command to execute.",
            }
        },
        "required": ["command"],
    },
    function=bash,
)

TOOLS: list[Tool] = [BASH_TOOL]
