"""Step 5: Add an edit_file tool."""

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import anthropic

if TYPE_CHECKING:
    from collections.abc import Callable


# ---------------------------------------------------------------------------
# Tool infrastructure (unchanged from step 2)
# ---------------------------------------------------------------------------

@dataclass
class Tool:
    """Bundles a tool's metadata and its callable implementation."""

    name: str
    description: str
    input_schema: dict[str, Any]
    function: Callable[[dict[str, Any]], str]


# ---------------------------------------------------------------------------
# read_file tool (carried forward unchanged)
# ---------------------------------------------------------------------------

READ_FILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "The relative path of a file in the working directory.",
        }
    },
    "required": ["path"],
}


def read_file(tool_input: dict[str, Any]) -> str:
    """Return the contents of the file at the given path."""
    return Path(tool_input["path"]).read_text()


READ_FILE_TOOL = Tool(
    name="read_file",
    description=(
        "Read the contents of a given relative file path. "
        "Use this when you want to see what's inside a file. "
        "Do not use this with directory names."
    ),
    input_schema=READ_FILE_SCHEMA,
    function=read_file,
)


# ---------------------------------------------------------------------------
# list_files tool (carried forward unchanged)
# ---------------------------------------------------------------------------

LIST_FILES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Relative path to list. Defaults to current directory.",
        }
    },
}

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
    input_schema=LIST_FILES_SCHEMA,
    function=list_files,
)


# ---------------------------------------------------------------------------
# bash tool (carried forward unchanged)
# ---------------------------------------------------------------------------

BASH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "command": {
            "type": "string",
            "description": "The bash command to execute.",
        }
    },
    "required": ["command"],
}


def bash(tool_input: dict[str, Any]) -> str:
    """Run a bash command and return its output (stdout + stderr combined).

    Command failures are returned as output rather than raised as exceptions
    so Claude can read the error and decide how to proceed.
    """
    result = subprocess.run(  # noqa: S603
        ["bash", "-c", tool_input["command"]],  # noqa: S607
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return f"Command failed (exit {result.returncode}):\n{result.stdout.strip()}"
    return result.stdout.strip()


BASH_TOOL = Tool(
    name="bash",
    description="Execute a bash command and return its output. Use this to run shell commands.",
    input_schema=BASH_SCHEMA,
    function=bash,
)


# ---------------------------------------------------------------------------
# edit_file tool
# ---------------------------------------------------------------------------

EDIT_FILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "The path to the file.",
        },
        "old_str": {
            "type": "string",
            "description": (
                "Text to search for — must match exactly and appear exactly once. "
                "Pass an empty string to create a new file or append to an existing one."
            ),
        },
        "new_str": {
            "type": "string",
            "description": "Text to replace old_str with.",
        },
    },
    "required": ["path", "old_str", "new_str"],
}


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
    input_schema=EDIT_FILE_SCHEMA,
    function=edit_file,
)


# ---------------------------------------------------------------------------
# Agent (unchanged from step 2, except _execute_tool catches all exceptions
# since edit_file raises ValueError in addition to OSError)
# ---------------------------------------------------------------------------

class Agent:
    """Chat agent with tool-use support."""

    def __init__(
        self,
        client: anthropic.Anthropic,
        get_user_message: Callable[[], tuple[str, bool]],
        tools: list[Tool],
        *,
        verbose: bool = False,
    ) -> None:
        """Initialise the agent with a client, input source, and tool list."""
        self.client = client
        self.get_user_message = get_user_message
        self.tools = tools
        self.verbose = verbose

    def run(self) -> None:
        """Outer loop: read user input, hand off to the tool loop, repeat."""
        conversation: list[anthropic.types.MessageParam] = []

        if self.verbose:
            print(f"[verbose] Starting session with {len(self.tools)} tool(s)", file=sys.stderr)

        print("Chat with Claude (use 'ctrl-c' to quit)")

        while True:
            print("\033[94mYou\033[0m: ", end="", flush=True)
            user_input, ok = self.get_user_message()
            if not ok:
                break
            if not user_input.strip():
                continue

            conversation.append({"role": "user", "content": user_input})
            message = self.run_inference(conversation)
            conversation.append({"role": "assistant", "content": message.content})
            self._run_tool_loop(message, conversation)

        if self.verbose:
            print("[verbose] Chat session ended", file=sys.stderr)

    def _run_tool_loop(
        self,
        message: anthropic.types.Message,
        conversation: list[anthropic.types.MessageParam],
    ) -> None:
        """Process tool calls until Claude responds with no tool_use blocks."""
        while True:
            tool_results: list[anthropic.types.ToolResultBlockParam] = []

            for block in message.content:
                if block.type == "text":
                    print(f"\033[93mClaude\033[0m: {block.text}")
                elif block.type == "tool_use":
                    print(f"\033[96mtool\033[0m: {block.name}({block.input})")
                    result, is_error = self._execute_tool(block.name, block.input)  # type: ignore[arg-type]
                    print(f"\033[92mresult\033[0m: {result}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                        "is_error": is_error,
                    })

            if not tool_results:
                break

            conversation.append({"role": "user", "content": tool_results})
            message = self.run_inference(conversation)
            conversation.append({"role": "assistant", "content": message.content})

    def _execute_tool(self, name: str, tool_input: dict[str, Any]) -> tuple[str, bool]:
        """Find and call the named tool; return (result, is_error)."""
        for tool in self.tools:
            if tool.name == name:
                if self.verbose:
                    print(f"[verbose] Executing tool: {name}", file=sys.stderr)
                try:
                    return tool.function(tool_input), False
                except Exception as exc:  # noqa: BLE001 — tool dispatcher catches all tool errors
                    return str(exc), True

        return f"Tool '{name}' not found", True

    def run_inference(
        self, conversation: list[anthropic.types.MessageParam]
    ) -> anthropic.types.Message:
        """Call the Claude API and return its response."""
        if self.verbose:
            print(
                f"[verbose] API call, conversation length: {len(conversation)}",
                file=sys.stderr,
            )

        return self.client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1024,
            tools=[
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
                for t in self.tools
            ],
            messages=conversation,
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Parse args, build the agent, run it."""
    verbose = "--verbose" in sys.argv

    client = anthropic.Anthropic()

    def get_user_message() -> tuple[str, bool]:
        """Read one line from stdin; return (text, ok)."""
        try:
            return input(), True
        except EOFError:
            return "", False

    tools = [READ_FILE_TOOL, LIST_FILES_TOOL, BASH_TOOL, EDIT_FILE_TOOL]
    agent = Agent(client, get_user_message, tools, verbose=verbose)
    agent.run()


if __name__ == "__main__":
    main()
