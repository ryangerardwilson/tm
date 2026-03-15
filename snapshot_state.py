from __future__ import annotations

import json
import shlex
import time
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from tmux_api import INDEX_SESSION_NAME, TmuxAPI, TmuxError


SNAPSHOT_INTERVAL_SECONDS = 3600
SNAPSHOT_VERSION = 1
SNAPSHOT_FILE_NAME = "session_snapshot.json"


class SnapshotError(RuntimeError):
    """Raised when the saved snapshot cannot be read or written."""


@dataclass(frozen=True)
class PaneSnapshot:
    cwd: str
    kind: str = "shell"
    codex_thread_id: str | None = None


@dataclass(frozen=True)
class WindowSnapshot:
    name: str
    layout: str
    active_pane_position: int
    panes: list[PaneSnapshot]


@dataclass(frozen=True)
class SessionSnapshot:
    name: str
    active_window_position: int
    windows: list[WindowSnapshot]


@dataclass(frozen=True)
class SavedSnapshot:
    version: int
    captured_at: int
    sessions: list[SessionSnapshot]


@dataclass(frozen=True)
class RestoreResult:
    restored_sessions: list[str]
    skipped_sessions: list[str]


def snapshot_path(home: str | None = None) -> Path:
    base = Path(home).expanduser() if home else Path.home()
    return base / ".tm" / "state" / SNAPSHOT_FILE_NAME


def load_saved_snapshot(home: str | None = None) -> SavedSnapshot | None:
    path = snapshot_path(home)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SnapshotError(f"Unable to read saved sessions: {exc}") from exc
    return _snapshot_from_dict(data)


def write_runtime_snapshot(api: TmuxAPI) -> SavedSnapshot:
    snapshot = capture_runtime_snapshot(api)
    path = snapshot_path(api.env.get("HOME"))
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with NamedTemporaryFile(
            "w",
            dir=path.parent,
            prefix=".snapshot.",
            suffix=".json",
            delete=False,
            encoding="utf-8",
        ) as handle:
            json.dump(_snapshot_to_dict(snapshot), handle, indent=2)
            handle.write("\n")
            temp_path = Path(handle.name)
        temp_path.replace(path)
    except OSError as exc:
        raise SnapshotError(f"Unable to save sessions: {exc}") from exc
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink(missing_ok=True)
    return snapshot


def capture_runtime_snapshot(api: TmuxAPI) -> SavedSnapshot:
    sessions = [
        session
        for session in api.list_sessions(allow_missing_server=True)
        if session.name != INDEX_SESSION_NAME
    ]
    processes, children_by_pid = api.process_tree()
    session_snapshots: list[SessionSnapshot] = []
    for session in sessions:
        windows = api.list_windows(session.name)
        window_snapshots: list[WindowSnapshot] = []
        active_window_position = 0
        for window_position, window in enumerate(windows):
            if window.active:
                active_window_position = window_position
            panes = api.list_panes(f"{session.name}:{window.index}")
            pane_snapshots: list[PaneSnapshot] = []
            active_pane_position = 0
            for pane_position, pane in enumerate(panes):
                if pane.active:
                    active_pane_position = pane_position
                thread_id = api.pane_codex_thread_id(
                    pane,
                    processes=processes,
                    children_by_pid=children_by_pid,
                )
                pane_snapshots.append(
                    PaneSnapshot(
                        cwd=pane.current_path or api.default_start_directory(),
                        kind="codex" if thread_id else "shell",
                        codex_thread_id=thread_id,
                    )
                )
            if not pane_snapshots:
                pane_snapshots.append(PaneSnapshot(cwd=api.default_start_directory()))
            window_snapshots.append(
                WindowSnapshot(
                    name=window.name,
                    layout=window.layout,
                    active_pane_position=active_pane_position,
                    panes=pane_snapshots,
                )
            )
        session_snapshots.append(
            SessionSnapshot(
                name=session.name,
                active_window_position=active_window_position,
                windows=window_snapshots,
            )
        )
    return SavedSnapshot(
        version=SNAPSHOT_VERSION,
        captured_at=int(time.time()),
        sessions=session_snapshots,
    )


def restore_saved_sessions_if_needed(api: TmuxAPI) -> RestoreResult | None:
    snapshot = load_saved_snapshot(api.env.get("HOME"))
    if snapshot is None or not snapshot.sessions:
        return None
    live_sessions = [
        session
        for session in api.list_sessions(allow_missing_server=True)
        if session.name != INDEX_SESSION_NAME
    ]
    if live_sessions:
        return None
    return restore_snapshot(api, snapshot)


def restore_snapshot(api: TmuxAPI, snapshot: SavedSnapshot) -> RestoreResult:
    restored_sessions: list[str] = []
    skipped_sessions: list[str] = []
    for session_snapshot in snapshot.sessions:
        if api.has_session(session_snapshot.name):
            skipped_sessions.append(session_snapshot.name)
            continue
        _restore_session(api, session_snapshot)
        restored_sessions.append(session_snapshot.name)
    return RestoreResult(
        restored_sessions=restored_sessions,
        skipped_sessions=skipped_sessions,
    )


def _restore_session(api: TmuxAPI, session_snapshot: SessionSnapshot) -> None:
    if not session_snapshot.windows:
        return
    first_window = session_snapshot.windows[0]
    first_pane = first_window.panes[0]
    rc = api.new_session(
        session_snapshot.name,
        detached=True,
        start_directory=first_pane.cwd or api.default_start_directory(),
        window_name=first_window.name,
        command=_restore_command(first_pane),
    )
    if rc != 0:
        raise TmuxError(f"Unable to restore session: {session_snapshot.name}")
    _restore_window_layout(api, session_snapshot.name, 0, first_window)

    for window_position, window_snapshot in enumerate(session_snapshot.windows[1:], start=1):
        first_window_pane = window_snapshot.panes[0]
        rc = api.new_window(
            session_snapshot.name,
            window_snapshot.name,
            start_directory=first_window_pane.cwd or api.default_start_directory(),
            command=_restore_command(first_window_pane),
        )
        if rc != 0:
            raise TmuxError(f"Unable to restore session: {session_snapshot.name}")
        _restore_window_layout(api, session_snapshot.name, window_position, window_snapshot)

    api.select_window(f"{session_snapshot.name}:{session_snapshot.active_window_position}")


def _restore_window_layout(
    api: TmuxAPI,
    session_name: str,
    window_position: int,
    window_snapshot: WindowSnapshot,
) -> None:
    target = f"{session_name}:{window_position}"
    for pane_snapshot in window_snapshot.panes[1:]:
        rc = api.split_window(
            target,
            start_directory=pane_snapshot.cwd or api.default_start_directory(),
            command=_restore_command(pane_snapshot),
        )
        if rc != 0:
            raise TmuxError(f"Unable to restore session: {session_name}")
    if window_snapshot.layout:
        api.select_layout(target, window_snapshot.layout)
    api.select_pane(f"{target}.{window_snapshot.active_pane_position}")


def _restore_command(pane_snapshot: PaneSnapshot) -> str | None:
    if pane_snapshot.kind != "codex" or not pane_snapshot.codex_thread_id:
        return None
    return f"codex resume {shlex.quote(pane_snapshot.codex_thread_id)}"


def _snapshot_to_dict(snapshot: SavedSnapshot) -> dict[str, Any]:
    return {
        "version": snapshot.version,
        "captured_at": snapshot.captured_at,
        "sessions": [
            {
                "name": session.name,
                "active_window_position": session.active_window_position,
                "windows": [
                    {
                        "name": window.name,
                        "layout": window.layout,
                        "active_pane_position": window.active_pane_position,
                        "panes": [
                            {
                                "cwd": pane.cwd,
                                "kind": pane.kind,
                                "codex_thread_id": pane.codex_thread_id,
                            }
                            for pane in window.panes
                        ],
                    }
                    for window in session.windows
                ],
            }
            for session in snapshot.sessions
        ],
    }


def _snapshot_from_dict(data: dict[str, Any]) -> SavedSnapshot:
    if not isinstance(data, dict):
        raise SnapshotError("Unable to read saved sessions: invalid snapshot format")
    version = data.get("version")
    if version != SNAPSHOT_VERSION:
        raise SnapshotError(f"Unable to read saved sessions: unsupported snapshot version {version}")
    sessions_data = data.get("sessions", [])
    if not isinstance(sessions_data, list):
        raise SnapshotError("Unable to read saved sessions: invalid session list")
    sessions: list[SessionSnapshot] = []
    for session_data in sessions_data:
        if not isinstance(session_data, dict):
            raise SnapshotError("Unable to read saved sessions: invalid session entry")
        windows_data = session_data.get("windows", [])
        if not isinstance(windows_data, list):
            raise SnapshotError("Unable to read saved sessions: invalid window list")
        windows: list[WindowSnapshot] = []
        for window_data in windows_data:
            if not isinstance(window_data, dict):
                raise SnapshotError("Unable to read saved sessions: invalid window entry")
            panes_data = window_data.get("panes", [])
            if not isinstance(panes_data, list):
                raise SnapshotError("Unable to read saved sessions: invalid pane list")
            panes: list[PaneSnapshot] = []
            for pane_data in panes_data:
                if not isinstance(pane_data, dict):
                    raise SnapshotError("Unable to read saved sessions: invalid pane entry")
                panes.append(
                    PaneSnapshot(
                        cwd=str(pane_data.get("cwd", "")),
                        kind=str(pane_data.get("kind", "shell")),
                        codex_thread_id=_optional_str(pane_data.get("codex_thread_id")),
                    )
                )
            windows.append(
                WindowSnapshot(
                    name=str(window_data.get("name", "")),
                    layout=str(window_data.get("layout", "")),
                    active_pane_position=int(window_data.get("active_pane_position", 0)),
                    panes=panes,
                )
            )
        sessions.append(
            SessionSnapshot(
                name=str(session_data.get("name", "")),
                active_window_position=int(session_data.get("active_window_position", 0)),
                windows=windows,
            )
        )
    return SavedSnapshot(
        version=SNAPSHOT_VERSION,
        captured_at=int(data.get("captured_at", 0)),
        sessions=sessions,
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
