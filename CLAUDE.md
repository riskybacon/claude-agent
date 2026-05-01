# coding-agent — Agent Guidelines

## Project Overview

A step-by-step Python port of the [how-to-build-a-coding-agent](https://github.com/anthropics/anthropic-cookbook) workshop. Each module in `src/coding_agent/` is a self-contained, runnable step that adds one capability on top of the previous one.

| Step | Module | Tool(s) added |
|------|--------|---------------|
| 1 | `chat.py` | — (basic chat loop) |
| 2 | `read.py` | `read_file` |
| 3 | `list_files.py` | `list_files` |
| 4 | `bash.py` | `bash` |
| 5 | `edit.py` | `edit_file` |
| 6 | `code_search.py` | `code_search` |

Each step is a complete agent — it does not import from previous steps.

## Development

**Setup**: install [pixi](https://pixi.sh), then:

```
pixi install
pixi run install-hooks   # installs the pre-commit lint hook
```

**Run a step**:

```
pixi run chat       # step 1
pixi run read       # step 2
# etc.
```

**Code quality** (run globally before committing — not just on changed files):

```
pixi run lint       # ruff check src/
pixi run fmt        # ruff format src/
pixi run typecheck  # mypy
```

The pre-commit hook runs `ruff check` automatically and blocks commits that fail.

**Testing**: `pytest` (no tests yet — add them in `tests/` mirroring `src/` paths).

## Code Style

- Python 3.14, PEP 8, 4-space indent, `snake_case` / `CamelCase`
- Do NOT use `from __future__ import annotations` — that PEP 563 pattern is legacy and was never made the default. Python 3.14 has PEP 649 deferred annotation evaluation built in, so `TYPE_CHECKING`-guarded imports already work without it.
- Type hints everywhere; mypy is strict
- Line length: 100 chars (`pyproject.toml`)
- Ruff with `select = ["ALL"]` — check `pyproject.toml` for the intentional ignore list before adding a `# noqa`

## Architecture: Tool Loop

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

## Commits

Conventional Commits format:

```
feat: add list_files tool (step 3)
fix: handle OSError in read_file
docs: update CLAUDE.md
```
