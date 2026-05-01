"""Full coding agent — all tools combined."""

import sys
from typing import TYPE_CHECKING, Any

import anthropic

from coding_agent.tools import ALL_TOOLS, Tool

if TYPE_CHECKING:
    from collections.abc import Callable

SYSTEM_PROMPT = """You are a coding assistant working in the user's local repository.

You have tools to read files, list directories, run shell commands, edit files, and search code.
Before making any changes, read the relevant files first so your edits are accurate.
Prefer targeted edits over rewriting entire files.
When you run a command to verify something, show the output to the user."""


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
            system=SYSTEM_PROMPT,
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

    agent = Agent(client, get_user_message, ALL_TOOLS, verbose=verbose)
    agent.run()


if __name__ == "__main__":
    main()
