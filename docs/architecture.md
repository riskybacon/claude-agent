# Architecture

Key design decisions behind the CLI. For token-efficiency decisions (tool result
truncation, prompt caching, sliding window) see `token-efficiency.md`.

---

## Protocol-based dependency injection

**Decision:** Every terminal-dependent boundary (`InputReader`, `OutputWriter`,
`StreamingClient`, `StreamHandle`) is defined as a `Protocol`. The main loop accepts
protocols, not concrete implementations. Real implementations (`PromptToolkitInput`,
`RichOutput`, `AnthropicStream`) live in their own modules; fake implementations
(`FakeInput`, `FakeOutput`, `FakeStreamingClient`, `FakeStreamHandle`) live in
`tests/fakes.py`.

**Context:** Terminal I/O and network calls are the two hardest things to test. The
usual workaround — mocking — couples tests to implementation details and breaks when
internals change. We needed every layer of the CLI (input loop, streaming, tool
execution, cancellation) to have fast, deterministic, network-free tests.

**Consequences:**
- All logic is testable without a real terminal or Anthropic API key
- Adding a new output sink (e.g. a web UI) means implementing `OutputWriter`, not
  changing `run_loop`
- The fake implementations must be kept in sync with the protocols — a protocol
  change that isn't reflected in the fakes will surface as a type error, not a
  silent test gap
- `main.py` is the only file that touches real implementations; everything else is
  purely in terms of protocols

---

## Ctrl+C cancellation via `on_handle` callback

**Decision:** `stream_response` accepts an `on_handle` callback that is called with
the live stream handle immediately after the streaming context manager opens, before
token iteration begins. `main.py` stores the handle in a mutable cell
(`active_handle: list[Any] = [None]`) and the SIGINT handler calls `.cancel()` on
whatever is in that cell.

**Context:** The Anthropic SDK stream has a `.cancel()` / `cancelled` flag that stops
token delivery and skips tool execution. The challenge is getting a reference to the
live handle out to the signal handler, which is registered at startup before any
stream exists. Three approaches were considered:

- **Global variable** — works but is invisible to callers and untestable
- **Subclass / wrapper** — `AnthropicStream` could expose the active handle as an
  attribute, but that couples `main.py` to the concrete type, not the protocol
- **Callback (chosen)** — `on_handle` is threaded from `main.py` through `run_loop`
  and `_run_turn` to `stream_response`. The mutable cell pattern (`list[Any] = [None]`)
  is a standard Python idiom for a closure-writable variable

**Consequences:**
- The cancellation path is fully testable: pass `on_handle=lambda h: h.cancel()` and
  assert tool calls are suppressed
- `run_loop` gains a parameter (`on_handle`) that most callers don't need — it
  defaults to `None` so existing call sites are unaffected
- The SIGINT handler only cancels the *current* stream; if no stream is active,
  `active_handle[0]` is `None` and the handler is a no-op. Ctrl+C outside a stream
  falls through to Python's default `KeyboardInterrupt`, which exits the process —
  this is the correct behaviour since there is nothing to cancel

---

## CLAUDE.md loading

**Decision:** At startup, `_load_claude_md(Path.cwd())` walks up the directory tree
from the current working directory and returns the content of the first `CLAUDE.md`
it finds. The content is appended to the base system prompt (not prepended, not used
as a replacement). The agent prints the resolved file path before the first prompt so
the user knows project instructions were loaded.

**Context:** Coding agents need project-specific context — conventions, architecture
notes, things not to do — that varies per repo. Hard-coding it in the system prompt
doesn't scale. Loading it from a file the user controls gives them a first-class way
to shape the agent's behaviour for their specific codebase.

**Walk-up** mirrors the behaviour of Claude Code and most config-file tools (`.git`,
`.editorconfig`, etc.). It means you can launch the agent from any subdirectory of a
repo and still pick up the root-level `CLAUDE.md`, which is where it naturally lives.
The nearest file wins, so a nested `CLAUDE.md` can override the parent.

**Append rather than prepend** keeps the base instructions (how the agent behaves) as
the stable prefix and adds project context after it. This also means the stable prefix
is always in the same position for prompt caching purposes.

**Consequences:**
- Users can customise the agent's knowledge of their project without touching source
  code
- If no `CLAUDE.md` is found the agent starts normally with no visible change
- The loading function (`_load_claude_md`) is a pure `Path → tuple | None` function,
  independently testable with `tmp_path`
- The `--system` flag (custom system prompt from a file) replaces the base prompt
  entirely; `CLAUDE.md` is then appended to *that*, so the two mechanisms compose
