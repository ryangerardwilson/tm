from __future__ import annotations

import curses

import session_tui
from session_tui import (
    AGENT_WORKING_FRAMES,
    SessionBrowserState,
    _enter_session,
    _fit_row_segments,
    _format_session_row,
    _handle_normal_key,
    _maybe_write_hourly_snapshot,
    _handle_prompt_key,
    _rename_selected_session,
    _visible_sessions,
)
from tmux_api import AgentStatus, Session


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
    assert action == "prompt-create"
    assert value is None


def test_leader_rn_opens_rename_prompt_for_current_session() -> None:
    state = build_state()
    state.index = 1

    action, value = _handle_normal_key(state, ord(","))
    assert action is None
    assert value is None
    assert state.leader_active is True
    assert state.leader_buffer == ""

    action, value = _handle_normal_key(state, ord("r"))
    assert action is None
    assert value is None
    assert state.leader_active is True
    assert state.leader_buffer == "r"

    action, value = _handle_normal_key(state, ord("n"))
    assert action == "prompt-rename"
    assert value == "b"
    assert state.leader_active is False
    assert state.leader_buffer == ""


def test_index_session_is_hidden_from_browser_rows() -> None:
    sessions = [
        Session("index", attached=0, windows=1),
        Session("work", attached=1, windows=2),
        Session("notes", attached=0, windows=3),
    ]
    assert [session.name for session in _visible_sessions(sessions)] == ["work", "notes"]


def test_prompt_collects_name_and_submits() -> None:
    state = build_state()
    state.begin_prompt("New session: ", action="create")
    _handle_prompt_key(state, ord("w"))
    _handle_prompt_key(state, ord("o"))
    _handle_prompt_key(state, ord("r"))
    _handle_prompt_key(state, ord("k"))
    action, value = _handle_prompt_key(state, 10)
    assert action == "create"
    assert value == "work"


def test_prompt_submits_rename_action() -> None:
    state = build_state()
    state.begin_prompt("Rename session: ", action="rename", initial_value="work")
    _handle_prompt_key(state, curses.KEY_BACKSPACE)
    _handle_prompt_key(state, curses.KEY_BACKSPACE)
    _handle_prompt_key(state, curses.KEY_BACKSPACE)
    _handle_prompt_key(state, curses.KEY_BACKSPACE)
    _handle_prompt_key(state, ord("n"))
    _handle_prompt_key(state, ord("e"))
    _handle_prompt_key(state, ord("w"))
    action, value = _handle_prompt_key(state, 10)
    assert action == "rename"
    assert value == "new"


def test_enter_from_index_session_switches_and_refreshes_order(monkeypatch) -> None:
    state = build_state()
    state.index = 1

    class FakeAPI:
        env = {"TMUX": "/tmp/socket,1,0"}

        def __init__(self) -> None:
            self.switched: list[str] = []

        def switch_client(self, target_session: str) -> None:
            self.switched.append(target_session)

        def list_sessions(self) -> list[Session]:
            return [
                Session("b", attached=1, windows=2),
                Session("a", attached=0, windows=1),
                Session("c", attached=0, windows=3),
                Session("index", attached=0, windows=1),
            ]

        def list_session_agent_statuses(self) -> dict[str, AgentStatus]:
            return {}

    monkeypatch.setattr(session_tui, "ensure_index_session", lambda api: False)
    api = FakeAPI()
    rc = _enter_session(api, state, persistent=True)
    assert rc is None
    assert api.switched == ["b"]
    assert [session.name for session in state.sessions] == ["b", "a", "c"]
    assert state.index == 0
    assert state.status_message == "Switched to b"


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


def test_rename_selected_session_refreshes_state_and_preserves_mark(monkeypatch) -> None:
    state = build_state()
    state.marked.add("a")
    recorded: list[object] = []

    class FakeAPI:
        def __init__(self) -> None:
            self.renamed: list[tuple[str, str]] = []

        def has_session(self, name: str) -> bool:
            return False

        def rename_session(self, current_name: str, new_name: str) -> None:
            self.renamed.append((current_name, new_name))

        def list_sessions(self) -> list[Session]:
            return [
                Session("renamed", attached=0, windows=1),
                Session("b", attached=1, windows=2),
                Session("c", attached=0, windows=3),
                Session("index", attached=0, windows=1),
            ]

        def list_session_agent_statuses(self) -> dict[str, AgentStatus]:
            return {}

    def fake_ensure_index(active_api):  # type: ignore[no-untyped-def]
        return False

    def fake_write(active_api):  # type: ignore[no-untyped-def]
        recorded.append(active_api)

    monkeypatch.setattr(session_tui, "ensure_index_session", fake_ensure_index)
    monkeypatch.setattr(session_tui, "write_runtime_snapshot", fake_write)

    api = FakeAPI()
    _rename_selected_session(api, state, "renamed")

    assert api.renamed == [("a", "renamed")]
    assert [session.name for session in state.sessions] == ["renamed", "b", "c"]
    assert state.current_name() == "renamed"
    assert state.marked == {"renamed"}
    assert state.status_message == "Renamed a to renamed"
    assert recorded == [api]


def test_sync_agent_statuses_updates_existing_rows_without_reordering() -> None:
    state = build_state()
    state.index = 1
    state.sync_agent_statuses({"b": AgentStatus(total=2, working=1, idle=1)})
    assert [session.name for session in state.sessions] == ["a", "b", "c"]
    assert state.index == 1
    assert state.sessions[0].agent_total == 0
    assert state.sessions[1].agent_total == 2
    assert state.sessions[1].agent_working == 1
    assert state.sessions[1].agent_idle == 1


def test_current_row_uses_bold_not_reverse() -> None:
    line, agent_suffix, attrs = _format_session_row(
        "work",
        is_current=True,
        is_marked=False,
        is_visual=False,
        attached=False,
    )
    assert line == ">   work"
    assert agent_suffix == ""
    assert attrs & curses.A_BOLD
    assert not attrs & curses.A_REVERSE


def test_visual_row_uses_reverse_video() -> None:
    line, agent_suffix, attrs = _format_session_row(
        "work",
        is_current=False,
        is_marked=True,
        is_visual=True,
        attached=True,
    )
    assert line == " *+ work (attached)"
    assert agent_suffix == ""
    assert attrs & curses.A_REVERSE
    assert not attrs & curses.A_BOLD


def test_session_row_shows_working_animation_only_when_agents_are_active() -> None:
    line, agent_suffix, _ = _format_session_row(
        "work",
        is_current=False,
        is_marked=False,
        is_visual=False,
        attached=False,
        agent_total=1,
        agent_working=0,
        agent_idle=1,
    )
    assert line == "    work"
    assert agent_suffix == ""

    line, agent_suffix, _ = _format_session_row(
        "notes",
        is_current=False,
        is_marked=False,
        is_visual=False,
        attached=False,
        agent_total=2,
        agent_working=1,
        agent_idle=1,
        animation_step=2,
    )
    assert line == "    notes"
    assert agent_suffix == AGENT_WORKING_FRAMES[2]

    line, agent_suffix, _ = _format_session_row(
        "repo_tm",
        is_current=False,
        is_marked=False,
        is_visual=False,
        attached=False,
        agent_total=3,
        agent_working=2,
        agent_idle=1,
        animation_step=5,
    )
    assert line == "    repo_tm"
    assert agent_suffix == AGENT_WORKING_FRAMES[5]


def test_fit_row_segments_preserves_agent_suffix_in_narrow_widths() -> None:
    base_line, suffix_line = _fit_row_segments(
        "    repo_tm (attached)",
        AGENT_WORKING_FRAMES[0],
        20,
    )
    assert suffix_line == AGENT_WORKING_FRAMES[0]
    assert len(base_line) + len(suffix_line) <= 20


def test_hourly_snapshot_runs_immediately_for_persistent_browser(monkeypatch) -> None:
    state = build_state()
    recorded: list[object] = []

    def fake_write(api):  # type: ignore[no-untyped-def]
        recorded.append(api)

    api = object()
    monkeypatch.setattr(session_tui, "write_runtime_snapshot", fake_write)
    saved_at = _maybe_write_hourly_snapshot(api, state, True, None, now=100.0)
    assert saved_at == 100.0
    assert recorded == [api]


def test_hourly_snapshot_waits_until_interval_passes(monkeypatch) -> None:
    state = build_state()
    recorded: list[object] = []

    def fake_write(api):  # type: ignore[no-untyped-def]
        recorded.append(api)

    api = object()
    monkeypatch.setattr(session_tui, "write_runtime_snapshot", fake_write)
    saved_at = _maybe_write_hourly_snapshot(api, state, True, 100.0, now=200.0)
    assert saved_at == 100.0
    assert recorded == []
