from __future__ import annotations

import tmux_api
from tmux_api import (
    AgentStatus,
    INDEX_WINDOW_NAME,
    LIST_PANES_FORMAT,
    TmuxAPI,
    ProcessInfo,
    attach_or_create_session,
    ensure_index_session,
    index_browser_command,
    kill_session_safely,
    kill_sessions_safely,
    _rollout_thread_id_from_lsof_output,
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


LIST_SESSIONS_FORMAT = "#{session_name}\t#{session_attached}\t#{session_windows}\t#{session_last_attached}"


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


def test_list_sessions_orders_by_most_recent_attach() -> None:
    api = FakeAPI(
        {
            ("list-sessions", "-F", LIST_SESSIONS_FORMAT): FakeProc(
                stdout="older\t0\t1\t100\nnewer\t1\t2\t300\nnever\t0\t1\t0\n"
            )
        }
    )
    sessions = api.list_sessions()
    assert [session.name for session in sessions] == ["newer", "older", "never"]


def test_list_session_agent_statuses_counts_working_and_idle_codex_panes() -> None:
    class AgentAPI(FakeAPI):
        def _process_snapshot(self) -> dict[int, ProcessInfo]:
            return {
                100: ProcessInfo(100, 1, "node-MainThread", "node /home/ryan/.npm-global/bin/codex"),
                101: ProcessInfo(101, 100, "codex", "/vendor/codex/codex"),
                200: ProcessInfo(200, 1, "node-MainThread", "node /home/ryan/.npm-global/bin/codex"),
                201: ProcessInfo(201, 200, "codex", "/vendor/codex/codex"),
                300: ProcessInfo(300, 1, "bash", "bash"),
            }

    api = AgentAPI(
        {
            ("list-panes", "-a", "-F", LIST_PANES_FORMAT): FakeProc(
                stdout=(
                    "work\t0\t0\t%1\t100\tnode\t/tmp/work\t1\n"
                    "work\t0\t1\t%2\t200\tnode\t/tmp/work\t0\n"
                    "notes\t0\t0\t%3\t300\tbash\t/tmp/notes\t1\n"
                )
            ),
            ("capture-pane", "-p", "-t", "%1", "-S", "-40"): FakeProc(
                stdout="• Working (28s • esc to interrupt)\n"
            ),
            ("capture-pane", "-p", "-t", "%2", "-S", "-40"): FakeProc(
                stdout="› Explain this codebase\n"
            ),
        }
    )
    statuses = api.list_session_agent_statuses()
    assert statuses == {"work": AgentStatus(total=2, working=1, idle=1)}


def test_rollout_thread_id_parser_extracts_codex_thread_id() -> None:
    output = (
        "codex 2101 ryan 45w REG 0,55 340110 14346254 "
        "/home/ryan/.codex/sessions/2026/03/15/"
        "rollout-2026-03-15T11-55-31-019cf02b-d991-7221-a544-abaa9bbfa2f3.jsonl\n"
    )
    assert _rollout_thread_id_from_lsof_output(output) == "019cf02b-d991-7221-a544-abaa9bbfa2f3"


def test_kill_session_safely_moves_clients_then_kills() -> None:
    api = FakeAPI(
        {
            ("has-session", "-t", "work"): FakeProc(returncode=0),
            ("list-sessions", "-F", LIST_SESSIONS_FORMAT): FakeProc(
                stdout="work\t1\t2\t200\nnotes\t0\t1\t100\n"
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
        ("list-sessions", "-F", LIST_SESSIONS_FORMAT),
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
            ("list-sessions", "-F", LIST_SESSIONS_FORMAT): FakeProc(
                stdout="work\t1\t2\t300\nnotes\t1\t1\t200\nkeep\t0\t4\t100\n"
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
        ("list-sessions", "-F", LIST_SESSIONS_FORMAT),
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
            ("list-sessions", "-F", LIST_SESSIONS_FORMAT): FakeProc(
                stdout="work\t1\t2\t200\n"
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
        ("list-sessions", "-F", LIST_SESSIONS_FORMAT),
        ("list-sessions", "-F", LIST_SESSIONS_FORMAT),
        ("new-session", "-d", "-c", "/tmp/home", "-s", "__tmp_123"),
    ]
    assert api.calls[4:] == [
        ("list-clients", "-t", "work", "-F", "#{client_tty}"),
        ("switch-client", "-c", "/dev/pts/1", "-t", "__tmp_123"),
        ("kill-session", "-t", "work"),
    ]
