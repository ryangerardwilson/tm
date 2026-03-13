from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass


class TmuxError(RuntimeError):
    """Raised when a tmux command fails."""


@dataclass(frozen=True)
class Session:
    name: str
    attached: int
    windows: int


class TmuxAPI:
    def __init__(self, env: dict[str, str] | None = None) -> None:
        self.env = os.environ.copy() if env is None else dict(env)

    def _run(self, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
        proc = subprocess.run(
            ["tmux", *args],
            capture_output=True,
            text=True,
            check=False,
            env=self.env,
        )
        if check and proc.returncode != 0:
            message = (proc.stderr or proc.stdout).strip() or "tmux command failed"
            raise TmuxError(message)
        return proc

    def has_session(self, name: str) -> bool:
        return self._run(["has-session", "-t", name], check=False).returncode == 0

    def list_sessions(self) -> list[Session]:
        proc = self._run(
            ["list-sessions", "-F", "#{session_name}\t#{session_attached}\t#{session_windows}"]
        )
        sessions: list[Session] = []
        for line in proc.stdout.splitlines():
            name, attached, windows = (line.split("\t") + ["0", "0"])[:3]
            sessions.append(Session(name=name, attached=int(attached), windows=int(windows)))
        return sessions

    def list_client_ttys(self, session_name: str) -> list[str]:
        proc = self._run(["list-clients", "-t", session_name, "-F", "#{client_tty}"], check=False)
        if proc.returncode != 0:
            return []
        return [line.strip() for line in proc.stdout.splitlines() if line.strip()]

    def switch_client(self, target_session: str, client_tty: str | None = None) -> None:
        args = ["switch-client"]
        if client_tty:
            args.extend(["-c", client_tty])
        args.extend(["-t", target_session])
        self._run(args)

    def attach_session(self, session_name: str) -> int:
        return self._run(["attach-session", "-t", session_name], check=False).returncode

    def new_session(self, session_name: str, detached: bool = False) -> int:
        args = ["new-session"]
        if detached:
            args.append("-d")
        args.extend(["-s", session_name])
        return self._run(args, check=False).returncode

    def kill_session(self, session_name: str) -> None:
        self._run(["kill-session", "-t", session_name])

    def fallback_session(self, target_session: str) -> tuple[str, bool]:
        for session in self.list_sessions():
            if session.name != target_session:
                return session.name, False
        fallback = f"__tmp_{int(time.time())}"
        self._run(["new-session", "-d", "-s", fallback])
        return fallback, True


def attach_or_create_session(api: TmuxAPI, session_name: str) -> int:
    inside_tmux = bool(api.env.get("TMUX"))
    if api.has_session(session_name):
        if inside_tmux:
            api.switch_client(session_name)
            return 0
        return api.attach_session(session_name)

    if inside_tmux:
        create_rc = api.new_session(session_name, detached=True)
        if create_rc != 0:
            return create_rc
        api.switch_client(session_name)
        return 0
    return api.new_session(session_name, detached=False)


def kill_session_safely(api: TmuxAPI, session_name: str) -> str:
    return kill_sessions_safely(api, [session_name])


def kill_sessions_safely(api: TmuxAPI, session_names: list[str]) -> str:
    targets = []
    seen: set[str] = set()
    for name in session_names:
        if name in seen:
            continue
        seen.add(name)
        targets.append(name)
    if not targets:
        raise TmuxError("No sessions selected")
    for name in targets:
        if not api.has_session(name):
            raise TmuxError(f"No such session: {name}")

    sessions = api.list_sessions()
    fallback = next((session.name for session in sessions if session.name not in seen), "")
    if not fallback:
        fallback, _created = api.fallback_session(targets[0])

    for name in targets:
        for client_tty in api.list_client_ttys(name):
            api.switch_client(fallback, client_tty=client_tty)
    for name in targets:
        api.kill_session(name)
    return fallback
