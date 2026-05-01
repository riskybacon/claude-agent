# CLI Implementation Plan

Test-driven plan for building the CLI described in `cli-spec.md`. The design uses dependency
injection at terminal boundaries so that all phases — including input, cancellation, and
end-to-end wiring — have automated acceptance criteria.

## Core design principle

Define a `Protocol` for every terminal-dependent piece. Implement it twice: once for real
(production), once as a fake (tests). The main loop accepts protocols, not concrete
implementations. Manual testing is then only "does the real terminal feel right", not "does
the logic work".

## Protocols

```python
# cli/protocols.py

class InputReader(Protocol):
    def read(self) -> str | None: ...
    # Returns the next line of user input. None signals EOF/exit.

class OutputWriter(Protocol):
    def print_token(self, text: str) -> None: ...
    def print_tool_line(self, name: str, args: dict[str, Any], result: str) -> None: ...
    def print_markdown(self, text: str) -> None: ...
    def print_error(self, message: str) -> None: ...
    def print_expand(self, result: str) -> None: ...
    def show_spinner(self) -> None: ...
    def hide_spinner(self) -> None: ...

class StreamHandle(Protocol):
    def cancel(self) -> None: ...
    # Cancels the active inference stream.

class StreamingClient(Protocol):
    def stream(
        self,
        model: str,
        system: str,
        tools: list[dict[str, Any]],
        messages: list[MessageParam],
    ) -> AbstractContextManager[StreamHandle]: ...
    # Context manager that yields a StreamHandle and streams tokens via OutputWriter.
```

## Fakes (shared across all test phases)

```python
# tests/fakes.py

class FakeInput:
    def __init__(self, lines: list[str | None]) -> None: ...
    def read(self) -> str | None: ...  # pops from lines

class FakeOutput:
    tokens: list[str]
    tool_lines: list[tuple[str, dict, str]]
    markdown_calls: list[str]
    errors: list[str]
    spinner_shown: bool
    # implements OutputWriter, captures everything for assertions

class FakeStreamHandle:
    cancelled: bool = False
    def cancel(self) -> None: ...  # sets cancelled = True

class FakeStreamingClient:
    def __init__(self, tokens: list[str], tool_uses: list[...] | None = None) -> None: ...
    # yields tokens one at a time, then optionally a tool_use block
    # returns a FakeStreamHandle
```

## File structure

```
src/coding_agent/cli/
    __init__.py
    protocols.py    # Protocol definitions
    commands.py     # slash command parsing
    session.py      # mutable session state
    output.py       # RichOutput — real OutputWriter (uses rich)
    input.py        # PromptToolkitInput — real InputReader (uses prompt_toolkit)
    streaming.py    # AnthropicStream — real StreamingClient (uses anthropic SDK)
    main.py         # wires real implementations; entry point

tests/
    __init__.py
    fakes.py
    test_commands.py
    test_session.py
    test_output.py
    test_streaming.py
    test_input_loop.py
    test_cancellation.py
```

## Dependencies to add

```toml
# pixi.toml [dependencies]
rich = ">=14.0,<15"
prompt-toolkit = ">=3.0,<4"
pytest = ">=8.0,<9"
pytest-mock = ">=3.14,<4"
```

---

## Phase 1 — Protocols, slash commands, session state

**Why first:** defines the contracts everything else is built against. Pure logic, no
terminal or network dependencies.

### Deliverables
- `cli/protocols.py`
- `cli/commands.py`
- `cli/session.py`
- `tests/fakes.py` (stub — add to it in later phases)
- `tests/test_commands.py`
- `tests/test_session.py`

### Acceptance criteria — automated

```python
# test_commands.py
def test_parse_clear():
    assert parse_command("/clear").name == "clear"

def test_parse_model_with_arg():
    cmd = parse_command("/model haiku")
    assert cmd.name == "model" and cmd.args == ["haiku"]

def test_plain_text_returns_none():
    assert parse_command("hello world") is None

def test_empty_string_returns_none():
    assert parse_command("") is None

def test_unknown_slash_command_is_parsed_not_dropped():
    assert parse_command("/unknown").name == "unknown"
```

```python
# test_session.py
def test_clear_resets_conversation():
    s = Session(model="opus", ...)
    s.conversation.append({"role": "user", "content": "hi"})
    s.clear()
    assert s.conversation == []

def test_clear_preserves_model_and_system_prompt():
    s = Session(model="haiku", system_prompt="custom", ...)
    s.clear()
    assert s.model == "haiku" and s.system_prompt == "custom"

def test_switch_model():
    s = Session(model="opus", ...)
    s.switch_model("haiku")
    assert s.model == "haiku"

def test_last_tool_result_stored():
    s = Session(...)
    s.last_tool_result = "file contents"
    assert s.last_tool_result == "file contents"

def test_last_tool_result_none_on_init():
    assert Session(...).last_tool_result is None
```

---

## Phase 2 — Output rendering

**Why second:** no network or input dependencies. Tests use `FakeOutput` to capture calls
and assert on them without touching the terminal.

### Deliverables
- `cli/output.py` (`RichOutput` implementing `OutputWriter`)
- `tests/fakes.py` — add `FakeOutput`
- `tests/test_output.py`

### Acceptance criteria — automated

```python
# test_output.py
def test_format_tool_line_contains_name():
    out = FakeOutput()
    out.print_tool_line("read_file", {"path": "foo.py"}, "contents")
    assert "read_file" in out.tool_lines[0]

def test_format_tool_line_contains_byte_count():
    out = FakeOutput()
    out.print_tool_line("read_file", {}, "hello")
    assert "5" in out.tool_lines[0]  # 5 bytes

def test_format_tool_line_starts_with_arrow():
    out = FakeOutput()
    out.print_tool_line("bash", {"command": "ls"}, "file.py")
    assert out.tool_lines[0].startswith("▶")

def test_tool_line_does_not_include_full_result():
    out = FakeOutput()
    out.print_tool_line("read_file", {}, "x" * 10_000)
    assert len(out.tool_lines[0]) < 200

def test_expand_prints_full_result():
    out = FakeOutput()
    out.print_expand("full result here")
    assert "full result here" in out.expand_calls[0]

def test_error_is_captured():
    out = FakeOutput()
    out.print_error("something went wrong")
    assert out.errors == ["something went wrong"]
```

### Acceptance criteria — manual

- Tool call appears as one collapsed line: `▶ read_file({"path": "..."})  [N bytes]`
- Claude's text renders with markdown (headings, bold, syntax-highlighted code blocks)
- `--verbose` flag prints full tool results inline

---

## Phase 3 — Streaming

**Why third:** depends on session state (Phase 1) and output rendering (Phase 2).
`FakeStreamingClient` replaces the real Anthropic client in all tests.

### Deliverables
- `cli/streaming.py` (`AnthropicStream` implementing `StreamingClient`)
- `tests/fakes.py` — add `FakeStreamingClient` and `FakeStreamHandle`
- `tests/test_streaming.py`

### Acceptance criteria — automated

```python
# test_streaming.py
def test_tokens_printed_as_they_arrive():
    out = FakeOutput()
    client = FakeStreamingClient(tokens=["hello", " world"])
    stream_response(client, session, out)
    assert out.tokens == ["hello", " world"]

def test_spinner_shown_before_first_token():
    out = FakeOutput()
    client = FakeStreamingClient(tokens=["hi"])
    stream_response(client, session, out)
    assert out.spinner_shown_before_first_token  # FakeOutput tracks ordering

def test_spinner_hidden_after_streaming_ends():
    out = FakeOutput()
    client = FakeStreamingClient(tokens=["hi"])
    stream_response(client, session, out)
    assert not out.spinner_visible

def test_final_message_appended_to_conversation():
    client = FakeStreamingClient(tokens=["hi"])
    stream_response(client, session, FakeOutput())
    assert len(session.conversation) == 2  # user + assistant

def test_tool_use_triggers_tool_execution():
    client = FakeStreamingClient(tokens=[], tool_uses=[{"name": "read_file", ...}])
    executed = []
    stream_response(client, session, FakeOutput(), on_tool=executed.append)
    assert executed[0]["name"] == "read_file"
```

### Acceptance criteria — manual

- Text appears token-by-token, not all at once
- Spinner visible before first token, gone once streaming starts

---

## Phase 4 — Input loop

**Why fourth:** depends on session state and output (for rendering command results).
`FakeInput` replaces `PromptToolkitInput` in all tests — the input loop is now fully
testable.

### Deliverables
- `cli/input.py` (`PromptToolkitInput` implementing `InputReader`)
- `tests/fakes.py` — add `FakeInput`
- `tests/test_input_loop.py`

### Acceptance criteria — automated

```python
# test_input_loop.py
def test_plain_message_sent_to_agent():
    inp = FakeInput(["what files are here?", None])
    client = FakeStreamingClient(tokens=["here are your files"])
    calls = run_loop(inp, FakeOutput(), client, session)
    assert calls[0] == "what files are here?"

def test_slash_clear_resets_conversation():
    session.conversation = [{"role": "user", "content": "hi"}]
    inp = FakeInput(["/clear", None])
    run_loop(inp, FakeOutput(), FakeStreamingClient(tokens=[]), session)
    assert session.conversation == []

def test_slash_model_switches_model():
    inp = FakeInput(["/model haiku", None])
    run_loop(inp, FakeOutput(), FakeStreamingClient(tokens=[]), session)
    assert session.model == "haiku"

def test_slash_expand_prints_last_tool_result():
    session.last_tool_result = "file contents"
    out = FakeOutput()
    inp = FakeInput(["/expand", None])
    run_loop(inp, out, FakeStreamingClient(tokens=[]), session)
    assert "file contents" in out.expand_calls[0]

def test_empty_input_is_skipped():
    inp = FakeInput(["", "hello", None])
    client = FakeStreamingClient(tokens=["hi"])
    calls = run_loop(inp, FakeOutput(), client, session)
    assert calls == ["hello"]  # empty string not forwarded

def test_none_input_exits_loop():
    inp = FakeInput([None])
    run_loop(inp, FakeOutput(), FakeStreamingClient(tokens=[]), session)
    # no assertion needed — just must not hang
```

### Acceptance criteria — manual

| Scenario | Expected |
|----------|----------|
| `Enter` on a message | Submitted |
| `Shift+Enter` | Newline inserted |
| `↑` / `↓` | History navigation |
| `Ctrl+D` on empty input | Clean exit |

---

## Phase 5 — Ctrl+C cancellation

**Why fifth:** depends on streaming (Phase 3) and the input loop (Phase 4).
`FakeStreamHandle` lets tests verify cancellation without sending a real SIGINT.

### Deliverables
- Signal handler in `cli/main.py` calling `active_stream.cancel()`
- `tests/test_cancellation.py`

### Acceptance criteria — automated

```python
# test_cancellation.py
def test_cancel_is_called_on_interrupt():
    handle = FakeStreamHandle()
    simulate_interrupt(handle)  # calls the signal handler directly
    assert handle.cancelled

def test_loop_continues_after_cancellation():
    handle = FakeStreamHandle()
    inp = FakeInput(["long question", "short question", None])
    client = FakeStreamingClient(tokens=["answer"], handle=handle)
    out = FakeOutput()
    # simulate interrupt mid-first-stream, then second message completes
    calls = run_loop_with_interrupt(inp, out, client, session, interrupt_after=0)
    assert "short question" in calls

def test_tool_not_executed_after_cancellation():
    handle = FakeStreamHandle()
    client = FakeStreamingClient(tokens=[], tool_uses=[{"name": "bash", ...}], handle=handle)
    handle.cancelled = True  # pre-cancelled
    executed = []
    stream_response(client, session, FakeOutput(), on_tool=executed.append)
    assert executed == []
```

### Acceptance criteria — manual

| Scenario | Expected |
|----------|----------|
| `Ctrl+C` while thinking | Spinner stops, prompt returns |
| `Ctrl+C` mid-stream | Partial output stops, prompt returns |
| `Ctrl+C` with no active inference | Nothing happens |
| New message after cancel | Agent responds normally |

---

## Phase 6 — Wiring

**Why last:** all logic is already tested. This phase is a thin constructor that passes
real implementations where fakes were used in tests.

### Deliverables
- `cli/main.py` — constructs `PromptToolkitInput`, `RichOutput`, `AnthropicStream`, calls `run_loop`
- `pyproject.toml` script: `coding-agent-cli = "coding_agent.cli.main:main"`
- `pixi.toml` task: `cli = "python -m coding_agent.cli.main"`

### Acceptance criteria — manual (end-to-end)

| Scenario | Expected |
|----------|----------|
| `pixi run cli` | Starts, shows welcome |
| `pixi run cli --model claude-haiku-4-5-20251001` | Uses Haiku |
| `pixi run cli --system prompt.txt` | Uses custom system prompt |
| `pixi run cli --verbose` | Full tool results inline |
| `/help` | Lists slash commands |
| `/model claude-haiku-4-5-20251001` | Switches mid-session |
| `/clear` | Resets conversation |
| `/expand` after a tool call | Full result printed |
| Markdown response | Renders correctly |

---

## Implementation order summary

```
Phase 1  protocols + commands + session    ← pure logic, unit tests
Phase 2  output.py (RichOutput)            ← rendering, unit tests via FakeOutput
Phase 3  streaming.py (AnthropicStream)    ← unit tests via FakeStreamingClient
Phase 4  input.py (PromptToolkitInput)     ← unit tests via FakeInput
Phase 5  Ctrl+C cancellation               ← unit tests via FakeStreamHandle
Phase 6  main.py wiring                    ← manual end-to-end only
```

Phases 1–5 are fully automated. Phase 6 is the only phase with manual-only criteria,
and it contains no logic — just construction.
