"""code_search tool — search for patterns using ripgrep."""

import subprocess
from typing import Any

from claude_agent.tools import Tool

_MAX_SEARCH_MATCHES = 50
_BASH_TIMEOUT_SECONDS = 120


def code_search(tool_input: dict[str, Any]) -> str:
    """Search for a pattern using ripgrep; return matching lines with file and line number.

    ripgrep exits with code 1 when there are no matches — that is not an error.
    Output is capped at _MAX_SEARCH_MATCHES lines to keep responses manageable.
    """
    pattern: str = tool_input["pattern"]
    if not pattern:
        msg = "pattern must not be empty"
        raise ValueError(msg)

    args = ["rg", "--line-number", "--with-filename", "--color=never"]

    if not tool_input.get("case_sensitive", False):
        args.append("--ignore-case")

    if file_type := tool_input.get("file_type"):
        args.extend(["--type", file_type])

    args.append(pattern)
    args.append(tool_input.get("path", "."))

    try:
        result = subprocess.run(  # noqa: S603
            args,
            capture_output=True,
            text=True,
            check=False,
            timeout=_BASH_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return f"Search timed out after {_BASH_TIMEOUT_SECONDS} seconds"

    if result.returncode == 1:
        return "No matches found"
    if result.returncode != 0:
        msg = f"search failed: {result.stderr.strip()}"
        raise RuntimeError(msg)

    lines = result.stdout.strip().splitlines()
    if len(lines) > _MAX_SEARCH_MATCHES:
        truncated = "\n".join(lines[:_MAX_SEARCH_MATCHES])
        return f"{truncated}\n... (showing first {_MAX_SEARCH_MATCHES} of {len(lines)} matches)"
    return result.stdout.strip()


CODE_SEARCH_TOOL = Tool(
    name="code_search",
    description=(
        "Search for code patterns using ripgrep (rg).\n\n"
        "Use this to find function definitions, variable usage, or any text in the codebase. "
        "You can filter by file type or directory."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "The search pattern or regex to look for.",
            },
            "path": {
                "type": "string",
                "description": "Optional path to search in. Defaults to '.'.",
            },
            "file_type": {
                "type": "string",
                "description": "Optional file type filter (e.g. 'py', 'js').",
            },
            "case_sensitive": {
                "type": "boolean",
                "description": "Case sensitive search. Defaults to false.",
            },
        },
        "required": ["pattern"],
    },
    function=code_search,
)

TOOLS: list[Tool] = [CODE_SEARCH_TOOL]
