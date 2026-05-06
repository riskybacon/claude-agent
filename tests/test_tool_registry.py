"""Tests for ToolRegistry — registration, API formatting, execution, and plugin discovery."""

from pathlib import Path
from typing import Any

import pytest

import claude_agent.tools as _builtin_tools_pkg
from claude_agent.exceptions import PluginDiscoveryError, ToolRegistrationError
from claude_agent.tool_registry import ToolRegistry
from claude_agent.tools import Tool, ToolContext
from tests.fakes import FakeSession

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "plugins"


def _make_tool(name: str, *, fn: Any = None) -> Tool:  # noqa: ANN401
    """Build a minimal Tool for testing."""
    if fn is None:
        fn = lambda _input, _ctx: f"{name} result"  # noqa: E731
    return Tool(
        name=name,
        description=f"Description for {name}",
        input_schema={"type": "object", "properties": {}},
        function=fn,
    )


def _ctx() -> ToolContext:
    """Return a minimal ToolContext for tests."""
    return ToolContext(session=FakeSession())


# ---------------------------------------------------------------------------
# Phase 1 — core registration
# ---------------------------------------------------------------------------

def test_empty_registry_has_no_tools() -> None:
    """Fresh registry returns an empty list."""
    registry = ToolRegistry()
    assert registry.get_enabled_tools() == []


def test_empty_registry_build_api_defs_is_empty() -> None:
    """Fresh registry returns no API definitions."""
    registry = ToolRegistry()
    assert registry.build_api_defs() == []


def test_register_tool_makes_it_available() -> None:
    """A registered tool appears in get_enabled_tools."""
    registry = ToolRegistry()
    tool = _make_tool("read_file")
    registry.register_tool(tool)
    assert tool in registry.get_enabled_tools()


def test_register_multiple_tools_all_available() -> None:
    """All registered tools appear in get_enabled_tools."""
    registry = ToolRegistry()
    t1 = _make_tool("alpha")
    t2 = _make_tool("beta")
    registry.register_tool(t1)
    registry.register_tool(t2)
    assert registry.get_enabled_tools() == [t1, t2]


def test_register_preserves_insertion_order() -> None:
    """Tools are returned in registration order."""
    registry = ToolRegistry()
    names = ["charlie", "alpha", "beta"]
    tools = [_make_tool(n) for n in names]
    for t in tools:
        registry.register_tool(t)
    result_names = [t.name for t in registry.get_enabled_tools()]
    assert result_names == names


def test_register_duplicate_name_raises() -> None:
    """Registering the same tool name twice raises ToolRegistrationError."""
    registry = ToolRegistry()
    registry.register_tool(_make_tool("read_file"))
    with pytest.raises(ToolRegistrationError, match="read_file"):
        registry.register_tool(_make_tool("read_file"))


def test_get_enabled_tools_returns_copy() -> None:
    """Mutating the returned list does not affect the registry."""
    registry = ToolRegistry()
    registry.register_tool(_make_tool("alpha"))
    lst = registry.get_enabled_tools()
    lst.clear()
    assert len(registry.get_enabled_tools()) == 1


def test_build_api_defs_has_required_keys() -> None:
    """Each API definition contains name, description, and input_schema."""
    registry = ToolRegistry()
    tool = _make_tool("bash")
    registry.register_tool(tool)
    defs = registry.build_api_defs()
    assert len(defs) == 1
    defn = defs[0]
    assert defn["name"] == "bash"
    assert defn["description"] == tool.description
    assert defn["input_schema"] == tool.input_schema


def test_build_api_defs_contains_no_extra_keys() -> None:
    """API definitions contain exactly the three expected keys."""
    registry = ToolRegistry()
    registry.register_tool(_make_tool("bash"))
    defn = registry.build_api_defs()[0]
    assert set(defn.keys()) == {"name", "description", "input_schema"}


def test_build_api_defs_order_matches_registration() -> None:
    """build_api_defs preserves the same order as get_enabled_tools."""
    registry = ToolRegistry()
    for name in ["c", "a", "b"]:
        registry.register_tool(_make_tool(name))
    names = [d["name"] for d in registry.build_api_defs()]
    assert names == ["c", "a", "b"]


def test_executor_dispatches_by_name() -> None:
    """make_executor returns a callable that routes calls to the correct tool."""
    registry = ToolRegistry()
    registry.register_tool(_make_tool("greet", fn=lambda _input, _ctx: "hello"))
    executor = registry.make_executor(_ctx())
    result, is_error = executor("greet", {})
    assert result == "hello"
    assert is_error is False


def test_executor_passes_input_to_function() -> None:
    """The executor forwards tool_input unchanged to the tool function."""
    received: list[dict[str, Any]] = []

    def capture(tool_input: dict[str, Any], context: ToolContext) -> str:  # noqa: ARG001
        """Capture invocation args."""
        received.append(tool_input)
        return "ok"

    registry = ToolRegistry()
    registry.register_tool(_make_tool("capture", fn=capture))
    registry.make_executor(_ctx())("capture", {"key": "value"})
    assert received == [{"key": "value"}]


def test_executor_passes_context_to_function() -> None:
    """The executor forwards the bound ToolContext to every tool call."""
    received: list[ToolContext] = []

    def capture(_tool_input: dict[str, Any], context: ToolContext) -> str:
        """Capture the context passed in."""
        received.append(context)
        return "ok"

    ctx = _ctx()
    registry = ToolRegistry()
    registry.register_tool(_make_tool("capture", fn=capture))
    registry.make_executor(ctx)("capture", {})
    assert received == [ctx]


def test_executor_unknown_tool_returns_error_tuple() -> None:
    """Calling an unregistered tool name returns an error tuple."""
    registry = ToolRegistry()
    executor = registry.make_executor(_ctx())
    result, is_error = executor("nonexistent", {})
    assert is_error is True
    assert "nonexistent" in result


def test_executor_catches_tool_exception() -> None:
    """An exception raised by a tool is caught and returned as an error tuple."""
    def boom(_input: dict[str, Any], _ctx: ToolContext) -> str:
        """Raise unconditionally."""
        msg = "something broke"
        raise RuntimeError(msg)

    registry = ToolRegistry()
    registry.register_tool(_make_tool("boom", fn=boom))
    executor = registry.make_executor(_ctx())
    result, is_error = executor("boom", {})
    assert is_error is True
    assert "something broke" in result


def test_executor_snapshot_is_independent_of_later_registrations() -> None:
    """An executor created before a registration does not see the new tool."""
    registry = ToolRegistry()
    registry.register_tool(_make_tool("first"))
    executor = registry.make_executor(_ctx())
    registry.register_tool(_make_tool("second"))
    _, is_error = executor("second", {})
    assert is_error is True


# ---------------------------------------------------------------------------
# Phase 2 — plugin discovery
# ---------------------------------------------------------------------------

def test_discover_empty_dir_registers_nothing(tmp_path: Path) -> None:
    """Discovering an empty directory adds no tools."""
    registry = ToolRegistry()
    registry.discover_plugins(tmp_path)
    assert registry.get_enabled_tools() == []


def test_discover_loads_tools_from_valid_module() -> None:
    """A plugin module that exports TOOLS has all its tools registered."""
    registry = ToolRegistry()
    registry.discover_plugins(FIXTURES_DIR)
    names = [t.name for t in registry.get_enabled_tools()]
    assert "plugin_alpha" in names
    assert "plugin_beta" in names


def test_discover_skips_module_without_tools_attr() -> None:
    """A plugin module without a TOOLS attribute is silently skipped."""
    registry = ToolRegistry()
    registry.discover_plugins(FIXTURES_DIR)
    names = [t.name for t in registry.get_enabled_tools()]
    assert "no_tools_tool" not in names


def test_discover_skips_private_modules() -> None:
    """Modules whose filename starts with '_' are not loaded."""
    registry = ToolRegistry()
    registry.discover_plugins(FIXTURES_DIR)
    names = [t.name for t in registry.get_enabled_tools()]
    assert "private_tool" not in names


def test_discover_nonexistent_dir_raises() -> None:
    """Passing a non-existent directory raises PluginDiscoveryError."""
    registry = ToolRegistry()
    with pytest.raises(PluginDiscoveryError, match="does not exist"):
        registry.discover_plugins(Path("/nonexistent/plugin/dir"))


def test_discover_duplicate_across_plugins_raises(tmp_path: Path) -> None:
    """Two plugins registering the same tool name raises ToolRegistrationError."""
    tool_code = (
        "from claude_agent.tools import Tool\n"
        "TOOLS = [Tool(name='dup', description='d',"
        " input_schema={}, function=lambda _: 'ok')]\n"
    )
    (tmp_path / "plugin_a.py").write_text(tool_code)
    (tmp_path / "plugin_b.py").write_text(tool_code)
    registry = ToolRegistry()
    with pytest.raises(ToolRegistrationError, match="dup"):
        registry.discover_plugins(tmp_path)


def test_discover_can_be_called_on_multiple_dirs(tmp_path: Path) -> None:
    """Calling discover_plugins on two separate directories accumulates tools from both."""
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    (dir_a / "pa.py").write_text(
        "from claude_agent.tools import Tool\n"
        "TOOLS = [Tool(name='from_a', description='d',"
        " input_schema={}, function=lambda _: 'ok')]\n"
    )
    (dir_b / "pb.py").write_text(
        "from claude_agent.tools import Tool\n"
        "TOOLS = [Tool(name='from_b', description='d',"
        " input_schema={}, function=lambda _: 'ok')]\n"
    )
    registry = ToolRegistry()
    registry.discover_plugins(dir_a)
    registry.discover_plugins(dir_b)
    names = [t.name for t in registry.get_enabled_tools()]
    assert "from_a" in names
    assert "from_b" in names


# ---------------------------------------------------------------------------
# Built-in tools package discoverability
# ---------------------------------------------------------------------------

def test_builtin_tools_package_is_discoverable() -> None:
    """All five built-in tools are discoverable via the tools package directory."""
    tools_dir = Path(_builtin_tools_pkg.__file__).parent  # type: ignore[arg-type]
    registry = ToolRegistry()
    registry.discover_plugins(tools_dir)
    names = {t.name for t in registry.get_enabled_tools()}
    assert names == {"read_file", "list_files", "bash", "edit_file", "code_search", "check_cost"}
