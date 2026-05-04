"""Custom exceptions for claude-agent."""


class ClaudeAgentError(Exception):
    """Base exception for all claude-agent errors."""


class ToolExecutionError(ClaudeAgentError):
    """Error during tool execution that should be reported to Claude."""

    def __init__(self, tool_name: str, message: str, *, recoverable: bool = True) -> None:
        """Initialize with tool name, error message, and recoverability flag."""
        super().__init__(f"Tool '{tool_name}' failed: {message}")
        self.tool_name = tool_name
        self.original_message = message
        self.recoverable = recoverable


class FileSystemError(ToolExecutionError):
    """File system operation failed."""


class ProcessExecutionError(ToolExecutionError):
    """Process execution failed."""


class NetworkError(ClaudeAgentError):
    """Network-related error (API calls, etc.)."""


class ConfigurationError(ClaudeAgentError):
    """Configuration or setup error."""


class ToolRegistrationError(ClaudeAgentError):
    """Raised when a tool cannot be registered (e.g. duplicate name)."""


class PluginDiscoveryError(ClaudeAgentError):
    """Raised when plugin discovery fails (e.g. directory does not exist)."""
