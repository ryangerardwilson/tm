from __future__ import annotations

from session_tui import SessionBrowserState, _handle_normal_key, _handle_prompt_key
from tmux_api import Session


def build_state() -> SessionBrowserState:
    return SessionBrowserState(
        sessions=[
            Session("a", attached=0, windows=1),
            Session("b", attached=1, windows=2),
            Session("c", attached=0, windows=3),
        ]
    )


def test_marking_auto_advances_and_kills_marked_sessions() -> None:
    state = build_state()
    action, _ = _handle_normal_key(state, ord("m"))
    assert action is None
    assert state.marked == {"a"}
    assert state.index == 1
    assert state.selected_names() == ["a"]


def test_visual_selection_returns_contiguous_range() -> None:
    state = build_state()
    _handle_normal_key(state, ord("v"))
    _handle_normal_key(state, ord("j"))
    _handle_normal_key(state, ord("j"))
    assert state.selected_names() == ["a", "b", "c"]


def test_help_is_hidden_until_toggled() -> None:
    state = build_state()
    assert state.show_help is False
    _handle_normal_key(state, ord("?"))
    assert state.show_help is True


def test_leader_sequence_opens_new_session_prompt() -> None:
    state = build_state()
    _handle_normal_key(state, ord(","))
    assert state.leader_sequence == ","
    _handle_normal_key(state, ord("n"))
    assert state.leader_sequence == ",n"
    action, value = _handle_normal_key(state, ord("s"))
    assert action == "prompt"
    assert value == "New session: "


def test_prompt_collects_name_and_submits() -> None:
    state = build_state()
    state.begin_prompt("New session: ")
    _handle_prompt_key(state, ord("w"))
    _handle_prompt_key(state, ord("o"))
    _handle_prompt_key(state, ord("r"))
    _handle_prompt_key(state, ord("k"))
    action, value = _handle_prompt_key(state, 10)
    assert action == "create"
    assert value == "work"
