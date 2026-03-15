from __future__ import annotations

from pathlib import Path

from snapshot_state import (
    PaneSnapshot,
    SavedSnapshot,
    SessionSnapshot,
    WindowSnapshot,
    capture_runtime_snapshot,
    load_saved_snapshot,
    restore_saved_sessions_if_needed,
    restore_snapshot,
    write_runtime_snapshot,
)
from tmux_api import INDEX_SESSION_NAME, Pane, Session, Window


class CaptureAPI:
    def __init__(self, home: Path) -> None:
        self.env = {"HOME": str(home)}
        self._sessions = [
            Session(INDEX_SESSION_NAME, attached=0, windows=1),
            Session("work", attached=1, windows=2),
        ]

    def default_start_directory(self) -> str:
        return self.env["HOME"]

    def list_sessions(self, allow_missing_server: bool = False) -> list[Session]:
        return list(self._sessions)

    def list_windows(self, session_name: str) -> list[Window]:
        assert session_name == "work"
        return [
            Window(index=0, name="dev", active=False, layout="layout-left"),
            Window(index=1, name="notes", active=True, layout="layout-right"),
        ]

    def list_panes(self, target: str | None = None) -> list[Pane]:
        panes = {
            "work:0": [
                Pane("work", "%1", 101, "node", window_index=0, pane_index=0, current_path="/tmp/work", active=False),
                Pane("work", "%2", 102, "bash", window_index=0, pane_index=1, current_path="/tmp/work", active=True),
            ],
            "work:1": [
                Pane("work", "%3", 103, "bash", window_index=1, pane_index=0, current_path="/tmp/notes", active=True),
            ],
        }
        assert target is not None
        return panes[target]

    def process_tree(self):  # type: ignore[no-untyped-def]
        return {}, {}

    def pane_codex_thread_id(self, pane, processes=None, children_by_pid=None):  # type: ignore[no-untyped-def]
        return {"%1": "019cf02b-d991-7221-a544-abaa9bbfa2f3"}.get(pane.pane_id)


class RestoreAPI:
    def __init__(self, home: Path, live_sessions: list[Session] | None = None) -> None:
        self.env = {"HOME": str(home)}
        self.live_sessions = list(live_sessions or [])
        self.calls: list[tuple[object, ...]] = []

    def default_start_directory(self) -> str:
        return self.env["HOME"]

    def list_sessions(self, allow_missing_server: bool = False) -> list[Session]:
        self.calls.append(("list_sessions", allow_missing_server))
        return list(self.live_sessions)

    def has_session(self, name: str) -> bool:
        self.calls.append(("has_session", name))
        return any(session.name == name for session in self.live_sessions)

    def new_session(  # type: ignore[no-untyped-def]
        self,
        session_name,
        detached=False,
        start_directory=None,
        window_name=None,
        command=None,
    ):
        self.calls.append(
            ("new_session", session_name, detached, start_directory, window_name, command)
        )
        self.live_sessions.append(Session(session_name, attached=0, windows=1))
        return 0

    def new_window(self, session_name, window_name, start_directory=None, command=None):  # type: ignore[no-untyped-def]
        self.calls.append(("new_window", session_name, window_name, start_directory, command))
        return 0

    def split_window(self, target, start_directory=None, command=None):  # type: ignore[no-untyped-def]
        self.calls.append(("split_window", target, start_directory, command))
        return 0

    def select_layout(self, target, layout):  # type: ignore[no-untyped-def]
        self.calls.append(("select_layout", target, layout))

    def select_pane(self, target):  # type: ignore[no-untyped-def]
        self.calls.append(("select_pane", target))

    def select_window(self, target):  # type: ignore[no-untyped-def]
        self.calls.append(("select_window", target))


def build_snapshot() -> SavedSnapshot:
    return SavedSnapshot(
        version=1,
        captured_at=123,
        sessions=[
            SessionSnapshot(
                name="work",
                active_window_position=1,
                windows=[
                    WindowSnapshot(
                        name="dev",
                        layout="layout-left",
                        active_pane_position=1,
                        panes=[
                            PaneSnapshot(
                                cwd="/tmp/work",
                                kind="codex",
                                codex_thread_id="019cf02b-d991-7221-a544-abaa9bbfa2f3",
                            ),
                            PaneSnapshot(cwd="/tmp/work"),
                        ],
                    ),
                    WindowSnapshot(
                        name="notes",
                        layout="layout-right",
                        active_pane_position=0,
                        panes=[PaneSnapshot(cwd="/tmp/notes")],
                    ),
                ],
            )
        ],
    )


def test_capture_runtime_snapshot_collects_layout_and_codex_threads(tmp_path: Path) -> None:
    snapshot = capture_runtime_snapshot(CaptureAPI(tmp_path))
    assert [session.name for session in snapshot.sessions] == ["work"]
    assert snapshot.sessions[0].active_window_position == 1
    assert [window.name for window in snapshot.sessions[0].windows] == ["dev", "notes"]
    assert snapshot.sessions[0].windows[0].active_pane_position == 1
    assert snapshot.sessions[0].windows[0].panes[0].kind == "codex"
    assert (
        snapshot.sessions[0].windows[0].panes[0].codex_thread_id
        == "019cf02b-d991-7221-a544-abaa9bbfa2f3"
    )


def test_write_and_load_snapshot_round_trips(tmp_path: Path) -> None:
    snapshot = write_runtime_snapshot(CaptureAPI(tmp_path))
    loaded = load_saved_snapshot(str(tmp_path))
    assert loaded == snapshot


def test_restore_snapshot_rebuilds_tmux_layouts_and_codex_panes(tmp_path: Path) -> None:
    api = RestoreAPI(tmp_path)
    result = restore_snapshot(api, build_snapshot())
    assert result.restored_sessions == ["work"]
    assert result.skipped_sessions == []
    assert api.calls == [
        ("has_session", "work"),
        (
            "new_session",
            "work",
            True,
            "/tmp/work",
            "dev",
            "codex resume 019cf02b-d991-7221-a544-abaa9bbfa2f3",
        ),
        ("split_window", "work:0", "/tmp/work", None),
        ("select_layout", "work:0", "layout-left"),
        ("select_pane", "work:0.1"),
        ("new_window", "work", "notes", "/tmp/notes", None),
        ("select_layout", "work:1", "layout-right"),
        ("select_pane", "work:1.0"),
        ("select_window", "work:1"),
    ]


def test_restore_saved_sessions_if_needed_restores_when_only_index_exists(tmp_path: Path) -> None:
    path = write_runtime_snapshot(CaptureAPI(tmp_path))
    assert path.sessions
    api = RestoreAPI(
        tmp_path,
        live_sessions=[Session(INDEX_SESSION_NAME, attached=0, windows=1)],
    )
    result = restore_saved_sessions_if_needed(api)
    assert result is not None
    assert result.restored_sessions == ["work"]


def test_restore_saved_sessions_if_needed_skips_when_live_sessions_exist(tmp_path: Path) -> None:
    snapshot = write_runtime_snapshot(CaptureAPI(tmp_path))
    assert snapshot.sessions
    api = RestoreAPI(
        tmp_path,
        live_sessions=[Session("work", attached=1, windows=2)],
    )
    result = restore_saved_sessions_if_needed(api)
    assert result is None
    assert api.calls == [("list_sessions", True)]
