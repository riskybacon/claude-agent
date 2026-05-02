# claude-agent — Agent Guidelines

## Project Overview

A CLI coding assistant powered by the Anthropic API. The agent streams responses
token-by-token, executes tools (read, list, bash, edit, search), and manages a
multi-turn conversation session with prompt caching and a sliding-window context limit.

The CLI lives in `src/claude_agent/cli/`. Tool implementations live in
`src/claude_agent/tools.py`.

## Development

**Setup**: install [pixi](https://pixi.sh), then:

```
pixi install
pixi run install-hooks   # installs the pre-commit lint hook
```

**Run the agent**:

```
pixi run cli
```

**Code quality** (run globally before committing — not just on changed files):

```
pixi run lint       # ruff check src/
pixi run fmt        # ruff format src/
pixi run typecheck  # mypy
```

The pre-commit hook runs `ruff check` automatically and blocks commits that fail.

**Testing**: `pytest` — tests live in `tests/`, mirroring `src/` paths.

```
pytest              # run all tests
pytest tests/test_streaming.py   # run one file
```

## TDD Workflow

Prefer test-first for all non-trivial changes:

1. Write a failing test that exposes the missing behaviour
2. Confirm it fails for the right reason
3. Implement the fix
4. Confirm it passes
5. Run the full suite before committing

For bug fixes: stash any in-progress changes, write the failing test, pop the stash, fix, confirm green.

## Code Style

- Python 3.14, PEP 8, 4-space indent, `snake_case` / `CamelCase`
- Do NOT use `from __future__ import annotations` — that PEP 563 pattern is legacy and was never made the default. Python 3.14 has PEP 649 deferred annotation evaluation built in, so `TYPE_CHECKING`-guarded imports already work without it.
- Type hints everywhere; mypy is strict
- Line length: 100 chars (`pyproject.toml`)
- Ruff with `select = ["ALL"]` — check `pyproject.toml` for the intentional ignore list before adding a `# noqa`. Fix the code; suppress only when the rule is genuinely inapplicable (e.g. `ARG002` on Protocol method stubs, `ANN401` on intentional `Any` callback params).

## Architecture: Step Modules (Tool Loop)

The core pattern introduced in step 2 and reused in every subsequent step:

```
user input
  └─▶ run_inference(conversation)
        └─▶ Claude responds
              ├─ text blocks   → print to stdout
              └─ tool_use blocks → execute tool → collect results
                    └─▶ run_inference(conversation + tool results)
                          └─▶ repeat until no tool_use blocks
```

`Agent._run_tool_loop()` owns this inner loop. `Agent.run()` owns the outer user-input loop. New tools are registered by appending a `Tool` instance to the list passed to `Agent`.

## Architecture: CLI (`src/claude_agent/cli/`)

The CLI is built around Protocol-based dependency injection so every layer is unit-testable without a real terminal or network.

| Module | Responsibility |
|--------|---------------|
| `protocols.py` | `InputReader`, `OutputWriter`, `StreamHandle`, `StreamingClient` interfaces |
| `session.py` | Conversation state — model, system prompt, tools, history |
| `commands.py` | Slash-command parsing (`/clear`, `/model`, `/expand`, `/help`) |
| `streaming.py` | `stream_response()`, `AnthropicStream`, sliding-window trimming |
| `loop.py` | `run_loop()` — outer input loop; `_run_turn()` — inner tool loop |
| `input.py` | `PromptToolkitInput` — terminal input with key bindings |
| `output.py` | `RichOutput` — rich-formatted terminal output |
| `main.py` | Wires real implementations, registers SIGINT handler, starts loop |

Fake implementations for testing live in `tests/fakes.py` (`FakeInput`, `FakeOutput`, `FakeStreamHandle`, `FakeStreamingClient`).

### Key design decisions

**Conversation trimming** (`streaming.py`): `_trim_to_turns()` keeps only the last `_MAX_CONVERSATION_TURNS` turns in the slice sent to the API. A "turn" starts at every `role: user` message with plain string content — `tool_result` messages (list content) are never turn boundaries, so `tool_use`/`tool_result` pairs are never split.

**Tool result truncation** (`loop.py`): Results over `_MAX_TOOL_RESULT_IN_HISTORY` characters are truncated before being stored in conversation history. `session.last_tool_result` always holds the full result for `/expand`.

**Prompt caching** (`streaming.py`): The system prompt and tool definitions are marked with `cache_control: {"type": "ephemeral"}` on every request so turns 2–N pay cache read prices for those tokens.

**Cancellation** (`streaming.py`, `main.py`): `stream_response` accepts an `on_handle` callback that is called with the live stream handle as soon as streaming begins. `main.py` stores it in a mutable cell; the SIGINT handler calls `.cancel()` on whatever is in that cell, stopping the stream and returning control to the prompt.

## Commits

Conventional Commits format:

```
feat: add list_files tool (step 3)
fix: handle OSError in read_file
docs: update CLAUDE.md
```
