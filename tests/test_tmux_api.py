from __future__ import annotations

from tmux_api import TmuxAPI, attach_or_create_session, kill_session_safely, kill_sessions_safely


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
            ("new-session", "-d", "-s", "work"): FakeProc(returncode=0),
            ("switch-client", "-t", "work"): FakeProc(returncode=0),
        },
        env={"TMUX": "/tmp/socket,1,0"},
    )
    assert attach_or_create_session(api, "work") == 0
    assert api.calls == [
        ("has-session", "-t", "work"),
        ("new-session", "-d", "-s", "work"),
        ("switch-client", "-t", "work"),
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
