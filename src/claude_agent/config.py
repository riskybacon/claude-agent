"""Configuration management for claude-agent."""

import os
import tomllib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class AgentConfig:
    """Centralized configuration for all claude-agent settings."""

    max_tool_result_history: int = 1000
    max_conversation_turns: int = 20
    bash_timeout_seconds: int = 120
    cost_hard_stop: float = 0.25
    max_tool_calls_per_turn: int = 20
    cost_injection_interval: int = 5
    max_search_matches: int = 50
    default_model: str = "claude-sonnet-4-20250514"
    system_prompt: str = """You are a coding assistant working in the user's local repository.

You have tools to read files, list directories, run shell commands, edit files, and search code.
Before making any changes, read the relevant files first so your edits are accurate.
Prefer targeted edits over rewriting entire files.
When you run a command to verify something, show the output to the user."""
    skip_dirs: set[str] = field(
        default_factory=lambda: {".git", ".pixi", "__pycache__", ".mypy_cache", ".ruff_cache"}
    )

    @classmethod
    def from_env(cls) -> AgentConfig:
        """Load configuration from environment variables."""
        # Get values from environment with CLAUDE_AGENT_ prefix
        bash_timeout = os.getenv("CLAUDE_AGENT_BASH_TIMEOUT")
        cost_hard_stop = os.getenv("CLAUDE_AGENT_COST_HARD_STOP")
        default_model = os.getenv("CLAUDE_AGENT_DEFAULT_MODEL")

        # Build kwargs for values that were provided
        kwargs = {}
        if bash_timeout is not None:
            kwargs["bash_timeout_seconds"] = int(bash_timeout)
        if cost_hard_stop is not None:
            kwargs["cost_hard_stop"] = float(cost_hard_stop)
        if default_model is not None:
            kwargs["default_model"] = default_model

        return cls(**kwargs)

    @classmethod
    def from_file(cls, path: Path) -> AgentConfig:
        """Load configuration from TOML file."""
        with path.open("rb") as f:
            data = tomllib.load(f)

        # Filter to only known configuration fields
        known_fields = {
            "max_tool_result_history",
            "max_conversation_turns",
            "bash_timeout_seconds",
            "cost_hard_stop",
            "max_tool_calls_per_turn",
            "cost_injection_interval",
            "max_search_matches",
            "default_model",
            "system_prompt",
        }

        kwargs = {k: v for k, v in data.items() if k in known_fields}
        return cls(**kwargs)

    @classmethod
    def from_sources(
        cls,
        config_file: Path | None = None,
        cli_args: dict[str, Any] | None = None
    ) -> AgentConfig:
        """Load configuration from multiple sources.

        Priority order: CLI args > env vars > config file > defaults.
        """
        # Start with defaults
        config_data = {}

        # Override with config file
        if config_file is not None:
            file_config = cls.from_file(config_file)
            config_data.update({
                k: v for k, v in file_config.__dict__.items()
                if not k.startswith("_")
            })

        # Override with environment variables
        env_config = cls.from_env()
        config_data.update({
            k: v for k, v in env_config.__dict__.items()
            if not k.startswith("_") and getattr(cls(), k) != v  # Only if different from default
        })

        # Override with CLI args
        if cli_args is not None:
            config_data.update(cli_args)

        return cls(**config_data)
