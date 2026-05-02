"""All tool definitions for the claude-agent."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from claude_agent.exceptions import FileSystemError

if TYPE_CHECKING:
    from collections.abc import Callable

_MAX_SEARCH_MATCHES = 50
_SKIP_DIRS = {".git", ".pixi", "__pycache__", ".mypy_cache", ".ruff_cache"}


@dataclass
class Tool:
    """Bundles a tool's metadata and its callable implementation."""

    name: str
    description: str
    input_schema: dict[str, Any]
    function: Callable[[dict[str, Any]], str]


# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------

def read_file(tool_input: dict[str, Any]) -> str:
    """Return the contents of the file at the given path."""
    path = Path(tool_input["path"])
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        msg = f"File not found: {path}"
        raise FileSystemError("read_file", msg) from None
    except PermissionError:
        msg = f"Permission denied: {path}"
        raise FileSystemError("read_file", msg) from None
    except IsADirectoryError:
        msg = f"Path is a directory, not a file: {path}"
        raise FileSystemError("read_file", msg) from None
    except UnicodeDecodeError as e:
        msg = f"File contains non-UTF-8 content: {path} ({e})"
        raise FileSystemError("read_file", msg) from None
    except OSError as e:
        msg = f"OS error reading {path}: {e}"
        raise FileSystemError("read_file", msg) from None


READ_FILE_TOOL = Tool(
    name="read_file",
    description=(
        "Read the contents of a given relative file path. "
        "Use this when you want to see what's inside a file. "
        "Do not use this with directory names."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The relative path of a file in the working directory.",
            }
        },
        "required": ["path"],
    },
    function=read_file,
)


# ---------------------------------------------------------------------------
# list_files
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# bash
# ---------------------------------------------------------------------------

_BASH_TIMEOUT_SECONDS = 120


def bash(tool_input: dict[str, Any]) -> str:
    """Run a bash command and return its output (stdout + stderr combined).

    Command failures are returned as output rather than raised as exceptions
    so Claude can read the error and decide how to proceed.
    """
    try:
        result = subprocess.run(  # noqa: S603
            ["bash", "-c", tool_input["command"]],  # noqa: S607
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
            timeout=_BASH_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return f"Command timed out after {_BASH_TIMEOUT_SECONDS} seconds"
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


# ---------------------------------------------------------------------------
# edit_file
# ---------------------------------------------------------------------------

def edit_file(tool_input: dict[str, Any]) -> str:
    """Create, append to, or perform a unique string replacement in a file.

    Three cases based on old_str and whether the file exists:
      - old_str == "" and file missing  → create file (with parent dirs)
      - old_str == "" and file exists   → append new_str to the file
      - old_str != ""                   → replace exactly one occurrence
    """
    path_str: str = tool_input["path"]
    old_str: str = tool_input["old_str"]
    new_str: str = tool_input["new_str"]

    if not path_str:
        msg = "path must not be empty"
        raise ValueError(msg)
    if old_str == new_str:
        msg = "old_str and new_str must differ"
        raise ValueError(msg)

    file_path = Path(path_str)

    if not file_path.exists():
        if old_str == "":
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(new_str)
            return f"Successfully created {path_str}"
        msg = f"file not found: {path_str}"
        raise FileNotFoundError(msg)

    content = file_path.read_text()

    if old_str == "":
        file_path.write_text(content + new_str)
        return "OK"

    count = content.count(old_str)
    if count == 0:
        msg = "old_str not found in file"
        raise ValueError(msg)
    if count > 1:
        msg = f"old_str found {count} times in file — must be unique"
        raise ValueError(msg)

    file_path.write_text(content.replace(old_str, new_str, 1))
    return "OK"


EDIT_FILE_TOOL = Tool(
    name="edit_file",
    description=(
        "Make edits to a text file.\n\n"
        "Replaces 'old_str' with 'new_str' in the given file. "
        "'old_str' and 'new_str' MUST be different from each other.\n\n"
        "If the file specified with path doesn't exist, it will be created."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "The path to the file."},
            "old_str": {
                "type": "string",
                "description": (
                    "Text to search for — must match exactly and appear exactly once. "
                    "Pass an empty string to create a new file or append to an existing one."
                ),
            },
            "new_str": {"type": "string", "description": "Text to replace old_str with."},
        },
        "required": ["path", "old_str", "new_str"],
    },
    function=edit_file,
)


# ---------------------------------------------------------------------------
# code_search
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Full tool list
# ---------------------------------------------------------------------------

ALL_TOOLS: list[Tool] = [
    READ_FILE_TOOL,
    LIST_FILES_TOOL,
    BASH_TOOL,
    EDIT_FILE_TOOL,
    CODE_SEARCH_TOOL,
]
