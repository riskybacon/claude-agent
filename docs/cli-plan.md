# CLI Implementation Plan

Test-driven plan for building the CLI described in `cli-spec.md`. Each phase has a clear
deliverable, automated acceptance criteria where possible, and manual criteria where the
terminal is unavoidable.

## Guiding principle

`agent.py` and `tools.py` do not change. The CLI is a new `src/coding_agent/cli/` package
that wraps the existing `Agent` class with a richer shell.

## File structure

```
src/coding_agent/cli/
    __init__.py
    commands.py     # slash command parsing and dispatch
    session.py      # mutable session state (model, history, last tool result)
    output.py       # rich rendering and collapsed tool display
    input.py        # prompt_toolkit setup (Shift+Enter, history, keybindings)
    main.py         # wires everything together; entry point

tests/
    __init__.py
    test_commands.py
    test_session.py
    test_output.py
    test_streaming.py
```

## Dependencies to add

```toml
# pixi.toml [dependencies]
rich = ">=14.0,<15"
prompt-toolkit = ">=3.0,<4"

# pixi.toml [dependencies] (dev/test)
pytest = ">=8.0,<9"
pytest-mock = ">=3.14,<4"
```

---

## Phase 1 — Slash commands and session state

**Why first:** pure logic with no terminal or network dependencies. Fully unit-testable.
Everything else depends on session state being correct.

### Deliverables
- `cli/commands.py` — parse and dispatch slash commands
- `cli/session.py` — mutable session state
- `tests/test_commands.py`
- `tests/test_session.py`

### `commands.py` design

```python
@dataclass
class ParsedCommand:
    name: str        # "model", "clear", "help", "expand"
    args: list[str]  # e.g. ["haiku"] for /model haiku

def parse_command(text: str) -> ParsedCommand | None:
    """Return a ParsedCommand if text starts with /, else None."""
```

### `session.py` design

```python
@dataclass
class Session:
    model: str
    system_prompt: str
    conversation: list[MessageParam]
    last_tool_result: str | None
    verbose: bool
```

### Acceptance criteria — automated

```python
# test_commands.py
def test_parse_clear():
    assert parse_command("/clear").name == "clear"

def test_parse_model_with_arg():
    cmd = parse_command("/model haiku")
    assert cmd.name == "model"
    assert cmd.args == ["haiku"]

def test_parse_returns_none_for_plain_text():
    assert parse_command("hello world") is None

def test_parse_returns_none_for_empty():
    assert parse_command("") is None

def test_unknown_slash_command_returns_command():
    # unknown commands are parsed, not silently dropped
    assert parse_command("/unknown").name == "unknown"
```

```python
# test_session.py
def test_clear_resets_conversation():
    session = Session(model="claude-opus-4-5", ...)
    session.conversation.append({"role": "user", "content": "hi"})
    session.clear()
    assert session.conversation == []

def test_clear_preserves_model_and_system_prompt():
    session = Session(model="haiku", system_prompt="custom", ...)
    session.clear()
    assert session.model == "haiku"
    assert session.system_prompt == "custom"

def test_switch_model():
    session = Session(model="claude-opus-4-5", ...)
    session.switch_model("claude-haiku-4-5-20251001")
    assert session.model == "claude-haiku-4-5-20251001"

def test_set_last_tool_result():
    session = Session(...)
    session.last_tool_result = "file contents here"
    assert session.last_tool_result == "file contents here"
```

---

## Phase 2 — Output rendering

**Why second:** no network or terminal input dependencies. Output functions are pure
transformations from data to strings, testable by capturing stdout.

### Deliverables
- `cli/output.py`
- `tests/test_output.py`

### `output.py` design

```python
def format_tool_line(name: str, args: dict, result: str) -> str:
    """Return the single collapsed line shown for a tool call."""
    # e.g. "▶ read_file({"path": "foo.py"})  [128 bytes]"

def render_markdown(text: str) -> None:
    """Print text as rendered markdown via rich."""

def render_tool_line(name: str, args: dict, result: str) -> None:
    """Print the collapsed tool line."""

def render_expand(result: str) -> None:
    """Print the full tool result."""

def render_error(message: str) -> None:
    """Print an error message in red."""
```

### Acceptance criteria — automated

```python
# test_output.py
def test_format_tool_line_includes_tool_name():
    line = format_tool_line("read_file", {"path": "foo.py"}, "contents")
    assert "read_file" in line

def test_format_tool_line_includes_byte_count():
    result = "hello"
    line = format_tool_line("read_file", {}, result)
    assert "5 bytes" in line or "5B" in line

def test_format_tool_line_starts_with_arrow():
    line = format_tool_line("bash", {"command": "ls"}, "file.py")
    assert line.startswith("▶")

def test_format_tool_line_long_result_does_not_expand():
    result = "x" * 10_000
    line = format_tool_line("read_file", {}, result)
    assert len(line) < 200  # still a single line
```

### Acceptance criteria — manual

- Run `pixi run agent`, ask Claude to read a file. Tool call appears as one line:
  `▶ read_file({"path": "..."})  [N bytes]`
- Full result is NOT printed inline (unless `--verbose`)
- Claude's text response renders with markdown (bold, code blocks highlighted)

---

## Phase 3 — Streaming

**Why third:** depends on session state (Phase 1) and output rendering (Phase 2). This is the
only phase that touches `Agent.run_inference`.

### Deliverables
- Updated `Agent.run_inference` → `Agent.stream_inference` using `client.messages.stream()`
- Updated `Agent._run_tool_loop` to handle streamed responses
- `tests/test_streaming.py`

### Design note

`client.messages.stream()` is a context manager. The streaming loop looks like:

```python
with self.client.messages.stream(...) as stream:
    for text in stream.text_stream:
        render_token(text)
    message = stream.get_final_message()
```

The `stream` object also supports `stream.close()` for cancellation (Phase 5).

### Acceptance criteria — automated (with mocking)

```python
# test_streaming.py
def test_tokens_are_printed_as_they_arrive(mocker):
    # mock client.messages.stream() to yield fake tokens
    # assert each token is printed before the next arrives

def test_final_message_is_appended_to_conversation(mocker):
    # mock stream, assert conversation grows by one after streaming

def test_tool_use_blocks_are_collected_from_final_message(mocker):
    # mock a stream that ends with a tool_use block
    # assert _execute_tool is called with the right name and input
```

### Acceptance criteria — manual

- Run `pixi run agent`, ask a question. Text appears word-by-word, not all at once.
- A spinner (`⠋ thinking...`) is visible before the first token arrives.
- Spinner disappears as soon as streaming begins.

---

## Phase 4 — prompt_toolkit input

**Why fourth:** depends on session state (for `/clear`, `/model`) and output (for rendering
command results). No automated tests — this is terminal I/O.

### Deliverables
- `cli/input.py` — `PromptSession` with keybindings
- Manual acceptance criteria only

### Design note

```python
from prompt_toolkit import PromptSession
from prompt_toolkit.keys import Keys

session = PromptSession()
# bind Shift+Enter to insert newline instead of submitting
```

### Acceptance criteria — manual

| Scenario | Expected |
|----------|----------|
| Type a message, press `Enter` | Message submitted |
| Type a message, press `Shift+Enter` | Newline inserted, cursor moves down |
| Paste multi-line text | All lines appear in input buffer |
| Submit, then press `↑` | Previous input restored |
| Press `↑` twice | Input before that restored |
| Press `Ctrl+D` on empty input | Process exits cleanly |
| Press `Ctrl+D` mid-input | Process exits cleanly |

---

## Phase 5 — Ctrl+C cancellation

**Why fifth:** requires the streaming infrastructure from Phase 3 and the input loop from
Phase 4.

### Deliverables
- SIGINT handler in `cli/main.py` that calls `stream.close()` on the active stream
- Manual acceptance criteria only

### Design note

The active stream needs to be accessible from the signal handler. Store it on the session
or in a module-level variable set before streaming begins and cleared after.

### Acceptance criteria — manual

| Scenario | Expected |
|----------|----------|
| Press `Ctrl+C` while Claude is thinking (before first token) | Spinner stops, prompt returns |
| Press `Ctrl+C` mid-stream | Partial output stops, prompt returns |
| Press `Ctrl+C` with no active inference | Nothing happens (or prints a message) |
| After cancellation, submit a new message | Agent responds normally |
| Cancelled tool call | Tool is not executed after cancellation |

---

## Phase 6 — Integration and wiring

**Why last:** wires all phases together into a working CLI.

### Deliverables
- `cli/main.py` — entry point, connects input → session → agent → output
- Updated `pyproject.toml` `[project.scripts]` entry: `coding-agent-cli`
- Updated `pixi.toml` task: `cli = "python -m coding_agent.cli.main"`

### Acceptance criteria — manual (full end-to-end)

| Scenario | Expected |
|----------|----------|
| `pixi run cli` | Starts, shows welcome message |
| `pixi run cli --model claude-haiku-4-5-20251001` | Starts with Haiku |
| `pixi run cli --system path/to/prompt.txt` | Uses custom system prompt |
| `pixi run cli --verbose` | Tool results print in full inline |
| Type `/help` | Lists all slash commands |
| Type `/model claude-haiku-4-5-20251001` | Subsequent responses use Haiku |
| Type `/clear` | Conversation resets, confirmed in output |
| Ask Claude to read a file, then type `/expand` | Full file contents printed |
| Ask a question that produces markdown | Headings and code blocks render correctly |

---

## Implementation order summary

```
Phase 1  commands.py + session.py      ← pure logic, unit tests
Phase 2  output.py                     ← rendering, unit tests
Phase 3  streaming                     ← mocked integration tests
Phase 4  input.py (prompt_toolkit)     ← manual only
Phase 5  Ctrl+C cancellation           ← manual only
Phase 6  cli/main.py wiring            ← manual end-to-end
```

Each phase is independently mergeable. Phases 1–3 produce real test coverage.
Phases 4–6 are verified manually using the acceptance criteria tables above.
