# coding-agent

A hands-on project for building a coding agent with Claude, step by step.

## Prerequisites

- [pixi](https://pixi.sh) for environment management
- An Anthropic API key set as `ANTHROPIC_API_KEY`

## Setup

```bash
pixi install
```

## Usage

```bash
# Start a chat session
pixi run chat

# With verbose output
pixi run chat -- --verbose
```

### Cost Control

This agent includes several safeguards to prevent runaway costs:

- **Tool call limits**: Max 20 tool calls per turn to prevent infinite loops
- **Usage tracking**: Use `/usage` to see API/tool call counts
- **Enhanced Ctrl-C**: Cancellation works during tool execution
- **Warnings**: Alerts when >10 API calls in one session

See [docs/token-efficiency.md](docs/token-efficiency.md) for details.

## Development

```bash
pixi run lint       # ruff check
pixi run fmt        # ruff format
pixi run typecheck  # mypy
```

## License

Apache-2.0 — see [LICENSE](LICENSE).
