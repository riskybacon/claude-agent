# CLI Spec

A richer terminal interface for the coding agent. The agent loop itself (`agent.py`) stays
unchanged — this spec is entirely about the shell around it.

## Mental model

The agent loop inverts the usual relationship between code and inference: Claude is in control
of the flow, deciding which deterministic tools to call and when. The CLI is the shell that
presents that loop to the user — input handling, output rendering, and session management.

## Input

| Key | Behaviour |
|-----|-----------|
| `Enter` | Submit the current input to the agent |
| `Shift+Enter` | Insert a newline — allows multi-line prompts and code pastes |
| `Ctrl+C` | Cancel the current inference (return to prompt, do not exit) |
| `Ctrl+D` | Exit |
| `↑` / `↓` | Navigate input history |

**Library:** `prompt_toolkit` — handles raw key events, multi-line editing, and history.
The current `input()` loop cannot support Shift+Enter or Ctrl+C cancellation.

## Output

**Streaming** — responses print token-by-token as they arrive rather than all at once.
Requires switching `run_inference` from `client.messages.create()` to
`client.messages.stream()`.

**Tool calls** — shown as a single collapsed line by default:

```
▶ read_file({"path": "src/coding_agent/agent.py"})  [2.4 KB]
```

The line expands to show the full result when the user runs `/expand`.

**Rendering** — Claude's text responses are rendered as markdown (headings, bold, code blocks
with syntax highlighting). **Library:** `rich`.

**Status** — a spinner is shown while waiting for Claude to respond, e.g. `⠋ thinking...`.
Disappears as soon as streaming begins.

## Slash commands

| Command | Behaviour |
|---------|-----------|
| `/help` | List available slash commands |
| `/clear` | Reset the conversation (clears history, keeps tools and system prompt) |
| `/model <name>` | Switch the active model mid-session (e.g. `/model haiku`) |
| `/expand` | Print the full output of the most recent tool call |

Slash commands are parsed before the input is sent to the agent — they never reach the
inference call.

## Startup flags

| Flag | Default | Description |
|------|---------|-------------|
| `--model` | `claude-opus-4-5` | Initial model |
| `--system` | built-in prompt | Path to a file containing a custom system prompt |
| `--verbose` | off | Print full tool results inline instead of collapsing them |

## Architecture changes required

| Area | Current | New |
|------|---------|-----|
| Input loop | `input()` | `prompt_toolkit` `PromptSession` |
| Inference | `client.messages.create()` | `client.messages.stream()` |
| Ctrl+C | kills process | cancels active stream via `stream.close()` |
| Tool display | always prints full result | collapsed line; `/expand` shows full |
| Text output | `print()` | `rich.console.Console` with markdown |
| Model | hardcoded | stored in session state, mutable via `/model` |

## Libraries to add

```toml
# pixi.toml
prompt-toolkit = ">=3.0,<4"
rich = ">=14.0,<15"
```

## Out of scope

- Persistent session save/load across processes
- Mouse support
- Image or file attachments
- Any network features (auth, remote sessions)
