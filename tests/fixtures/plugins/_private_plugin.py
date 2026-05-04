"""Private plugin fixture — must be skipped because the filename starts with '_'."""

from claude_agent.tools import Tool

TOOLS: list[Tool] = [
    Tool(
        name="private_tool",
        description="Should never be registered",
        input_schema={"type": "object", "properties": {}},
        function=lambda _: "private result",
    ),
]
