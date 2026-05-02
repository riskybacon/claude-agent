# Token Efficiency

## Why it matters

Every API call sends the full conversation history as input. Token usage
compounds with each turn:

```
Request N input tokens =
  system prompt        (~200 tokens, fixed per call)
+ tool definitions × 5 (~800 tokens, fixed per call)
+ all user messages sent so far
+ all assistant responses sent so far
+ all tool results returned so far
```

The fixed costs (system prompt + tools) are present on every single call.
The variable costs grow with session length, and tool results are the biggest
driver — reading a 5 KB file adds ~1,250 tokens that get resent on every
subsequent call in the session.

---

## Method 1 — Truncate tool results in conversation history

**Status:** Implemented in `src/coding_agent/cli/loop.py` (`_run_turn`).

**Constant:** `_MAX_TOOL_RESULT_IN_HISTORY = 1000`

Claude does not need the full verbatim content of a tool result in order to
reason about it on future turns. It needs enough context to know what it saw
("I read foo.py, it had a class Agent with a run() method"), not the complete
10 KB. Tool results over 1,000 characters are truncated before being stored
in the conversation, with a suffix telling Claude it can ask to re-read the
file if it needs the full content.

`session.last_tool_result` still stores the full result so `/expand` continues
to show the user the complete output.

**Impact:** A session that reads 10 × 5 KB files accumulates ~12,500 extra
input tokens per subsequent call without truncation. With truncation that drops
to ~1,250 — a 10× reduction in tool-result overhead.

**Trade-off:** Claude loses the exact content of earlier tool calls. For most
reasoning tasks this is fine — it can re-read a file if it needs to. For tasks
requiring exact cross-file diffs it may occasionally need a second read.

---

## Method 2 — Prompt caching

**Status:** Implemented in `src/coding_agent/cli/streaming.py`
(`AnthropicStream.stream`).

The Anthropic API supports caching stable input prefixes server-side for 5
minutes. Cached tokens cost 10% of normal input tokens on re-read (with a
125% write cost on the first request). Since the system prompt and tool
definitions are identical on every call in a session, marking them with
`cache_control: {"type": "ephemeral"}` means turns 2–N pay 10% instead of
100% for those ~1,000 tokens.

The cache breakpoint sits at the end of the tool list — everything before it
(system prompt + tools) is stable and cached; everything after it (the
conversation) changes every turn and is not cached.

```
[system prompt  ← cache_control here]
[tool 1        ]
[tool 2        ]
[tool N        ← cache_control here]
──────────────────────────────── cache boundary
[message 1     ]  not cached — changes every turn
[message 2     ]
...
```

**Impact:** Over a 20-turn session with 5 tools, roughly 18,000 input tokens
are billed at cache rate rather than full rate.

**Trade-off:** The cache TTL is 5 minutes. A long pause between turns causes
a cache miss and pays the write cost again. If the session's model is switched
mid-session via `/model`, the cached prefix for the old model is no longer
useful.

---

## Method 3 — Sliding window (not yet implemented)

A sliding window drops the oldest conversation turns from the messages array
sent to the API while keeping the full history visible in the terminal.
Methods 1 and 2 cover the common case; this is the right follow-up for
sessions that routinely run to 50+ turns.

### The structural constraint

You cannot slice the messages array at an arbitrary index. The Anthropic API
requires:

1. The first message must be `role: user`
2. Roles must strictly alternate: user, assistant, user, assistant...
3. Every `tool_use` block in an assistant message must be paired with a
   matching `tool_result` in the immediately following user message — you
   cannot drop one without the other

The unit of the window must therefore be a **conversation turn**, not an
individual message. A single user question can expand into many messages once
tools are involved:

```
user:      "review this codebase"           ← turn start
assistant: [tool_use: list_files]
user:      [tool_result: ...]
assistant: [tool_use: read_file × 3]
user:      [tool_result × 3]
assistant: "Here is my review..."           ← turn end
```

That is one user question mapping to six messages. A naive "last 20 messages"
window would slice into the middle of a tool loop and produce an invalid
conversation.

### Turn boundary detection

A turn starts at every user message whose content is a plain string (not a
list of `tool_result` blocks):

```python
def _is_turn_start(msg: dict) -> bool:
    return msg["role"] == "user" and isinstance(msg["content"], str)
```

### Design sketch

```python
def _trim_to_turns(conversation: list, max_turns: int) -> list:
    turn_starts = [i for i, m in enumerate(conversation) if _is_turn_start(m)]
    if len(turn_starts) <= max_turns:
        return conversation
    return conversation[turn_starts[-max_turns]:]
```

Called in `stream_response` as a view — the full history stays in
`session.conversation`, only the trimmed slice goes to the API:

```python
messages=_trim_to_turns(session.conversation, max_turns=20)
```

### Trade-offs

- Claude loses context from dropped turns. It may repeat work it already did
  or contradict earlier statements.
- A `/history` command or terminal scrollback would still show the full
  session since we do not mutate `session.conversation`.
- The right value for `max_turns` depends on the task. Coding tasks that
  touch many files benefit from a larger window; focused single-file edits
  work fine with a smaller one.

---

## Method 4 — Cost Mitigation & Runaway Prevention

**Status:** Implemented in `src/coding_agent/cli/loop.py` and `src/coding_agent/cli/session.py`.

Even with token efficiency measures, coding agents can still generate runaway costs through:
- Infinite tool loops (agent keeps calling tools without progress)  
- User getting stuck in debugging spirals
- Ctrl-C not working during tool execution

### Tool Call Limits

**Constant:** `_MAX_TOOL_CALLS_PER_TURN = 20`

Prevents infinite tool loops by stopping execution after 20 tool calls in a single turn:

```python
if tool_calls_made >= _MAX_TOOL_CALLS_PER_TURN:
    out.print_error(f"Hit tool call limit ({_MAX_TOOL_CALLS_PER_TURN}) - stopping to prevent runaway costs")
    break
```

### Session Usage Tracking  

Track API and tool calls per session:

```python
session.api_calls_made += 1
session.tool_calls_made += 1
```

- **Warning system**: Alerts when >10 API calls in one session
- **Usage command**: `/usage` shows current session statistics  
- **Clear command**: `/clear` resets usage counters along with conversation

### Enhanced Cancellation

Added `KeyboardInterrupt` handling in tool execution loop:

```python
try:
    result, is_error = tool_executor(tu["name"], tu["input"])
    # ...
except KeyboardInterrupt:
    out.print_error("Tool execution cancelled") 
    return
```

**Why needed:** The original signal handler only cancels streaming, but tool execution happens after streaming completes.

### Additional Safeguards (Not Implemented)

For even stricter cost control, consider:
- **Time limits**: Stop turns after N minutes
- **Token estimation**: Rough cost calculation with user confirmation
- **Daily/session spending caps**: Hard limits with persistence  
- **User confirmation**: Prompt before expensive operations

---

## Summary

| Method | Where | Status | Best for |
|--------|-------|--------|----------|
| Truncate tool results | `loop.py` `_run_turn` | Done | File-heavy sessions |
| Prompt caching | `streaming.py` `AnthropicStream` | Done | All sessions |  
| Sliding window | `streaming.py` `stream_response` | Not implemented | Very long sessions (50+ turns) |
| Cost mitigation | `loop.py` `session.py` | **Done** | **Preventing runaway costs** |
