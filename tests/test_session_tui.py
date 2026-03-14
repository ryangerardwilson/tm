from __future__ import annotations

import curses

from session_tui import (
    SessionBrowserState,
    _enter_session,
    _format_session_row,
    _handle_normal_key,
    _handle_prompt_key,
    _visible_sessions,
)
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


def test_j_wraps_from_last_to_first() -> None:
    state = build_state()
    state.index = len(state.sessions) - 1
    _handle_normal_key(state, ord("j"))
    assert state.index == 0


def test_k_wraps_from_first_to_last() -> None:
    state = build_state()
    _handle_normal_key(state, ord("k"))
    assert state.index == len(state.sessions) - 1


def test_n_opens_new_session_prompt() -> None:
    state = build_state()
    action, value = _handle_normal_key(state, ord("n"))
    assert action == "prompt"
    assert value == "New session: "


def test_r_requests_refresh() -> None:
    state = build_state()
    action, value = _handle_normal_key(state, ord("r"))
    assert action == "refresh"
    assert value is None


def test_index_session_is_hidden_from_browser_rows() -> None:
    sessions = [
        Session("index", attached=0, windows=1),
        Session("work", attached=1, windows=2),
        Session("notes", attached=0, windows=3),
    ]
    assert [session.name for session in _visible_sessions(sessions)] == ["work", "notes"]


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


def test_enter_from_index_session_switches_without_exiting() -> None:
    state = build_state()

    class FakeAPI:
        env = {"TMUX": "/tmp/socket,1,0"}

        def __init__(self) -> None:
            self.switched: list[str] = []

        def switch_client(self, target_session: str) -> None:
            self.switched.append(target_session)

    api = FakeAPI()
    rc = _enter_session(api, state, persistent=True)
    assert rc is None
    assert api.switched == ["a"]
    assert state.status_message == "Switched to a"


def test_enter_from_non_index_tmux_session_exits_browser() -> None:
    state = build_state()

    class FakeAPI:
        env = {"TMUX": "/tmp/socket,1,0"}

        def __init__(self) -> None:
            self.switched: list[str] = []

        def switch_client(self, target_session: str) -> None:
            self.switched.append(target_session)

    api = FakeAPI()
    rc = _enter_session(api, state)
    assert rc == 0
    assert api.switched == ["a"]


def test_current_row_uses_bold_not_reverse() -> None:
    line, attrs = _format_session_row(
        "work",
        is_current=True,
        is_marked=False,
        is_visual=False,
        attached=False,
    )
    assert line == ">   work"
    assert attrs & curses.A_BOLD
    assert not attrs & curses.A_REVERSE


def test_visual_row_uses_reverse_video() -> None:
    line, attrs = _format_session_row(
        "work",
        is_current=False,
        is_marked=True,
        is_visual=True,
        attached=True,
    )
    assert line == " *+ work (attached)"
    assert attrs & curses.A_REVERSE
    assert not attrs & curses.A_BOLD
