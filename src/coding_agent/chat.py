"""Step 1: Basic chat with Claude — no tools."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import anthropic

if TYPE_CHECKING:
    from collections.abc import Callable


def main() -> None:
    """Entry point — parse args, wire up the agent, and run it."""
    verbose = "--verbose" in sys.argv

    client = anthropic.Anthropic()

    if verbose:
        print("[verbose] Anthropic client initialized", file=sys.stderr)

    def get_user_message() -> tuple[str, bool]:
        """Read one line from stdin; return (text, ok)."""
        try:
            return input(), True
        except EOFError:
            return "", False

    agent = Agent(client, get_user_message, verbose=verbose)
    agent.run()


class Agent:
    """Chat agent that maintains a conversation with Claude."""

    def __init__(
        self,
        client: anthropic.Anthropic,
        get_user_message: Callable[[], tuple[str, bool]],
        *,
        verbose: bool = False,
    ) -> None:
        """Initialise the agent with a client and input source."""
        self.client = client
        self.get_user_message = get_user_message
        self.verbose = verbose

    def run(self) -> None:
        """Run the main event loop: read → send → display, until EOF."""
        conversation: list[anthropic.types.MessageParam] = []

        if self.verbose:
            print("[verbose] Starting chat session", file=sys.stderr)

        print("Chat with Claude (use 'ctrl-c' to quit)")

        while True:
            print("\033[94mYou\033[0m: ", end="", flush=True)
            user_input, ok = self.get_user_message()
            if not ok:
                break
            if not user_input.strip():
                continue

            if self.verbose:
                print(f"[verbose] User input: {user_input!r}", file=sys.stderr)

            conversation.append({"role": "user", "content": user_input})

            message = self.run_inference(conversation)
            conversation.append({"role": "assistant", "content": message.content})

            for block in message.content:
                if block.type == "text":
                    print(f"\033[93mClaude\033[0m: {block.text}")

        if self.verbose:
            print("[verbose] Chat session ended", file=sys.stderr)

    def run_inference(
        self, conversation: list[anthropic.types.MessageParam]
    ) -> anthropic.types.Message:
        """Send the conversation to Claude and return its response."""
        if self.verbose:
            print(
                f"[verbose] Calling API, conversation length: {len(conversation)}",
                file=sys.stderr,
            )

        message = self.client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1024,
            messages=conversation,
        )

        if self.verbose:
            print("[verbose] API call successful", file=sys.stderr)

        return message


if __name__ == "__main__":
    main()
