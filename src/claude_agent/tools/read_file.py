"""read_file tool — return the UTF-8 contents of a file."""

from pathlib import Path
from typing import Any

from claude_agent.exceptions import FileSystemError
from claude_agent.tools import Tool


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

TOOLS: list[Tool] = [READ_FILE_TOOL]
