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

## Development

```bash
pixi run lint       # ruff check
pixi run fmt        # ruff format
pixi run typecheck  # mypy
```

## License

Apache-2.0 — see [LICENSE](LICENSE).
