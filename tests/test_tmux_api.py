from __future__ import annotations

import tmux_api
from tmux_api import (
    INDEX_WINDOW_NAME,
    TmuxAPI,
    attach_or_create_session,
    ensure_index_session,
    index_browser_command,
    kill_session_safely,
    kill_sessions_safely,
)


class FakeProc:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class FakeAPI(TmuxAPI):
    def __init__(self, responses: dict[tuple[str, ...], FakeProc], env: dict[str, str] | None = None) -> None:
        super().__init__(env=env or {})
        self.responses = responses
        self.calls: list[tuple[str, ...]] = []

    def _run(self, args: list[str], check: bool = True) -> FakeProc:
        key = tuple(args)
        self.calls.append(key)
        proc = self.responses.get(key, FakeProc())
        if check and proc.returncode != 0:
            raise RuntimeError(proc.stderr or proc.stdout or "tmux command failed")
        return proc


def test_attach_or_create_outside_tmux_attaches_existing() -> None:
    api = FakeAPI(
        {
            ("has-session", "-t", "work"): FakeProc(returncode=0),
            ("attach-session", "-t", "work"): FakeProc(returncode=0),
        }
    )
    assert attach_or_create_session(api, "work") == 0
    assert api.calls == [
        ("has-session", "-t", "work"),
        ("attach-session", "-t", "work"),
    ]


def test_attach_or_create_inside_tmux_creates_and_switches() -> None:
    api = FakeAPI(
        {
            ("has-session", "-t", "work"): FakeProc(returncode=1),
            ("new-session", "-d", "-c", "/tmp/home", "-s", "work"): FakeProc(returncode=0),
            ("switch-client", "-t", "work"): FakeProc(returncode=0),
        },
        env={"TMUX": "/tmp/socket,1,0", "HOME": "/tmp/home"},
    )
    assert attach_or_create_session(api, "work") == 0
    assert api.calls == [
        ("has-session", "-t", "work"),
        ("new-session", "-d", "-c", "/tmp/home", "-s", "work"),
        ("switch-client", "-t", "work"),
    ]


def test_attach_or_create_outside_tmux_creates_in_home_directory() -> None:
    api = FakeAPI(
        {
            ("has-session", "-t", "work"): FakeProc(returncode=1),
            ("new-session", "-c", "/tmp/home", "-s", "work"): FakeProc(returncode=0),
        },
        env={"HOME": "/tmp/home"},
    )
    assert attach_or_create_session(api, "work") == 0
    assert api.calls == [
        ("has-session", "-t", "work"),
        ("new-session", "-c", "/tmp/home", "-s", "work"),
    ]


def test_ensure_index_session_creates_missing_index() -> None:
    browser_command = index_browser_command()
    api = FakeAPI(
        {
            ("has-session", "-t", "index"): FakeProc(returncode=1),
            (
                "new-session",
                "-d",
                "-c",
                "/tmp/home",
                "-s",
                "index",
                "-n",
                INDEX_WINDOW_NAME,
                browser_command,
            ): FakeProc(returncode=0),
        },
        env={"HOME": "/tmp/home"},
    )
    created = ensure_index_session(api)
    assert created is True
    assert api.calls == [
        ("has-session", "-t", "index"),
        (
            "new-session",
            "-d",
            "-c",
            "/tmp/home",
            "-s",
            "index",
            "-n",
            INDEX_WINDOW_NAME,
            browser_command,
        ),
    ]


def test_ensure_index_session_skips_existing_index() -> None:
    api = FakeAPI(
        {
            ("has-session", "-t", "index"): FakeProc(returncode=0),
            ("display-message", "-p", "-t", "index:index", "#{window_id}"): FakeProc(returncode=0, stdout="@1"),
        }
    )
    created = ensure_index_session(api)
    assert created is False
    assert api.calls == [
        ("has-session", "-t", "index"),
        ("display-message", "-p", "-t", "index:index", "#{window_id}"),
    ]


def test_ensure_index_session_creates_missing_browser_window() -> None:
    browser_command = index_browser_command()
    api = FakeAPI(
        {
            ("has-session", "-t", "index"): FakeProc(returncode=0),
            ("display-message", "-p", "-t", "index:index", "#{window_id}"): FakeProc(returncode=1),
            (
                "new-window",
                "-d",
                "-t",
                "index",
                "-n",
                INDEX_WINDOW_NAME,
                "-c",
                "/tmp/home",
                browser_command,
            ): FakeProc(returncode=0),
        },
        env={"HOME": "/tmp/home"},
    )
    created = ensure_index_session(api)
    assert created is True
    assert api.calls == [
        ("has-session", "-t", "index"),
        ("display-message", "-p", "-t", "index:index", "#{window_id}"),
        (
            "new-window",
            "-d",
            "-t",
            "index",
            "-n",
            INDEX_WINDOW_NAME,
            "-c",
            "/tmp/home",
            browser_command,
        ),
    ]


def test_kill_session_safely_moves_clients_then_kills() -> None:
    api = FakeAPI(
        {
            ("has-session", "-t", "work"): FakeProc(returncode=0),
            ("list-sessions", "-F", "#{session_name}\t#{session_attached}\t#{session_windows}"): FakeProc(
                stdout="work\t1\t2\nnotes\t0\t1\n"
            ),
            ("list-clients", "-t", "work", "-F", "#{client_tty}"): FakeProc(stdout="/dev/pts/1\n/dev/pts/2\n"),
            ("switch-client", "-c", "/dev/pts/1", "-t", "notes"): FakeProc(returncode=0),
            ("switch-client", "-c", "/dev/pts/2", "-t", "notes"): FakeProc(returncode=0),
            ("kill-session", "-t", "work"): FakeProc(returncode=0),
        }
    )
    fallback = kill_session_safely(api, "work")
    assert fallback == "notes"
    assert api.calls == [
        ("has-session", "-t", "work"),
        ("list-sessions", "-F", "#{session_name}\t#{session_attached}\t#{session_windows}"),
        ("list-clients", "-t", "work", "-F", "#{client_tty}"),
        ("switch-client", "-c", "/dev/pts/1", "-t", "notes"),
        ("switch-client", "-c", "/dev/pts/2", "-t", "notes"),
        ("kill-session", "-t", "work"),
    ]


def test_kill_sessions_safely_uses_non_target_fallback_for_multiple_targets() -> None:
    api = FakeAPI(
        {
            ("has-session", "-t", "work"): FakeProc(returncode=0),
            ("has-session", "-t", "notes"): FakeProc(returncode=0),
            ("list-sessions", "-F", "#{session_name}\t#{session_attached}\t#{session_windows}"): FakeProc(
                stdout="work\t1\t2\nnotes\t1\t1\nkeep\t0\t4\n"
            ),
            ("list-clients", "-t", "work", "-F", "#{client_tty}"): FakeProc(stdout="/dev/pts/1\n"),
            ("list-clients", "-t", "notes", "-F", "#{client_tty}"): FakeProc(stdout="/dev/pts/2\n"),
            ("switch-client", "-c", "/dev/pts/1", "-t", "keep"): FakeProc(returncode=0),
            ("switch-client", "-c", "/dev/pts/2", "-t", "keep"): FakeProc(returncode=0),
            ("kill-session", "-t", "work"): FakeProc(returncode=0),
            ("kill-session", "-t", "notes"): FakeProc(returncode=0),
        }
    )
    fallback = kill_sessions_safely(api, ["work", "notes"])
    assert fallback == "keep"
    assert api.calls == [
        ("has-session", "-t", "work"),
        ("has-session", "-t", "notes"),
        ("list-sessions", "-F", "#{session_name}\t#{session_attached}\t#{session_windows}"),
        ("list-clients", "-t", "work", "-F", "#{client_tty}"),
        ("switch-client", "-c", "/dev/pts/1", "-t", "keep"),
        ("list-clients", "-t", "notes", "-F", "#{client_tty}"),
        ("switch-client", "-c", "/dev/pts/2", "-t", "keep"),
        ("kill-session", "-t", "work"),
        ("kill-session", "-t", "notes"),
    ]


def test_kill_session_safely_creates_temp_fallback_in_home_directory(monkeypatch) -> None:
    monkeypatch.setattr(tmux_api.time, "time", lambda: 123)
    api = FakeAPI(
        {
            ("has-session", "-t", "work"): FakeProc(returncode=0),
            ("list-sessions", "-F", "#{session_name}\t#{session_attached}\t#{session_windows}"): FakeProc(
                stdout="work\t1\t2\n"
            ),
            ("new-session", "-d", "-c", "/tmp/home", "-s", "__tmp_123"): FakeProc(returncode=0),
            ("list-clients", "-t", "work", "-F", "#{client_tty}"): FakeProc(stdout="/dev/pts/1\n"),
            ("switch-client", "-c", "/dev/pts/1", "-t", "__tmp_123"): FakeProc(returncode=0),
            ("kill-session", "-t", "work"): FakeProc(returncode=0),
        },
        env={"HOME": "/tmp/home"},
    )
    fallback = kill_session_safely(api, "work")
    assert fallback == "__tmp_123"
    assert api.calls[:4] == [
        ("has-session", "-t", "work"),
        ("list-sessions", "-F", "#{session_name}\t#{session_attached}\t#{session_windows}"),
        ("list-sessions", "-F", "#{session_name}\t#{session_attached}\t#{session_windows}"),
        ("new-session", "-d", "-c", "/tmp/home", "-s", "__tmp_123"),
    ]
    assert api.calls[4:] == [
        ("list-clients", "-t", "work", "-F", "#{client_tty}"),
        ("switch-client", "-c", "/dev/pts/1", "-t", "__tmp_123"),
        ("kill-session", "-t", "work"),
    ]
