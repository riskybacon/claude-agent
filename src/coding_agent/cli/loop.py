"""Main input loop — reads user input, dispatches commands, calls stream_response."""

from typing import TYPE_CHECKING, Any

from coding_agent.cli.commands import parse_command
from coding_agent.cli.protocols import InputReader, OutputWriter, StreamingClient
from coding_agent.cli.session import Session
from coding_agent.cli.streaming import stream_response

if TYPE_CHECKING:
    from collections.abc import Callable

_MAX_TOOL_RESULT_IN_HISTORY = 1000

_HELP_TEXT = """\
Available commands:
  /help           Show this message
  /clear          Reset conversation history
  /model <name>   Switch the active model
  /expand         Print the full output of the most recent tool call
"""


def run_loop(
    inp: InputReader,
    out: OutputWriter,
    client: StreamingClient,
    session: Session,
    tool_executor: Callable[[str, dict[str, Any]], tuple[str, bool]] | None = None,
) -> list[str]:
    """Run the main input loop; return a list of user messages forwarded to the agent."""
    forwarded: list[str] = []

    while True:
        line = inp.read()
        if line is None:
            break
        if not line.strip():
            continue

        cmd = parse_command(line)
        if cmd is not None:
            _dispatch(cmd.name, cmd.args, session, out)
            continue

        session.conversation.append({"role": "user", "content": line})
        forwarded.append(line)
        try:
            _run_turn(client, session, out, tool_executor)
        except Exception as exc:  # noqa: BLE001 — display all API/network errors, don't crash
            session.conversation.pop()
            forwarded.pop()
            out.print_error(str(exc))

    return forwarded


def _run_turn(
    client: StreamingClient,
    session: Session,
    out: OutputWriter,
    tool_executor: Callable[[str, dict[str, Any]], tuple[str, bool]] | None,
) -> None:
    """Stream one response and execute any tool calls until Claude stops calling tools."""
    while True:
        tool_uses: list[dict[str, Any]] = []
        stream_response(client, session, out, on_tool=tool_uses.append)

        if not tool_uses or tool_executor is None:
            break

        tool_results: list[dict[str, Any]] = []
        for tu in tool_uses:
            result, is_error = tool_executor(tu["name"], tu["input"])
            session.last_tool_result = result
            out.print_tool_line(tu["name"], tu["input"], result)
            _suffix = "\n…[truncated — use /expand to see full result]"
            stored = (
                result
                if len(result) <= _MAX_TOOL_RESULT_IN_HISTORY
                else result[:_MAX_TOOL_RESULT_IN_HISTORY] + _suffix
            )
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu["id"],
                "content": stored,
                "is_error": is_error,
            })

        session.conversation.append({"role": "user", "content": tool_results})


def _dispatch(name: str, args: list[str], session: Session, out: OutputWriter) -> None:
    """Execute a slash command."""
    if name == "clear":
        session.clear()
    elif name == "model" and args:
        session.switch_model(args[0])
    elif name == "expand":
        if session.last_tool_result is not None:
            out.print_expand(session.last_tool_result)
        else:
            out.print_error("No tool result to expand")
    elif name == "help":
        out.print_markdown(_HELP_TEXT)
    else:
        out.print_error(f"Unknown command: /{name}")
