"""Slash command parsing for the CLI."""

from dataclasses import dataclass, field


@dataclass
class ParsedCommand:
    """A parsed slash command with its name and arguments."""

    name: str
    args: list[str] = field(default_factory=list)


def parse_command(text: str) -> ParsedCommand | None:
    """Return a ParsedCommand if text is a slash command, else None."""
    if not text.startswith("/"):
        return None
    parts = text[1:].split()
    if not parts:
        return None
    return ParsedCommand(name=parts[0], args=parts[1:])
