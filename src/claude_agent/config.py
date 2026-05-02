"""Configuration management for claude-agent."""

from dataclasses import dataclass, field


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
