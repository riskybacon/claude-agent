"""Valid plugin fixture — exports a TOOLS list with two tools."""

from claude_agent.tools import Tool

TOOLS: list[Tool] = [
    Tool(
        name="plugin_alpha",
        description="Alpha tool from valid_plugin fixture",
        input_schema={"type": "object", "properties": {}},
        function=lambda _: "alpha result",
    ),
    Tool(
        name="plugin_beta",
        description="Beta tool from valid_plugin fixture",
        input_schema={"type": "object", "properties": {}},
        function=lambda _: "beta result",
    ),
]
