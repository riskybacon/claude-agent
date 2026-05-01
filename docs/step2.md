# Step 2: read_file tool and the tool-execution loop

There are three distinct ideas in `read.py`.

## 0. The API is stateless — tools are re-sent every call

Claude has no memory between API calls. Every call to `run_inference` sends the full tool list as
part of the request — the same way it sends the model name and the conversation history. There is
no registration step, no persistent session. If you didn't include `tools=` in a call, Claude
would have no idea `read_file` exists for that call, even if you sent it on the previous one.

## 1. Telling Claude what tools exist

`READ_FILE_SCHEMA` is a plain JSON Schema dict — it's the contract Claude reads to know what
arguments it's allowed to send when it wants to call `read_file`. In this case: one required field
called `path`, which must be a string.

`READ_FILE_TOOL` bundles that schema together with the human-readable description (which Claude also
reads to decide *when* to use the tool) and the actual Python function to call. That's the `Tool`
dataclass — just four fields held together.

When `run_inference` calls the API, it converts every `Tool` into the dict format the API expects
and passes them all in the `tools=` argument. From that point, Claude knows what tools exist and
what arguments each one takes.

## 2. What Claude sends back

Before step 2, Claude's response was always just text blocks. Now it can also send `tool_use`
blocks. A `tool_use` block looks like this:

```python
{
    "type": "tool_use",
    "id": "toolu_abc123",       # unique ID for this specific call
    "name": "read_file",         # which tool Claude wants to use
    "input": {"path": "foo.txt"} # the arguments it chose
}
```

Claude decides entirely on its own which tool to call and with what arguments. Our job is to execute
whatever it asks for and send the result back.

## 3. The tool loop

This is the core of step 2. `_run_tool_loop` handles the back-and-forth after the first API call:

```
Claude responds
  ├── text block?    → print it
  └── tool_use block? → run the tool, collect the result

Any results collected?
  ├── No  → done, break out
  └── Yes → append results to conversation as a user message
             call Claude again
             loop back to top
```

The key insight is that tool results go back as a **user message**, not an assistant message. The
conversation ends up looking like:

```
user:      "what's in riddle.txt?"
assistant: [tool_use: read_file(path="riddle.txt")]
user:      [tool_result: "Why did the chicken..."]
assistant: [text: "The answer to the riddle is..."]
```

Claude only sends its final plain-text answer once it has all the information it needs. Until then
it keeps requesting tools, and we keep running them.

`_execute_tool` is the lookup — it finds the right `Tool` by name and calls its function. If the
file doesn't exist, `Path.read_text()` raises `OSError`, which is caught and sent back to Claude as
a failed tool result (`is_error: True`) instead of crashing the agent.
