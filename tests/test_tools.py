"""Tests for tool implementations."""

import subprocess
from unittest.mock import patch

from claude_agent.config import AgentConfig
from claude_agent.tools import ToolContext
from claude_agent.tools.bash import _BASH_TIMEOUT_SECONDS, bash
from tests.fakes import FakeSession


def _ctx(config: AgentConfig | None = None) -> ToolContext:
    """Return a minimal ToolContext for bash tests."""
    return ToolContext(session=FakeSession(), config=config)


def test_bash_timeout_returns_message() -> None:
    """Bash commands that exceed timeout return a friendly message."""
    with patch("claude_agent.tools.bash.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=120)
        result = bash({"command": "sleep 999"}, _ctx())
    assert f"timed out after {_BASH_TIMEOUT_SECONDS} seconds" in result


def test_bash_passes_timeout_to_subprocess() -> None:
    """Bash tool passes timeout argument to subprocess.run."""
    with patch("claude_agent.tools.bash.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "output"
        bash({"command": "echo hi"}, _ctx())
    _, kwargs = mock_run.call_args
    assert kwargs["timeout"] == _BASH_TIMEOUT_SECONDS


def test_bash_uses_config_timeout_from_context() -> None:
    """Bash tool reads timeout from context.config when present."""
    expected_timeout = 60
    config = AgentConfig(bash_timeout_seconds=expected_timeout)
    with patch("claude_agent.tools.bash.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "output"
        bash({"command": "echo hi"}, _ctx(config=config))
    _, kwargs = mock_run.call_args
    assert kwargs["timeout"] == expected_timeout
