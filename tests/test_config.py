"""Tests for AgentConfig configuration management."""

from typing import TYPE_CHECKING

from claude_agent.config import AgentConfig

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_agent_config_has_expected_defaults() -> None:
    """AgentConfig should initialize with sensible defaults."""
    config = AgentConfig()

    # Check all expected defaults
    expected_max_tool_result_history = 1000
    expected_max_conversation_turns = 20
    expected_bash_timeout_seconds = 120
    expected_cost_hard_stop = 0.25
    expected_max_tool_calls_per_turn = 20
    expected_cost_injection_interval = 5
    expected_max_search_matches = 50
    expected_model = "claude-sonnet-4-20250514"
    expected_skip_dirs = {".git", ".pixi", "__pycache__", ".mypy_cache", ".ruff_cache"}

    assert config.max_tool_result_history == expected_max_tool_result_history
    assert config.max_conversation_turns == expected_max_conversation_turns
    assert config.bash_timeout_seconds == expected_bash_timeout_seconds
    assert config.cost_hard_stop == expected_cost_hard_stop
    assert config.max_tool_calls_per_turn == expected_max_tool_calls_per_turn
    assert config.cost_injection_interval == expected_cost_injection_interval
    assert config.max_search_matches == expected_max_search_matches
    assert config.default_model == expected_model
    assert "coding assistant" in config.system_prompt
    assert config.skip_dirs == expected_skip_dirs


def test_agent_config_accepts_custom_values() -> None:
    """AgentConfig should accept custom values for all parameters."""
    custom_max_tool_result_history = 2000
    custom_max_conversation_turns = 10
    custom_bash_timeout_seconds = 60
    custom_cost_hard_stop = 0.50
    custom_max_tool_calls_per_turn = 15
    custom_default_model = "claude-opus-3"

    config = AgentConfig(
        max_tool_result_history=custom_max_tool_result_history,
        max_conversation_turns=custom_max_conversation_turns,
        bash_timeout_seconds=custom_bash_timeout_seconds,
        cost_hard_stop=custom_cost_hard_stop,
        max_tool_calls_per_turn=custom_max_tool_calls_per_turn,
        default_model=custom_default_model,
    )
    assert config.max_tool_result_history == custom_max_tool_result_history
    assert config.max_conversation_turns == custom_max_conversation_turns
    assert config.bash_timeout_seconds == custom_bash_timeout_seconds
    assert config.cost_hard_stop == custom_cost_hard_stop
    assert config.max_tool_calls_per_turn == custom_max_tool_calls_per_turn
    assert config.default_model == custom_default_model


def test_config_from_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    """AgentConfig should load values from environment variables."""
    monkeypatch.setenv("CLAUDE_AGENT_BASH_TIMEOUT", "180")
    monkeypatch.setenv("CLAUDE_AGENT_COST_HARD_STOP", "0.50")
    monkeypatch.setenv("CLAUDE_AGENT_DEFAULT_MODEL", "claude-opus-3")

    config = AgentConfig.from_env()

    expected_bash_timeout = 180
    expected_cost_hard_stop = 0.50
    expected_model = "claude-opus-3"

    assert config.bash_timeout_seconds == expected_bash_timeout
    assert config.cost_hard_stop == expected_cost_hard_stop
    assert config.default_model == expected_model


def test_config_from_file(tmp_path: Path) -> None:
    """AgentConfig should load from TOML configuration file."""
    config_file = tmp_path / "config.toml"
    config_file.write_text("""
    max_tool_result_history = 2000
    bash_timeout_seconds = 180
    cost_hard_stop = 0.30
    default_model = "claude-opus-3"
    """)

    config = AgentConfig.from_file(config_file)

    expected_max_tool_result_history = 2000
    expected_bash_timeout_seconds = 180
    expected_cost_hard_stop = 0.30
    expected_default_model = "claude-opus-3"

    assert config.max_tool_result_history == expected_max_tool_result_history
    assert config.bash_timeout_seconds == expected_bash_timeout_seconds
    assert config.cost_hard_stop == expected_cost_hard_stop
    assert config.default_model == expected_default_model


def test_config_priority_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI args > env vars > config file > defaults."""
    # Config file
    config_file = tmp_path / "config.toml"
    config_file.write_text("bash_timeout_seconds = 100")

    # Environment variable
    monkeypatch.setenv("CLAUDE_AGENT_BASH_TIMEOUT", "200")

    # CLI args override both
    config = AgentConfig.from_sources(
        config_file=config_file,
        cli_args={"bash_timeout_seconds": 300}
    )

    expected_bash_timeout = 300
    assert config.bash_timeout_seconds == expected_bash_timeout
