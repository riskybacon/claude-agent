# Cost Control

Agentic coding tools create a distinct cost risk: the agent operates in a loop,
calling tools to read, edit, verify, and repeat. When the agent's reasoning is
correct, loops are short and purposeful. When it is wrong — or when the task is
underspecified — loops can run for minutes and hundreds of tool calls before the
user notices. This document covers why naive approaches fall short and how the
current system is designed.

---

## Why API-call counting is the wrong metric

The previous guard was a threshold on cumulative input tokens (100,000) that
printed a warning and left the loop running. It had two problems:

1. **It is a proxy, not a cost.** A one-token call and a 100k-token call are both
   one API call. Counting calls conflates cheap and expensive turns.

2. **Warnings are opt-in for the agent.** Claude may continue regardless.
   A warning that appears in the terminal but is not surfaced as a tool error
   does not interrupt tool execution — it only interrupts the *next* user turn.

The current system replaces count/warning with token-based cost estimation and
a hard stop.

---

## The four-layer design

### Layer 1 — `pricing.py`: cost estimation

`estimate_cost(model, input_tokens, output_tokens, cache_read_tokens,
cache_creation_tokens)` converts token counts to a USD dollar figure using
per-model per-million-token rates.

```
Model                      Input    Output   Cache read  Cache create
claude-sonnet-4-6          $3.00   $15.00      $0.30       $3.75
claude-haiku-4-5-20251001  $0.80    $4.00      $0.08       $1.00
claude-opus-4-7           $15.00   $75.00      $1.50      $18.75
```

**Fallback:** Any model ID not in the table falls back to Sonnet rates. New
model variants appear frequently; maintaining an exhaustive list is not
practical. Sonnet sits mid-range, so a fallback estimate is slightly wrong
rather than catastrophically wrong.

### Layer 2 — `session.py`: snapshots and deltas

`session.token_snapshot()` captures the four token counters at a point in time
as a frozen `TokenSnapshot` dataclass.

`session.cost_since(snapshot)` computes the cost of tokens accumulated *since*
that snapshot — the delta, not the total. This is the mechanism that makes
per-turn windows work without resetting the session's cumulative counts.

```python
snap = session.token_snapshot()   # before the turn
# ... API call, tool calls ...
turn_cost = session.cost_since(snap)   # cost of just this turn
```

### Layer 3 — `loop.py`: automatic enforcement

Two mechanisms operate inside `_run_turn`, the inner tool-calling loop:

**Hard stop at $0.25/turn**

A snapshot is taken at the start of every `_run_turn` call (i.e., at the start
of processing each user message). After each `stream_response` call, if
`cost_since(snap)` exceeds `_COST_HARD_STOP = 0.25`, all pending tool_use
blocks receive error tool_results and the loop exits. The agent cannot bypass
this — it does not run as an assistant decision; it runs as a loop-level check.

**Cost injection every 5 tool calls**

After every `_COST_INJECTION_INTERVAL = 5` tool executions, a
`{"type": "text", "text": "Estimated cost this turn: $X.XXXX"}` block is
appended to the same user message that carries the tool_results. This gives
Claude visibility into its own spending mid-turn so it can choose to stop or
proceed more conservatively.

### Layer 4 — `cost_tool.py`: agent-callable reporting

`make_check_cost_tool(session)` returns a `Tool` that Claude can call by name
(`check_cost`) to request a full breakdown of session-level token usage and
estimated cost at any point. Unlike the auto-injection (which reports turn cost),
this reports cumulative session totals.

---

## Key design decisions

### Hard stop, not a soft warning

**Decision:** When the per-turn cost limit is hit, tool calls stop immediately.
Pending tool_uses receive error results; the while loop breaks.

**Context:** A warning printed to the terminal only reaches the *user*. It does
not propagate into the conversation as a tool error, so the agent's next
inference turn has no signal that anything changed. An error tool_result, by
contrast, is part of the conversation: Claude reads it, the invariant
(every tool_use must have a tool_result) is satisfied, and the agent's next
output can respond to the situation.

**Consequences:** The loop always terminates cleanly. The conversation history
is never left in an invalid state (no orphaned tool_use blocks). The user may
see an abrupt end to an agentic task and will need to resume manually.

### Per-turn window, not a cumulative session budget

**Decision:** The snapshot is taken at the start of each user turn, and the
hard stop measures cost *since that snapshot*, not since session start.

**Context:** A cumulative budget would prevent long but legitimate sessions —
a user who debugs a complex issue over 20 turns should not hit a wall because
the sum of 20 cheap turns crossed a threshold. The risk to guard against is a
*single runaway turn* where the agent loops unproductively. Per-turn isolation
addresses that directly.

**Consequences:** A user can have an arbitrarily long session as long as no
single turn exceeds the limit. A user who intentionally asks for a large
agentic task ("refactor the entire codebase") may still hit the hard stop
within a single turn. The `/clear` command resets the turn boundary implicitly
since it wipes the conversation, causing the next message to start a fresh
`_run_turn`.

### Cost injection as a text block, not a separate message

**Decision:** The cost report is added as a `{"type": "text", ...}` block
inside the same user message that contains the `tool_result` blocks — not as
a separate user message before or after.

**Context:** The Anthropic API enforces a strict invariant: after an assistant
message containing `tool_use` blocks, the immediately following user message
*must* contain matching `tool_result` blocks. Inserting a separate user message
between the assistant's tool_use and the tool_results would violate this
constraint and cause an API error.

A text block *alongside* tool_results is permitted — user messages with list
content can mix block types. This keeps the injection atomic with the results
it accompanies and requires no changes to message ordering.

### `check_cost` as a closure, not a stateless tool

**Decision:** `make_check_cost_tool(session)` is a factory that returns a
`Tool` whose `function` is a closure over the live session object.

**Context:** All tools in `ALL_TOOLS` are stateless: they receive a
`dict[str, Any]` input and return a string, with no access to session state.
`check_cost` needs the session's current token counters, which change after
every API call. A stateless function has no way to read them.

Three alternatives were considered:

- **Pass session as a tool input** — callers (Claude) would need to know and
  send token counts, which it cannot: it does not have access to its own usage
  data mid-conversation
- **Global session state** — untestable and fragile
- **Closure (chosen)** — the factory captures a reference to the session
  object. Because the session is mutated in place as tokens accumulate, the
  closure always reads the current state without any extra wiring

**Consequences:** `check_cost` cannot live in `ALL_TOOLS` (which is stateless
by design). It is created in `main.py` after session initialisation and merged
into the tool list there. `_build_tools` and `_make_executor` were refactored
to accept an explicit tool list rather than hard-coding `ALL_TOOLS`, which also
makes both functions independently testable.

---

## Constants

| Constant | Value | Location | Meaning |
|---|---|---|---|
| `_COST_HARD_STOP` | `0.25` | `loop.py` | USD per turn before stopping |
| `_COST_INJECTION_INTERVAL` | `5` | `loop.py` | Tool calls between cost injections |
| `_MAX_TOOL_CALLS_PER_TURN` | `20` | `loop.py` | Absolute tool call ceiling per turn |

The tool call ceiling (`_MAX_TOOL_CALLS_PER_TURN`) predates the cost system
and remains as a secondary guard. Cost and call count are complementary: cost
catches expensive-per-call loops; the call count catches cheap-but-numerous
loops (e.g. a bash tool that returns a few bytes each time).
