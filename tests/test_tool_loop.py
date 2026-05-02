"""Tests for tool execution within the input loop.

These expose the missing tool-execution loop in run_loop: when Claude
returns a tool_use block, the tool must actually be called, its result
appended to the conversation, and a second inference turn triggered.
"""

from contextlib import contextmanager
from typing import Any

import pytest

from claude_agent.cli.session import Session
from tests.fakes import FakeInput, FakeOutput, FakeStreamHandle


def _tool_use_result_invariant(conversation: list[Any]) -> None:
    """Assert every tool_use block has exactly one matching tool_result in the next message."""
    for i, msg in enumerate(conversation):
        if msg["role"] != "assistant" or not isinstance(msg["content"], list):
            continue
        tool_use_ids = {
            block["id"]
            for block in msg["content"]
            if isinstance(block, dict) and block.get("type") == "tool_use"
        }
        if not tool_use_ids:
            continue
        assert i + 1 < len(conversation), "assistant tool_use message has no following message"
        next_msg = conversation[i + 1]
        assert next_msg["role"] == "user", "message after tool_use is not a user message"
        assert isinstance(next_msg["content"], list), "tool_result message has empty/non-list content"
        result_ids = {
            block["tool_use_id"]
            for block in next_msg["content"]
            if isinstance(block, dict) and block.get("type") == "tool_result"
        }
        assert tool_use_ids == result_ids, (
            f"tool_use ids {tool_use_ids} do not match tool_result ids {result_ids}"
        )


class _SequentialStreamingClient:
    """Yields a different FakeStreamHandle on each successive stream() call."""

    def __init__(self, handles: list[FakeStreamHandle]) -> None:
        self._handles = list(handles)

    @contextmanager
    def stream(
        self,
        model: str,  # noqa: ARG002
        system: str,  # noqa: ARG002
        tools: list[dict[str, Any]],  # noqa: ARG002
        messages: list[Any],  # noqa: ARG002
        on_handle: Any = None,  # noqa: ANN401
    ) -> Any:  # noqa: ANN202
        handle = self._handles.pop(0) if self._handles else FakeStreamHandle()
        if on_handle is not None:
            on_handle(handle)
        yield handle


@pytest.fixture()
def session() -> Session:
    return Session(model="opus", system_prompt="system", tools=[])


def test_tool_is_executed_and_result_appended(session: Session) -> None:
    """run_loop must execute the tool Claude calls and feed the result back."""
    from claude_agent.cli.loop import run_loop

    first = FakeStreamHandle(tool_uses=[{"name": "bash", "id": "tu_1", "input": {"command": "ls"}}])
    second = FakeStreamHandle(tokens=["Done!"])
    client = _SequentialStreamingClient([first, second])

    executed: list[tuple[str, dict[str, Any]]] = []

    def executor(name: str, tool_input: dict[str, Any]) -> tuple[str, bool]:
        executed.append((name, tool_input))
        return "file.py\n", False

    run_loop(FakeInput(["list files", None]), FakeOutput(), client, session, tool_executor=executor)

    assert len(executed) == 1
    assert executed[0] == ("bash", {"command": "ls"})


def test_tool_result_added_to_conversation(session: Session) -> None:
    """Tool results must appear in the conversation so Claude sees them."""
    from claude_agent.cli.loop import run_loop

    first = FakeStreamHandle(tool_uses=[{"name": "bash", "id": "tu_1", "input": {"command": "ls"}}])
    second = FakeStreamHandle(tokens=["Done!"])
    client = _SequentialStreamingClient([first, second])

    run_loop(
        FakeInput(["list files", None]),
        FakeOutput(),
        client,
        session,
        tool_executor=lambda n, i: ("file.py\n", False),
    )

    # conversation: user, assistant (tool_use), user (tool_result), assistant (text)
    roles = [m["role"] for m in session.conversation]
    assert roles == ["user", "assistant", "user", "assistant"]


def test_large_tool_result_is_truncated_in_conversation(session: Session) -> None:
    """Tool results over 1000 chars must be truncated before storing in conversation."""
    from claude_agent.cli.loop import run_loop, _MAX_TOOL_RESULT_IN_HISTORY

    big_result = "x" * 5000
    first = FakeStreamHandle(tool_uses=[{"name": "read_file", "id": "tu_1", "input": {"path": "big.py"}}])
    second = FakeStreamHandle(tokens=["Done!"])
    client = _SequentialStreamingClient([first, second])

    run_loop(
        FakeInput(["read big file", None]),
        FakeOutput(),
        client,
        session,
        tool_executor=lambda n, i: (big_result, False),
    )

    # Find the tool_result message (role="user" with list content)
    tool_result_msg = next(
        m for m in session.conversation
        if m["role"] == "user" and isinstance(m["content"], list)
    )
    content = tool_result_msg["content"]
    assert isinstance(content, list)
    stored = content[0]["content"]  # type: ignore[index]
    assert isinstance(stored, str)
    assert len(stored) <= _MAX_TOOL_RESULT_IN_HISTORY + 100  # allow for truncation suffix
    assert "truncated" in stored


def test_small_tool_result_is_stored_in_full(session: Session) -> None:
    """Tool results under 1000 chars must be stored verbatim."""
    from claude_agent.cli.loop import run_loop, _MAX_TOOL_RESULT_IN_HISTORY

    small_result = "file.py\nother.py\n"
    first = FakeStreamHandle(tool_uses=[{"name": "bash", "id": "tu_1", "input": {"command": "ls"}}])
    second = FakeStreamHandle(tokens=["Done!"])
    client = _SequentialStreamingClient([first, second])

    run_loop(
        FakeInput(["list files", None]),
        FakeOutput(),
        client,
        session,
        tool_executor=lambda n, i: (small_result, False),
    )

    tool_result_msg = next(
        m for m in session.conversation
        if m["role"] == "user" and isinstance(m["content"], list)
    )
    content = tool_result_msg["content"]
    assert isinstance(content, list)
    stored = content[0]["content"]  # type: ignore[index]
    assert stored == small_result


def test_tool_call_limit_prevents_runaway_loops(session: Session) -> None:
    """Tool call limits should prevent infinite loops and runaway costs."""
    from claude_agent.cli.loop import run_loop, _MAX_TOOL_CALLS_PER_TURN

    # Create a stream that keeps generating tool calls
    many_tools = [{"name": "bash", "id": f"tu_{i}", "input": {"command": "echo hi"}} 
                  for i in range(_MAX_TOOL_CALLS_PER_TURN + 5)]
    
    first = FakeStreamHandle(tokens=["Starting..."], tool_uses=many_tools)
    client = _SequentialStreamingClient([first])
    out = FakeOutput()

    run_loop(
        FakeInput(["cause chaos", None]),
        out,
        client,
        session,
        tool_executor=lambda n, i: ("output", False),
    )

    # Should have stopped at the limit, not executed all tools
    assert len(out.tool_lines) == _MAX_TOOL_CALLS_PER_TURN
    assert len(out.errors) >= 1
    assert any("tool call limit" in error for error in out.errors)


def test_tool_call_limit_all_tool_uses_have_results(session: Session) -> None:
    """Every tool_use must have a matching tool_result even when the limit fires mid-response."""
    from claude_agent.cli.loop import run_loop, _MAX_TOOL_CALLS_PER_TURN

    over_limit = _MAX_TOOL_CALLS_PER_TURN + 3
    tools = [{"name": "bash", "id": f"tu_{i}", "input": {"command": "echo hi"}}
             for i in range(over_limit)]
    client = _SequentialStreamingClient([FakeStreamHandle(tool_uses=tools)])

    run_loop(
        FakeInput(["go", None]),
        FakeOutput(),
        client,
        session,
        tool_executor=lambda n, i: ("ok", False),
    )

    _tool_use_result_invariant(session.conversation)


def test_tool_call_limit_accumulated_across_responses_no_empty_content(session: Session) -> None:
    """When the limit fires before executing any tool in a response, no empty user message is appended."""
    from claude_agent.cli.loop import run_loop, _MAX_TOOL_CALLS_PER_TURN

    # First response exactly fills the limit; second response pushes over it immediately.
    first_tools = [{"name": "bash", "id": f"tu_a{i}", "input": {}} for i in range(_MAX_TOOL_CALLS_PER_TURN)]
    second_tools = [{"name": "bash", "id": "tu_b0", "input": {}}, {"name": "bash", "id": "tu_b1", "input": {}}]

    client = _SequentialStreamingClient([
        FakeStreamHandle(tool_uses=first_tools),
        FakeStreamHandle(tool_uses=second_tools),
    ])

    run_loop(
        FakeInput(["go", None]),
        FakeOutput(),
        client,
        session,
        tool_executor=lambda n, i: ("ok", False),
    )

    for msg in session.conversation:
        if msg["role"] == "user":
            assert msg["content"], f"empty user message found in conversation: {msg}"
    _tool_use_result_invariant(session.conversation)


def test_newline_appears_between_response_tokens_and_tool_line(session: Session) -> None:
    """A newline must separate streamed response text from the following tool-call line."""
    from claude_agent.cli.loop import run_loop

    tool_use = {"name": "read_file", "id": "tu_1", "input": {"path": "foo.py"}}
    first = FakeStreamHandle(tokens=["I'll read that file"], tool_uses=[tool_use])
    second = FakeStreamHandle(tokens=["Done!"])
    client = _SequentialStreamingClient([first, second])
    out = FakeOutput()

    run_loop(
        FakeInput(["read foo.py", None]),
        out,
        client,
        session,
        tool_executor=lambda n, i: ("file contents", False),
    )

    kinds = [e[0] for e in out.events]
    assert "tool_line" in kinds, "no tool_line events recorded"
    first_tool_idx = next(i for i, k in enumerate(kinds) if k == "tool_line")
    pre_tool_token_indices = [i for i, k in enumerate(kinds) if k == "token" and i < first_tool_idx]
    assert pre_tool_token_indices, "no tokens recorded before tool_line"
    last_pre_tool_token_idx = max(pre_tool_token_indices)
    newline_between = any(
        k == "newline" and last_pre_tool_token_idx < i < first_tool_idx
        for i, k in enumerate(kinds)
    )
    assert newline_between, f"no newline between last response token and tool_line; events: {kinds}"


def test_full_result_still_available_for_expand(session: Session) -> None:
    """session.last_tool_result must hold the full result even when conversation is truncated."""
    from claude_agent.cli.loop import run_loop

    big_result = "y" * 5000
    first = FakeStreamHandle(tool_uses=[{"name": "read_file", "id": "tu_1", "input": {"path": "f.py"}}])
    second = FakeStreamHandle(tokens=["Done!"])
    client = _SequentialStreamingClient([first, second])

    run_loop(
        FakeInput(["read file", None]),
        FakeOutput(),
        client,
        session,
        tool_executor=lambda n, i: (big_result, False),
    )

    assert session.last_tool_result == big_result


# --- cost injection / hard stop ---

def test_cost_injection_adds_text_block_after_n_tool_calls(session: Session) -> None:
    """After _COST_INJECTION_INTERVAL tool calls, a cost-report text block appears in tool results."""
    from claude_agent.cli.loop import run_loop, _COST_INJECTION_INTERVAL

    tools = [{"name": "bash", "id": f"tu_{i}", "input": {}} for i in range(_COST_INJECTION_INTERVAL)]
    client = _SequentialStreamingClient([
        FakeStreamHandle(tool_uses=tools),
        FakeStreamHandle(tokens=["done"]),
    ])

    run_loop(FakeInput(["go", None]), FakeOutput(), client, session,
             tool_executor=lambda n, i: ("ok", False))

    tool_result_msg = next(
        m for m in session.conversation
        if m["role"] == "user" and isinstance(m["content"], list)
    )
    text_blocks: list[Any] = [b for b in tool_result_msg["content"]
                               if isinstance(b, dict) and b.get("type") == "text"]
    assert len(text_blocks) >= 1
    assert "cost" in text_blocks[0]["text"].lower()


def test_no_cost_injection_before_n_tool_calls(session: Session) -> None:
    """No cost text block is injected when fewer than _COST_INJECTION_INTERVAL tools have run."""
    from claude_agent.cli.loop import run_loop, _COST_INJECTION_INTERVAL

    tools = [{"name": "bash", "id": f"tu_{i}", "input": {}} for i in range(_COST_INJECTION_INTERVAL - 1)]
    client = _SequentialStreamingClient([
        FakeStreamHandle(tool_uses=tools),
        FakeStreamHandle(tokens=["done"]),
    ])

    run_loop(FakeInput(["go", None]), FakeOutput(), client, session,
             tool_executor=lambda n, i: ("ok", False))

    for msg in session.conversation:
        if msg["role"] == "user" and isinstance(msg["content"], list):
            text_blocks = [b for b in msg["content"]
                           if isinstance(b, dict) and b.get("type") == "text"]
            assert text_blocks == [], f"unexpected text blocks: {text_blocks}"


def test_cost_hard_stop_prevents_tool_execution(session: Session) -> None:
    """When stream cost exceeds _COST_HARD_STOP, tools are not executed."""
    from claude_agent.cli.loop import run_loop
    from claude_agent.cli.session import Session as _Session

    # 100k input tokens at Sonnet ($3/M) = $0.30 > $0.25 threshold
    expensive_handle = FakeStreamHandle(
        tool_uses=[{"name": "bash", "id": "tu_0", "input": {}}],
        input_tokens=100_000,
    )
    s = _Session(model="claude-sonnet-4-6", system_prompt="s", tools=[])
    executed: list[str] = []
    client = _SequentialStreamingClient([expensive_handle])

    def _executor(name: str, inp: dict[str, Any]) -> tuple[str, bool]:
        executed.append(name)
        return "ok", False

    run_loop(FakeInput(["go", None]), FakeOutput(), client, s, tool_executor=_executor)

    assert executed == []


def test_cost_hard_stop_shows_error(session: Session) -> None:
    """An error message mentioning cost is shown when the hard stop fires."""
    from claude_agent.cli.loop import run_loop
    from claude_agent.cli.session import Session as _Session

    expensive_handle = FakeStreamHandle(
        tool_uses=[{"name": "bash", "id": "tu_0", "input": {}}],
        input_tokens=100_000,
    )
    s = _Session(model="claude-sonnet-4-6", system_prompt="s", tools=[])
    out = FakeOutput()
    client = _SequentialStreamingClient([expensive_handle])

    run_loop(FakeInput(["go", None]), out, client, s,
             tool_executor=lambda n, i: ("ok", False))

    assert any("cost" in e.lower() for e in out.errors)


def test_cost_hard_stop_all_tool_uses_have_results(session: Session) -> None:
    """Every tool_use must have a matching tool_result even when the hard stop fires."""
    from claude_agent.cli.loop import run_loop
    from claude_agent.cli.session import Session as _Session

    tools = [{"name": "bash", "id": f"tu_{i}", "input": {}} for i in range(3)]
    expensive_handle = FakeStreamHandle(tool_uses=tools, input_tokens=100_000)
    s = _Session(model="claude-sonnet-4-6", system_prompt="s", tools=[])
    client = _SequentialStreamingClient([expensive_handle])

    run_loop(FakeInput(["go", None]), FakeOutput(), client, s,
             tool_executor=lambda n, i: ("ok", False))

    _tool_use_result_invariant(s.conversation)
