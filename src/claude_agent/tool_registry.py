"""ToolRegistry — dynamic registration and plugin discovery for claude-agent tools."""

import importlib.util
from typing import TYPE_CHECKING, Any

from claude_agent.exceptions import PluginDiscoveryError, ToolRegistrationError
from claude_agent.tools import Tool

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


class ToolRegistry:
    """Owns the set of active tools and provides executor/API-def views over them.

    SOLID alignment
    ---------------
    SRP  — registration, lookup, API formatting, and executor creation live here.
           Tool implementations live in their own modules.
    OCP  — new tools are added via register_tool / discover_plugins, not by
           editing this class or tools.py.
    ISP  — callers that only need the executor Callable never have to import
           this class; main.py is the only composition root that does.
    DIP  — loop.py depends on the abstract Callable; only main.py knows about
           ToolRegistry.
    """

    def __init__(self) -> None:
        """Initialise an empty registry."""
        self._tools: list[Tool] = []
        self._names: set[str] = set()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_tool(self, tool: Tool) -> None:
        """Add *tool* to the registry.

        Raises ToolRegistrationError if a tool with the same name is already
        registered — duplicate names would make executor dispatch ambiguous.
        """
        if tool.name in self._names:
            msg = f"Tool '{tool.name}' is already registered"
            raise ToolRegistrationError(msg)
        self._tools.append(tool)
        self._names.add(tool.name)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_enabled_tools(self) -> list[Tool]:
        """Return a snapshot of registered tools in insertion order."""
        return list(self._tools)

    def build_api_defs(self) -> list[dict[str, Any]]:
        """Return the Anthropic API tool-definition list for the registered tools."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in self._tools
        ]

    # ------------------------------------------------------------------
    # Executor factory
    # ------------------------------------------------------------------

    def make_executor(self) -> Callable[[str, dict[str, Any]], tuple[str, bool]]:
        """Return a callable that dispatches tool calls by name.

        The executor captures the current registry state; tools registered
        after this call are *not* visible to the returned callable.
        This makes the executor's behaviour predictable for a given session.
        """
        dispatch: dict[str, Callable[[dict[str, Any]], str]] = {
            t.name: t.function for t in self._tools
        }

        def execute(name: str, tool_input: dict[str, Any]) -> tuple[str, bool]:
            """Execute the named tool and return (result, is_error)."""
            if name not in dispatch:
                return f"Tool '{name}' not found", True
            try:
                return dispatch[name](tool_input), False
            except Exception as exc:  # noqa: BLE001
                return str(exc), True

        return execute

    # ------------------------------------------------------------------
    # Plugin discovery
    # ------------------------------------------------------------------

    def discover_plugins(self, plugin_dir: Path) -> None:
        """Load tools from every public Python module in *plugin_dir*.

        Convention
        ----------
        A plugin module must export a ``TOOLS: list[Tool]`` attribute.
        Modules whose filename starts with ``_`` are skipped so that
        private helper modules and ``__init__.py`` are never loaded.

        Raises
        ------
        PluginDiscoveryError
            If *plugin_dir* does not exist.
        ToolRegistrationError
            If any tool name collides with an already-registered tool.

        """
        if not plugin_dir.exists():
            msg = f"Plugin directory does not exist: {plugin_dir}"
            raise PluginDiscoveryError(msg)

        for module_path in sorted(plugin_dir.glob("*.py")):
            if module_path.stem.startswith("_"):
                continue
            self._load_module(module_path)

    def _load_module(self, module_path: Path) -> None:
        """Import *module_path* and register any tools it exports."""
        spec = importlib.util.spec_from_file_location(module_path.stem, module_path)
        if spec is None or spec.loader is None:
            return
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]

        tools: list[Tool] | None = getattr(module, "TOOLS", None)
        if tools is None:
            return
        for tool in tools:
            self.register_tool(tool)
