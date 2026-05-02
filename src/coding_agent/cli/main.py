"""CLI entry point — wires real implementations and runs the input loop."""

import argparse
import signal
import sys
from pathlib import Path
from typing import Any

import anthropic

from coding_agent.cli.input import PromptToolkitInput
from coding_agent.cli.loop import run_loop
from coding_agent.cli.output import RichOutput
from coding_agent.cli.session import Session
from coding_agent.cli.streaming import AnthropicStream
from coding_agent.tools import ALL_TOOLS

_DEFAULT_MODEL = "claude-sonnet-4-20250514"

_SYSTEM_PROMPT = """You are a coding assistant working in the user's local repository.

You have tools to read files, list directories, run shell commands, edit files, and search code.
Before making any changes, read the relevant files first so your edits are accurate.
Prefer targeted edits over rewriting entire files.
When you run a command to verify something, show the output to the user."""


def _load_claude_md(start: Path) -> tuple[Path, str] | None:
    """Walk up from start, return (path, content) of the first CLAUDE.md found."""
    for directory in [start, *start.parents]:
        candidate = directory / "CLAUDE.md"
        if candidate.is_file():
            return candidate, candidate.read_text()
    return None


def _build_tools() -> list[dict[str, Any]]:
    return [
        {"name": t.name, "description": t.description, "input_schema": t.input_schema}
        for t in ALL_TOOLS
    ]


def _make_executor() -> Any:  # noqa: ANN401
    def execute(name: str, tool_input: dict[str, Any]) -> tuple[str, bool]:
        for tool in ALL_TOOLS:
            if tool.name == name:
                try:
                    return tool.function(tool_input), False
                except Exception as exc:  # noqa: BLE001
                    return str(exc), True
        return f"Tool '{name}' not found", True
    return execute


def main() -> None:
    """Parse args, wire real implementations, run the loop."""
    parser = argparse.ArgumentParser(description="coding-agent CLI")
    parser.add_argument("--model", default=_DEFAULT_MODEL, help="Model to use")
    parser.add_argument("--system", help="Path to a file containing a custom system prompt")
    parser.add_argument("--verbose", action="store_true", help="Print full tool results inline")
    args = parser.parse_args()

    system_prompt = _SYSTEM_PROMPT
    if args.system:
        system_prompt = Path(args.system).read_text()

    claude_md = _load_claude_md(Path.cwd())
    if claude_md is not None:
        claude_md_path, claude_md_content = claude_md
        system_prompt = system_prompt + "\n\n" + claude_md_content

    session = Session(
        model=args.model,
        system_prompt=system_prompt,
        tools=_build_tools(),
    )

    client = AnthropicStream(anthropic.Anthropic())
    inp = PromptToolkitInput()
    out = RichOutput(verbose=args.verbose)

    active_handle: list[Any] = [None]

    def _on_sigint(signum: int, frame: object) -> None:  # noqa: ARG001
        if active_handle[0] is not None:
            active_handle[0].cancel()

    signal.signal(signal.SIGINT, _on_sigint)

    def _store_handle(h: Any) -> None:  # noqa: ANN401
        active_handle[0] = h

    out.print_markdown("**coding-agent** — type `/help` for commands, Ctrl+D to exit\n")
    if claude_md is not None:
        out.print_markdown(f"Using **CLAUDE.md** from `{claude_md_path}`\n")

    run_loop(inp, out, client, session, tool_executor=_make_executor(), on_handle=_store_handle)

    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
