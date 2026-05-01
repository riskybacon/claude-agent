"""Main input loop — reads user input, dispatches commands, calls stream_response."""

from coding_agent.cli.commands import parse_command
from coding_agent.cli.protocols import InputReader, OutputWriter, StreamingClient
from coding_agent.cli.session import Session
from coding_agent.cli.streaming import stream_response

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
        stream_response(client, session, out)

    return forwarded


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
