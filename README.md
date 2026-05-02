# 🤖 claude-agent

A terminal-based coding assistant powered by the [Anthropic API](https://docs.anthropic.com). It streams responses token-by-token, executes tools against your local filesystem, and manages a multi-turn session with prompt caching and a sliding-window context limit.

## Features

- **Streaming output** — responses appear as they're generated, not all at once
- **Filesystem tools** — read files, list directories, edit files, run shell commands, search code
- **Prompt caching** — system prompt and tool definitions are cached server-side, so turns 2–N cost ~10% of normal input token prices for those tokens
- **Sliding window** — only the last 20 conversation turns are sent to the API; full history stays in your terminal
- **Token tracking** — session token counts visible via `/usage`; warns at 100k input tokens

## Prerequisites

- [pixi](https://pixi.sh) for environment and dependency management
- An Anthropic API key exported as `ANTHROPIC_API_KEY`

## Quick Start

```bash
pixi install
pixi run chat
```

With verbose tool output:

```bash
pixi run chat -- --verbose
```

With a custom system prompt:

```bash
pixi run chat -- --system path/to/prompt.txt
```

## Slash Commands

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/clear` | Reset conversation history and token counters |
| `/model <name>` | Switch model mid-session (e.g. `claude-opus-4-7`) |
| `/expand` | Print the full output of the most recent tool call |
| `/usage` | Show input, output, and cache token counts for this session |

## 💰 Cost Controls

| Safeguard | Detail |
|-----------|--------|
| Tool call limit | Max 20 tool calls per turn — prevents infinite loops |
| Token warning | Alerts when session input tokens exceed 100k |
| Ctrl-C | Cancels the active stream and returns to the prompt |
| `/clear` | Resets conversation history to start fresh |

See [docs/token-efficiency.md](docs/token-efficiency.md) for a detailed breakdown of how token costs compound across turns and how each method addresses them.

## 🛠️ Development

**Run checks** (run these before committing — they cover the full `src/` tree, not just changed files):

```bash
pixi run lint       # ruff check src/
pixi run fmt        # ruff format src/
pixi run typecheck  # mypy
```

**Run tests:**

```bash
pytest                               # all tests
pytest tests/test_streaming.py      # one file
```

The pre-commit hook runs `ruff check` automatically and blocks commits that fail lint.

### Architecture

The CLI is built around Protocol-based dependency injection so every layer is unit-testable without a real terminal or API connection.

| Module | Responsibility |
|--------|----------------|
| `cli/session.py` | Mutable session state — model, history, token counts |
| `cli/streaming.py` | `stream_response()`, `AnthropicStream`, sliding-window trimming |
| `cli/loop.py` | `run_loop()` — outer input loop; `_run_turn()` — inner tool loop |
| `cli/commands.py` | Slash-command parsing |
| `cli/input.py` | `PromptToolkitInput` — terminal input with key bindings |
| `cli/output.py` | `RichOutput` — rich-formatted terminal output |
| `cli/main.py` | Wires real implementations, registers SIGINT handler, starts loop |
| `tools.py` | All tool definitions (read, list, bash, edit, search) |

Fake implementations for testing live in `tests/fakes.py`.

## License

Apache-2.0 — see [LICENSE](LICENSE).
