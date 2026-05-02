# 🧪 **TDD Plan: Enhanced Configuration Management (#1)**

## **Phase 1: Core AgentConfig Class**

### **Test 1.1: AgentConfig Creation and Defaults** 
```python
# tests/test_config.py
def test_agent_config_has_expected_defaults():
    """AgentConfig should initialize with sensible defaults."""
    config = AgentConfig()
    assert config.max_tool_result_history == 1000
    assert config.max_conversation_turns == 20
    assert config.bash_timeout_seconds == 120
    assert config.cost_hard_stop == 0.25
    assert config.max_tool_calls_per_turn == 20
    assert config.cost_injection_interval == 5
    assert config.max_search_matches == 50
    assert config.default_model == "claude-sonnet-4-20250514"
    assert "coding assistant" in config.system_prompt
    assert config.skip_dirs == {".git", ".pixi", "__pycache__", ".mypy_cache", ".ruff_cache"}
```

### **Test 1.2: AgentConfig Custom Values**
```python
def test_agent_config_accepts_custom_values():
    """AgentConfig should accept custom values for all parameters."""
    config = AgentConfig(
        max_tool_result_history=2000,
        max_conversation_turns=10,
        bash_timeout_seconds=60,
        cost_hard_stop=0.50,
        max_tool_calls_per_turn=15,
        default_model="claude-opus-3",
    )
    assert config.max_tool_result_history == 2000
    assert config.max_conversation_turns == 10
    assert config.bash_timeout_seconds == 60
    assert config.cost_hard_stop == 0.50
    assert config.max_tool_calls_per_turn == 15
    assert config.default_model == "claude-opus-3"
```

### **Implementation 1: Create AgentConfig**
```python
# src/claude_agent/config.py
@dataclass
class AgentConfig:
    max_tool_result_history: int = 1000
    max_conversation_turns: int = 20
    bash_timeout_seconds: int = 120
    cost_hard_stop: float = 0.25
    max_tool_calls_per_turn: int = 20
    cost_injection_interval: int = 5
    max_search_matches: int = 50
    default_model: str = "claude-sonnet-4-20250514"
    system_prompt: str = "..."  # Move from main.py
    skip_dirs: set[str] = field(default_factory=lambda: {".git", ".pixi", "__pycache__", ".mypy_cache", ".ruff_cache"})
```

## **Phase 2: Configuration Loading**

### **Test 2.1: Environment Variable Loading**
```python
def test_config_from_environment_variables(monkeypatch):
    """AgentConfig should load values from environment variables."""
    monkeypatch.setenv("CLAUDE_AGENT_BASH_TIMEOUT", "180")
    monkeypatch.setenv("CLAUDE_AGENT_COST_HARD_STOP", "0.50")
    monkeypatch.setenv("CLAUDE_AGENT_DEFAULT_MODEL", "claude-opus-3")
    
    config = AgentConfig.from_env()
    assert config.bash_timeout_seconds == 180
    assert config.cost_hard_stop == 0.50
    assert config.default_model == "claude-opus-3"
```

### **Test 2.2: Config File Loading**
```python
def test_config_from_file(tmp_path):
    """AgentConfig should load from TOML configuration file."""
    config_file = tmp_path / "config.toml"
    config_file.write_text("""
    max_tool_result_history = 2000
    bash_timeout_seconds = 180
    cost_hard_stop = 0.30
    default_model = "claude-opus-3"
    """)
    
    config = AgentConfig.from_file(config_file)
    assert config.max_tool_result_history == 2000
    assert config.bash_timeout_seconds == 180
    assert config.cost_hard_stop == 0.30
    assert config.default_model == "claude-opus-3"
```

### **Test 2.3: Configuration Priority**
```python
def test_config_priority_order(tmp_path, monkeypatch):
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
    assert config.bash_timeout_seconds == 300
```

### **Implementation 2: Configuration Loading Methods**
```python
# src/claude_agent/config.py
@dataclass
class AgentConfig:
    # ... fields ...
    
    @classmethod
    def from_env(cls) -> "AgentConfig":
        """Load configuration from environment variables."""
        
    @classmethod  
    def from_file(cls, path: Path) -> "AgentConfig":
        """Load configuration from TOML file."""
        
    @classmethod
    def from_sources(cls, config_file: Path | None = None, cli_args: dict | None = None) -> "AgentConfig":
        """Load configuration from multiple sources with priority."""
```

## **Phase 3: Integration with Existing Code**

### **Test 3.1: Session Uses Config**
```python
def test_session_respects_config():
    """Session should use configuration values instead of hard-coded constants."""
    config = AgentConfig(max_conversation_turns=5)
    session = Session.from_config(config, model="opus", tools=[])
    
    # Session should store/use the config
    assert session.config.max_conversation_turns == 5
```

### **Test 3.2: Tools Use Config**  
```python
def test_bash_tool_uses_config_timeout():
    """Bash tool should respect config timeout value."""
    config = AgentConfig(bash_timeout_seconds=60)
    tool_registry = ToolRegistry(config)
    bash_tool = tool_registry.get_tool("bash")
    
    with patch("subprocess.run") as mock_run:
        bash_tool.function({"command": "echo test"})
        _, kwargs = mock_run.call_args
        assert kwargs["timeout"] == 60
```

### **Test 3.3: Streaming Uses Config**
```python
def test_streaming_respects_conversation_limit():
    """stream_response should trim conversations using config limit."""
    config = AgentConfig(max_conversation_turns=2)
    session = Session.from_config(config, model="opus", tools=[])
    
    # Add 3 turns worth of messages
    for i in range(6):
        session.conversation.append({"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"})
    
    client = FakeStreamingClient(tokens=["response"])
    out = FakeOutput()
    
    stream_response(client, session, out, config=config)
    
    # Should have trimmed to last 2 turns (4 messages)
    sent_messages = client.last_create_call["messages"]
    assert len(sent_messages) == 4
```

### **Implementation 3: Integrate Config Throughout Codebase**

**Update Session:**
```python
# src/claude_agent/cli/session.py
class Session:
    def __init__(self, model: str, system_prompt: str, tools: list, config: AgentConfig):
        self.config = config
        # ... rest of init
    
    @classmethod
    def from_config(cls, config: AgentConfig, model: str, tools: list) -> "Session":
        return cls(model, config.system_prompt, tools, config)
```

**Update Tools:**
```python  
# src/claude_agent/tools.py
def bash(tool_input: dict[str, Any], config: AgentConfig) -> str:
    # Use config.bash_timeout_seconds instead of _BASH_TIMEOUT_SECONDS
```

**Update Streaming:**
```python
# src/claude_agent/cli/streaming.py  
def stream_response(client, session, out, config: AgentConfig | None = None):
    if config is None:
        config = session.config
    # Use config.max_conversation_turns instead of _MAX_CONVERSATION_TURNS
```

## **Phase 4: CLI Integration**

### **Test 4.1: CLI Argument Parsing**
```python
def test_cli_config_arguments():
    """CLI should accept configuration arguments."""
    args = parse_args(["--config", "config.toml", "--timeout", "180", "--cost-limit", "0.50"])
    assert args.config_file == Path("config.toml")
    assert args.bash_timeout_seconds == 180
    assert args.cost_hard_stop == 0.50
```

### **Test 4.2: Main Function Integration**
```python
def test_main_uses_config_file():
    """main() should load and use configuration."""
    with patch("claude_agent.cli.main.run_loop") as mock_run_loop:
        main(["--config", "test_config.toml"])
        
        # Should have been called with a Session that has custom config
        session = mock_run_loop.call_args[0][3]  # session parameter
        assert session.config.max_conversation_turns == 5  # from test_config.toml
```

### **Implementation 4: Update CLI and Main**
```python
# src/claude_agent/cli/main.py
def parse_args(args: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, help="Configuration file")
    parser.add_argument("--timeout", type=int, dest="bash_timeout_seconds")
    parser.add_argument("--cost-limit", type=float, dest="cost_hard_stop")
    # ... other config options
    return parser.parse_args(args)

def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv or sys.argv[1:])
    config = AgentConfig.from_sources(
        config_file=args.config,
        cli_args=vars(args)
    )
    
    # Pass config to Session and other components
    session = Session.from_config(config, model=config.default_model, tools=make_tools(config))
    # ...
```

## **Phase 5: Cleanup and Validation**

### **Test 5.1: Remove Hard-coded Constants**
```python
def test_no_hardcoded_constants_remain():
    """Verify all hard-coded constants have been replaced with config usage."""
    # This test scans the codebase to ensure no old constants remain
    problematic_patterns = [
        "_MAX_TOOL_RESULT_IN_HISTORY",
        "_MAX_CONVERSATION_TURNS", 
        "_BASH_TIMEOUT_SECONDS",
        "_COST_HARD_STOP",
        "_MAX_TOOL_CALLS_PER_TURN",
    ]
    
    for pattern in problematic_patterns:
        matches = search_codebase(pattern)
        # Should only find them in config.py and maybe old test files
        assert all("config.py" in match or "test_" in match for match in matches)
```

### **Implementation 5: Remove Old Constants**
- Remove all `_CONSTANT = value` declarations from modules
- Update all references to use `config.field_name` instead
- Update tests to inject custom configs where needed

## **🚀 Execution Strategy**

**Run this TDD cycle:**
1. **Write the failing test** (`pixi run lint` on test file)
2. **Confirm it fails** for the right reason  
3. **Implement minimal code** to make it pass
4. **Run lint** on implementation (`pixi run lint`, fix any issues)
5. **Confirm test passes**
6. **Run full test suite** before moving to next test
7. **Commit** each working increment

**Total estimated tests:** ~15-20 tests across 5 phases
**Implementation complexity:** Medium - requires updating multiple modules but the architecture supports it well

This plan follows the project's TDD guidelines perfectly and will result in a clean, well-tested configuration management system! 🎯