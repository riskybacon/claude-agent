"""Main input loop — reads user input, dispatches commands, calls stream_response."""

from typing import TYPE_CHECKING, Any

from claude_agent.cli.commands import parse_command
from claude_agent.cli.protocols import InputReader, OutputWriter, StreamingClient
from claude_agent.cli.session import Session
from claude_agent.cli.streaming import stream_response

if TYPE_CHECKING:
    from collections.abc import Callable

_MAX_TOOL_RESULT_IN_HISTORY = 1000
_MAX_TOOL_CALLS_PER_TURN = 20
_API_CALL_WARNING_THRESHOLD = 10

_HELP_TEXT = """\
Available commands:
  /help           Show this message
  /clear          Reset conversation history
  /model <name>   Switch the active model
  /expand         Print the full output of the most recent tool call
  /usage          Show API and tool call usage for this session

Cost control: Max 20 tool calls/turn, Ctrl-C to cancel, /usage to monitor
"""


def run_loop(  # noqa: PLR0913
    inp: InputReader,
    out: OutputWriter,
    client: StreamingClient,
    session: Session,
    tool_executor: Callable[[str, dict[str, Any]], tuple[str, bool]] | None = None,
    on_handle: Any = None,  # noqa: ANN401
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

        conv_len = len(session.conversation)
        session.conversation.append({"role": "user", "content": line})
        forwarded.append(line)
        try:
            _run_turn(client, session, out, tool_executor, on_handle)
        except KeyboardInterrupt:
            del session.conversation[conv_len:]
            forwarded.pop()
            out.print_markdown("\n*(cancelled)*")
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
    on_handle: Any = None,  # noqa: ANN401
) -> None:
    """Stream one response and execute any tool calls until Claude stops calling tools."""
    tool_calls_made = 0
    while True:
        tool_uses: list[dict[str, Any]] = []
        session.api_calls_made += 1

        if session.api_calls_made > _API_CALL_WARNING_THRESHOLD:
            out.print_error(
                f"Warning: {session.api_calls_made} API calls made this session"
                " - potential cost issue"
            )

        stream_response(client, session, out, on_tool=tool_uses.append, on_handle=on_handle)

        if not tool_uses or tool_executor is None:
            break

        tool_results: list[dict[str, Any]] = []
        for tu in tool_uses:
            if tool_calls_made >= _MAX_TOOL_CALLS_PER_TURN:
                out.print_error(
                    f"Hit tool call limit ({_MAX_TOOL_CALLS_PER_TURN})"
                    " - stopping to prevent runaway costs"
                )
                break

            tool_calls_made += 1
            session.tool_calls_made += 1

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

        session.conversation.append({"role": "user", "content": tool_results})  # type: ignore[typeddict-item]


def _dispatch(name: str, args: list[str], session: Session, out: OutputWriter) -> None:
    """Execute a slash command."""
    if name == "clear":
        session.clear()
        out.print_markdown("Conversation cleared.")
    elif name == "model" and args:
        session.switch_model(args[0])
        out.print_markdown(f"Model switched to **{args[0]}**.")
    elif name == "model":
        out.print_error("Usage: /model <name>")
    elif name == "expand":
        if session.last_tool_result is not None:
            out.print_expand(session.last_tool_result)
        else:
            out.print_error("No tool result to expand")
    elif name == "usage":
        out.print_markdown(
            f"**Session Usage:**\n- API calls: {session.api_calls_made}"
            f"\n- Tool calls: {session.tool_calls_made}"
        )
    elif name == "help":
        out.print_markdown(_HELP_TEXT)
    else:
        out.print_error(f"Unknown command: /{name}")
