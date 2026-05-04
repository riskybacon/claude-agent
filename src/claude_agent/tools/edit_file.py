"""edit_file tool — create, append to, or string-replace a file."""

from pathlib import Path
from typing import Any

from claude_agent.tools import Tool


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

TOOLS: list[Tool] = [EDIT_FILE_TOOL]
