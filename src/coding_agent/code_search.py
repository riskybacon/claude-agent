"""Step 6: Add a code_search tool backed by ripgrep."""

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import anthropic

if TYPE_CHECKING:
    from collections.abc import Callable

_MAX_MATCHES = 50


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
# code_search tool
# ---------------------------------------------------------------------------

CODE_SEARCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "pattern": {
            "type": "string",
            "description": "The search pattern or regex to look for.",
        },
        "path": {
            "type": "string",
            "description": "Optional path to search in (file or directory). Defaults to '.'.",
        },
        "file_type": {
            "type": "string",
            "description": "Optional file type to limit search to (e.g. 'py', 'js', 'go').",
        },
        "case_sensitive": {
            "type": "boolean",
            "description": "Whether the search is case sensitive. Defaults to false.",
        },
    },
    "required": ["pattern"],
}


def code_search(tool_input: dict[str, Any]) -> str:
    """Search for a pattern using ripgrep; return matching lines with file and line number.

    ripgrep exits with code 1 when there are no matches — that is not an error.
    Output is capped at 50 matches to keep responses manageable.
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

    result = subprocess.run(args, capture_output=True, text=True, check=False)  # noqa: S603

    # Exit code 1 means no matches — not a tool failure.
    if result.returncode == 1:
        return "No matches found"
    if result.returncode != 0:
        msg = f"search failed: {result.stderr.strip()}"
        raise RuntimeError(msg)

    lines = result.stdout.strip().splitlines()
    if len(lines) > _MAX_MATCHES:
        truncated = "\n".join(lines[:_MAX_MATCHES])
        return f"{truncated}\n... (showing first {_MAX_MATCHES} of {len(lines)} matches)"
    return result.stdout.strip()


CODE_SEARCH_TOOL = Tool(
    name="code_search",
    description=(
        "Search for code patterns using ripgrep (rg).\n\n"
        "Use this to find function definitions, variable usage, or any text in the codebase. "
        "You can filter by file type or directory."
    ),
    input_schema=CODE_SEARCH_SCHEMA,
    function=code_search,
)


# ---------------------------------------------------------------------------
# Agent (unchanged from step 5)
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

    # Note: edit_file is not included in this step — code_search replaces it.
    tools = [READ_FILE_TOOL, LIST_FILES_TOOL, BASH_TOOL, CODE_SEARCH_TOOL]
    agent = Agent(client, get_user_message, tools, verbose=verbose)
    agent.run()


if __name__ == "__main__":
    main()
