from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

import tmux_api
from tmux_api import (
    DEFAULT_INDEX_KEY,
    AgentStatus,
    INDEX_WINDOW_NAME,
    LIST_PANES_FORMAT,
    MANAGED_COPY_MODE_VI_KEYS,
    MANAGED_PREFIX_KEYS,
    MANAGED_ROOT_KEYS,
    TmuxAPI,
    ProcessInfo,
    attach_or_create_session,
    ensure_index_session,
    index_browser_command,
    kill_session_safely,
    kill_sessions_safely,
    reload_managed_config,
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


def test_index_browser_command_uses_active_interpreter(monkeypatch) -> None:
    monkeypatch.setattr(tmux_api.sys, "executable", "/tmp/venv/bin/python")
    entrypoint = Path(tmux_api.__file__).resolve().with_name("main.py")
    assert tmux_api.index_browser_command() == f"{shlex.quote('/tmp/venv/bin/python')} {shlex.quote(str(entrypoint))} p"


def test_attach_or_create_outside_tmux_attaches_existing() -> None:
    api = FakeAPI(
        {
            ("has-session", "-t", "=work"): FakeProc(returncode=0),
            ("attach-session", "-t", "=work"): FakeProc(returncode=0),
        }
    )
    assert attach_or_create_session(api, "work") == 0
    assert api.calls == [
        ("has-session", "-t", "=work"),
        ("attach-session", "-t", "=work"),
    ]


def test_attach_or_create_inside_tmux_creates_and_switches() -> None:
    api = FakeAPI(
        {
            ("has-session", "-t", "=work"): FakeProc(returncode=1),
            ("new-session", "-d", "-c", "/tmp/home", "-s", "work"): FakeProc(returncode=0),
            ("switch-client", "-t", "=work"): FakeProc(returncode=0),
        },
        env={"TMUX": "/tmp/socket,1,0", "HOME": "/tmp/home"},
    )
    assert attach_or_create_session(api, "work") == 0
    assert api.calls == [
        ("has-session", "-t", "=work"),
        ("new-session", "-d", "-c", "/tmp/home", "-s", "work"),
        ("switch-client", "-t", "=work"),
    ]


def test_attach_or_create_outside_tmux_creates_in_home_directory() -> None:
    api = FakeAPI(
        {
            ("has-session", "-t", "=work"): FakeProc(returncode=1),
            ("new-session", "-c", "/tmp/home", "-s", "work"): FakeProc(returncode=0),
        },
        env={"HOME": "/tmp/home"},
    )
    assert attach_or_create_session(api, "work") == 0
    assert api.calls == [
        ("has-session", "-t", "=work"),
        ("new-session", "-c", "/tmp/home", "-s", "work"),
    ]


def test_attach_or_create_index_ensures_managed_session_first(monkeypatch) -> None:
    ensured: list[object] = []

    class IndexAPI(FakeAPI):
        def has_session(self, name: str) -> bool:
            self.calls.append(("has-session", "-t", f"={name}"))
            return True

    api = IndexAPI(
        {
            ("switch-client", "-t", "=index"): FakeProc(returncode=0),
        },
        env={"TMUX": "/tmp/socket,1,0"},
    )

    def fake_ensure_index(active_api):  # type: ignore[no-untyped-def]
        ensured.append(active_api)
        return False

    monkeypatch.setattr(tmux_api, "ensure_index_session", fake_ensure_index)
    assert attach_or_create_session(api, "index") == 0
    assert ensured == [api]
    assert api.calls == [
        ("has-session", "-t", "=index"),
        ("switch-client", "-t", "=index"),
    ]


def test_attach_or_create_inside_tmux_uses_explicit_client_tty_when_available() -> None:
    api = FakeAPI(
        {
            ("has-session", "-t", "=work"): FakeProc(returncode=0),
            ("switch-client", "-c", "/dev/pts/0", "-t", "=work"): FakeProc(returncode=0),
        },
        env={"TMUX": "/tmp/socket,1,0", "TMUX_CLIENT_TTY": "/dev/pts/0"},
    )
    assert attach_or_create_session(api, "work") == 0
    assert api.calls == [
        ("has-session", "-t", "=work"),
        ("switch-client", "-c", "/dev/pts/0", "-t", "=work"),
    ]


def test_reload_managed_config_unbinds_tm_managed_keys_and_sources_primary_conf(tmp_path) -> None:
    home_dir = tmp_path / "home"
    config_dir = home_dir / ".config" / "tmux"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "tmux.conf"
    config_path.write_text('bind -n "F10" run-shell "TMUX_CLIENT_TTY=\'#{client_tty}\' \\"/tmp/tm\\" index >/dev/null 2>&1"\n')

    api = FakeAPI({}, env={"HOME": str(home_dir)})

    reload_managed_config(api)

    assert ("unbind-key", "-q", "-n", "F10") in api.calls
    assert ("unbind-key", "-q", "-n", DEFAULT_INDEX_KEY) in api.calls
    assert ("unbind-key", "-q", "-n", "M-|") in api.calls
    assert ("unbind-key", "-q", "q") in api.calls
    assert ("unbind-key", "-q", "-T", "copy-mode-vi", "C-j") in api.calls
    assert api.calls[-1] == ("source-file", str(config_path))
    root_unbinds = [call for call in api.calls if call[:3] == ("unbind-key", "-q", "-n")]
    prefix_unbinds = [call for call in api.calls if call[:2] == ("unbind-key", "-q") and "-n" not in call and "-T" not in call]
    copy_mode_unbinds = [call for call in api.calls if call[:4] == ("unbind-key", "-q", "-T", "copy-mode-vi")]
    assert len(root_unbinds) == len({DEFAULT_INDEX_KEY, "F10", *MANAGED_ROOT_KEYS})
    assert len(prefix_unbinds) == len(MANAGED_PREFIX_KEYS)
    assert len(copy_mode_unbinds) == len(MANAGED_COPY_MODE_VI_KEYS)


def test_ensure_index_session_creates_missing_index() -> None:
    browser_command = index_browser_command()
    api = FakeAPI(
        {
            ("has-session", "-t", "=index"): FakeProc(returncode=1),
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
        ("has-session", "-t", "=index"),
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
    class BrowserAPI(FakeAPI):
        def _process_snapshot(self) -> dict[int, ProcessInfo]:
            return {
                100: ProcessInfo(100, 1, "python3", "python3 /tmp/tm/main.py p"),
            }

    api = BrowserAPI(
        {
            ("has-session", "-t", "=index"): FakeProc(returncode=0),
            ("display-message", "-p", "-t", "index:index", "#{window_id}"): FakeProc(returncode=0, stdout="@1"),
            ("list-panes", "-t", "index:index", "-F", LIST_PANES_FORMAT): FakeProc(
                stdout="index\t0\t0\t%0\t100\tpython3\t/tmp/home\t1\n"
            ),
        }
    )
    created = ensure_index_session(api)
    assert created is False
    assert api.calls == [
        ("has-session", "-t", "=index"),
        ("display-message", "-p", "-t", "index:index", "#{window_id}"),
        ("list-panes", "-t", "index:index", "-F", LIST_PANES_FORMAT),
    ]


def test_ensure_index_session_creates_missing_browser_window() -> None:
    browser_command = index_browser_command()
    api = FakeAPI(
        {
            ("has-session", "-t", "=index"): FakeProc(returncode=0),
            ("display-message", "-p", "-t", "index:index", "#{window_id}"): FakeProc(returncode=1),
            (
                "new-window",
                "-d",
                "-t",
                "=index",
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
        ("has-session", "-t", "=index"),
        ("display-message", "-p", "-t", "index:index", "#{window_id}"),
        (
            "new-window",
            "-d",
            "-t",
            "=index",
            "-n",
            INDEX_WINDOW_NAME,
            "-c",
            "/tmp/home",
            browser_command,
        ),
    ]


def test_ensure_index_session_respawns_browser_when_window_exists_without_tm_p() -> None:
    browser_command = index_browser_command()

    class BrokenIndexAPI(FakeAPI):
        def _process_snapshot(self) -> dict[int, ProcessInfo]:
            return {
                100: ProcessInfo(100, 1, "bash", "bash"),
            }

    api = BrokenIndexAPI(
        {
            ("has-session", "-t", "=index"): FakeProc(returncode=0),
            ("display-message", "-p", "-t", "index:index", "#{window_id}"): FakeProc(returncode=0, stdout="@1"),
            ("list-panes", "-t", "index:index", "-F", LIST_PANES_FORMAT): FakeProc(
                stdout="index\t0\t0\t%0\t100\tbash\t/tmp/home\t1\n"
            ),
            ("respawn-pane", "-k", "-t", "%0", browser_command): FakeProc(returncode=0),
        },
        env={"HOME": "/tmp/home"},
    )
    created = ensure_index_session(api)
    assert created is True
    assert api.calls == [
        ("has-session", "-t", "=index"),
        ("display-message", "-p", "-t", "index:index", "#{window_id}"),
        ("list-panes", "-t", "index:index", "-F", LIST_PANES_FORMAT),
        ("respawn-pane", "-k", "-t", "%0", browser_command),
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


def test_has_session_uses_exact_target() -> None:
    api = FakeAPI(
        {
            ("has-session", "-t", "=work"): FakeProc(returncode=0),
        }
    )
    assert api.has_session("work") is True
    assert api.calls == [("has-session", "-t", "=work")]


def test_window_base_index_reads_tmux_option() -> None:
    api = FakeAPI(
        {
            ("show-options", "-gqv", "base-index"): FakeProc(stdout="1\n"),
        }
    )
    assert api.window_base_index() == 1
    assert api.calls == [("show-options", "-gqv", "base-index")]


def test_pane_base_index_defaults_to_zero_on_invalid_value() -> None:
    api = FakeAPI(
        {
            ("show-options", "-gwqv", "pane-base-index"): FakeProc(stdout="invalid\n"),
        }
    )
    assert api.pane_base_index() == 0
    assert api.calls == [("show-options", "-gwqv", "pane-base-index")]


def test_rename_session_uses_tmux_rename_command() -> None:
    api = FakeAPI(
        {
            ("rename-session", "-t", "=work", "notes"): FakeProc(returncode=0),
        }
    )
    api.rename_session("work", "notes")
    assert api.calls == [("rename-session", "-t", "=work", "notes")]


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


def test_list_session_agent_statuses_treats_background_terminal_wait_as_working() -> None:
    class AgentAPI(FakeAPI):
        def _process_snapshot(self) -> dict[int, ProcessInfo]:
            return {
                100: ProcessInfo(100, 1, "node-MainThread", "node /home/ryan/.npm-global/bin/codex"),
                101: ProcessInfo(101, 100, "codex", "/vendor/codex/codex"),
            }

    api = AgentAPI(
        {
            ("list-panes", "-a", "-F", LIST_PANES_FORMAT): FakeProc(
                stdout="work\t0\t0\t%1\t100\tnode\t/tmp/work\t1\n"
            ),
            ("capture-pane", "-p", "-t", "%1", "-S", "-40"): FakeProc(
                stdout="Waiting for background\nterminal\n"
            ),
        }
    )

    statuses = api.list_session_agent_statuses()
    assert statuses == {"work": AgentStatus(total=1, working=1, idle=0)}


def test_pane_text_shows_working_for_background_terminal_wait_text() -> None:
    assert tmux_api._pane_text_shows_working("Waiting for background terminal\n") is True
    assert tmux_api._pane_text_shows_working("Waiting for background\nterminal\n") is True


def test_rollout_thread_id_parser_extracts_codex_thread_id() -> None:
    output = (
        "codex 2101 ryan 45w REG 0,55 340110 14346254 "
        "/home/ryan/.codex/sessions/2026/03/15/"
        "rollout-2026-03-15T11-55-31-019cf02b-d991-7221-a544-abaa9bbfa2f3.jsonl\n"
    )
    assert _rollout_thread_id_from_lsof_output(output) == "019cf02b-d991-7221-a544-abaa9bbfa2f3"


def test_pane_codex_thread_id_returns_none_when_lsof_is_missing(monkeypatch) -> None:
    api = TmuxAPI()
    pane = tmux_api.Pane("work", "%1", 100, "node")
    processes = {
        100: ProcessInfo(100, 1, "node-MainThread", "node /home/ryan/.npm-global/bin/codex"),
        101: ProcessInfo(101, 100, "codex", "/vendor/codex/codex"),
    }
    children_by_pid = {1: [100], 100: [101]}

    def raise_missing_lsof(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise FileNotFoundError("lsof")

    monkeypatch.setattr(subprocess, "run", raise_missing_lsof)
    assert api.pane_codex_thread_id(pane, processes=processes, children_by_pid=children_by_pid) is None


def test_kill_session_safely_moves_clients_then_kills() -> None:
    api = FakeAPI(
        {
            ("has-session", "-t", "=work"): FakeProc(returncode=0),
            ("list-sessions", "-F", LIST_SESSIONS_FORMAT): FakeProc(
                stdout="work\t1\t2\t200\nnotes\t0\t1\t100\n"
            ),
            ("list-clients", "-t", "=work", "-F", "#{client_tty}"): FakeProc(stdout="/dev/pts/1\n/dev/pts/2\n"),
            ("switch-client", "-c", "/dev/pts/1", "-t", "=notes"): FakeProc(returncode=0),
            ("switch-client", "-c", "/dev/pts/2", "-t", "=notes"): FakeProc(returncode=0),
            ("kill-session", "-t", "=work"): FakeProc(returncode=0),
        }
    )
    fallback = kill_session_safely(api, "work")
    assert fallback == "notes"
    assert api.calls == [
        ("has-session", "-t", "=work"),
        ("list-sessions", "-F", LIST_SESSIONS_FORMAT),
        ("list-clients", "-t", "=work", "-F", "#{client_tty}"),
        ("switch-client", "-c", "/dev/pts/1", "-t", "=notes"),
        ("switch-client", "-c", "/dev/pts/2", "-t", "=notes"),
        ("kill-session", "-t", "=work"),
    ]


def test_kill_sessions_safely_uses_non_target_fallback_for_multiple_targets() -> None:
    api = FakeAPI(
        {
            ("has-session", "-t", "=work"): FakeProc(returncode=0),
            ("has-session", "-t", "=notes"): FakeProc(returncode=0),
            ("list-sessions", "-F", LIST_SESSIONS_FORMAT): FakeProc(
                stdout="work\t1\t2\t300\nnotes\t1\t1\t200\nkeep\t0\t4\t100\n"
            ),
            ("list-clients", "-t", "=work", "-F", "#{client_tty}"): FakeProc(stdout="/dev/pts/1\n"),
            ("list-clients", "-t", "=notes", "-F", "#{client_tty}"): FakeProc(stdout="/dev/pts/2\n"),
            ("switch-client", "-c", "/dev/pts/1", "-t", "=keep"): FakeProc(returncode=0),
            ("switch-client", "-c", "/dev/pts/2", "-t", "=keep"): FakeProc(returncode=0),
            ("kill-session", "-t", "=work"): FakeProc(returncode=0),
            ("kill-session", "-t", "=notes"): FakeProc(returncode=0),
        }
    )
    fallback = kill_sessions_safely(api, ["work", "notes"])
    assert fallback == "keep"
    assert api.calls == [
        ("has-session", "-t", "=work"),
        ("has-session", "-t", "=notes"),
        ("list-sessions", "-F", LIST_SESSIONS_FORMAT),
        ("list-clients", "-t", "=work", "-F", "#{client_tty}"),
        ("switch-client", "-c", "/dev/pts/1", "-t", "=keep"),
        ("list-clients", "-t", "=notes", "-F", "#{client_tty}"),
        ("switch-client", "-c", "/dev/pts/2", "-t", "=keep"),
        ("kill-session", "-t", "=work"),
        ("kill-session", "-t", "=notes"),
    ]


def test_kill_sessions_safely_rejects_managed_index_session() -> None:
    api = FakeAPI({})
    try:
        kill_sessions_safely(api, ["index"])
    except tmux_api.TmuxError as exc:
        assert str(exc) == "Cannot kill managed session: index"
    else:
        raise AssertionError("TmuxError not raised")
    assert api.calls == []


def test_kill_session_safely_creates_temp_fallback_in_home_directory(monkeypatch) -> None:
    monkeypatch.setattr(tmux_api.time, "time", lambda: 123)
    api = FakeAPI(
        {
            ("has-session", "-t", "=work"): FakeProc(returncode=0),
            ("list-sessions", "-F", LIST_SESSIONS_FORMAT): FakeProc(
                stdout="work\t1\t2\t200\n"
            ),
            ("new-session", "-d", "-c", "/tmp/home", "-s", "__tmp_123"): FakeProc(returncode=0),
            ("list-clients", "-t", "=work", "-F", "#{client_tty}"): FakeProc(stdout="/dev/pts/1\n"),
            ("switch-client", "-c", "/dev/pts/1", "-t", "=__tmp_123"): FakeProc(returncode=0),
            ("kill-session", "-t", "=work"): FakeProc(returncode=0),
        },
        env={"HOME": "/tmp/home"},
    )
    fallback = kill_session_safely(api, "work")
    assert fallback == "__tmp_123"
    assert api.calls[:4] == [
        ("has-session", "-t", "=work"),
        ("list-sessions", "-F", LIST_SESSIONS_FORMAT),
        ("list-sessions", "-F", LIST_SESSIONS_FORMAT),
        ("new-session", "-d", "-c", "/tmp/home", "-s", "__tmp_123"),
    ]
    assert api.calls[4:] == [
        ("list-clients", "-t", "=work", "-F", "#{client_tty}"),
        ("switch-client", "-c", "/dev/pts/1", "-t", "=__tmp_123"),
        ("kill-session", "-t", "=work"),
    ]
