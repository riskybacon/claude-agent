"""Tests for session state."""

from coding_agent.cli.session import Session


def _make_session(**kwargs: object) -> Session:
    defaults: dict[str, object] = {"model": "opus", "system_prompt": "default", "tools": []}
    defaults.update(kwargs)
    return Session(
        model=str(defaults["model"]),
        system_prompt=str(defaults["system_prompt"]),
        tools=list(defaults["tools"]),  # type: ignore[arg-type]
    )


def test_clear_resets_conversation() -> None:
    s = _make_session()
    s.conversation.append({"role": "user", "content": "hi"})
    s.clear()
    assert s.conversation == []


def test_clear_preserves_model_and_system_prompt() -> None:
    s = _make_session(model="haiku", system_prompt="custom")
    s.clear()
    assert s.model == "haiku"
    assert s.system_prompt == "custom"


def test_switch_model() -> None:
    s = _make_session(model="opus")
    s.switch_model("haiku")
    assert s.model == "haiku"


def test_last_tool_result_stored() -> None:
    s = _make_session()
    s.last_tool_result = "file contents"
    assert s.last_tool_result == "file contents"


def test_last_tool_result_none_on_init() -> None:
    assert _make_session().last_tool_result is None
