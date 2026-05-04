"""list_files tool — recursively list files under a directory."""

import json
from pathlib import Path
from typing import Any

from claude_agent.tools import Tool

_SKIP_DIRS = {".git", ".pixi", "__pycache__", ".mypy_cache", ".ruff_cache"}


def _collect(root: Path, current: Path, entries: list[str]) -> None:
    """Recursively collect file/dir paths in lexical DFS order."""
    for item in sorted(current.iterdir(), key=lambda p: p.name):
        if item.is_dir():
            if item.name in _SKIP_DIRS:
                continue
            entries.append(str(item.relative_to(root)) + "/")
            _collect(root, item, entries)
        else:
            entries.append(str(item.relative_to(root)))


def list_files(tool_input: dict[str, Any]) -> str:
    """Return a JSON array of paths under the given directory."""
    root = Path(tool_input.get("path", "."))
    entries: list[str] = []
    _collect(root, root, entries)
    return json.dumps(entries)


LIST_FILES_TOOL = Tool(
    name="list_files",
    description=(
        "List files and directories at a given path. "
        "If no path is provided, lists files in the current directory."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path to list. Defaults to current directory.",
            }
        },
    },
    function=list_files,
)

TOOLS: list[Tool] = [LIST_FILES_TOOL]
