from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


class TmuxError(RuntimeError):
    """Raised when a tmux command fails."""


INDEX_SESSION_NAME = "index"
INDEX_WINDOW_NAME = "index"
LIST_SESSIONS_FORMAT = "#{session_name}\t#{session_attached}\t#{session_windows}\t#{session_last_attached}"
LIST_WINDOWS_FORMAT = "#{window_index}\t#{window_name}\t#{window_active}\t#{window_layout}"
LIST_PANES_FORMAT = (
    "#{session_name}\t#{window_index}\t#{pane_index}\t#{pane_id}\t#{pane_pid}\t"
    "#{pane_current_command}\t#{pane_current_path}\t#{pane_active}"
)
ROLLOUT_PATH_RE = re.compile(
    r"rollout-.*-(?P<thread_id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$"
)


@dataclass(frozen=True)
class AgentStatus:
    total: int = 0
    working: int = 0
    idle: int = 0


@dataclass(frozen=True)
class Pane:
    session_name: str
    pane_id: str
    pane_pid: int
    current_command: str
    window_index: int = 0
    pane_index: int = 0
    current_path: str = ""
    active: bool = False


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    ppid: int
    comm: str
    args: str


@dataclass(frozen=True)
class Session:
    name: str
    attached: int
    windows: int
    last_attached: int = 0
    agent_total: int = 0
    agent_working: int = 0
    agent_idle: int = 0


@dataclass(frozen=True)
class Window:
    index: int
    name: str
    active: bool
    layout: str


def _is_codex_process(process: ProcessInfo) -> bool:
    return (
        process.comm == "codex"
        or "/bin/codex" in process.args
        or "@openai/codex" in process.args
    )


def _is_tm_browser_process(process: ProcessInfo) -> bool:
    return "main.py p" in process.args or " tm p" in process.args or process.args.endswith("tm p")


def _pane_text_shows_working(text: str) -> bool:
    recent_lines = [line.strip().lower() for line in text.splitlines() if line.strip()][-3:]
    return any("working (" in line or "esc to interrupt" in line for line in recent_lines)


def _tmux_server_missing(text: str) -> bool:
    lowered = text.lower()
    return "no server running" in lowered or "failed to connect to server" in lowered


def _rollout_thread_id_from_lsof_output(output: str) -> str | None:
    for line in output.splitlines():
        match = ROLLOUT_PATH_RE.search(line.strip())
        if match:
            return match.group("thread_id")
    return None


class TmuxAPI:
    def __init__(self, env: dict[str, str] | None = None) -> None:
        self.env = os.environ.copy() if env is None else dict(env)

    def default_start_directory(self) -> str:
        return self.env.get("HOME") or str(Path.home())

    def current_client_tty(self) -> str | None:
        client_tty = (self.env.get("TMUX_CLIENT_TTY") or "").strip()
        return client_tty or None

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

    def list_sessions(self, allow_missing_server: bool = False) -> list[Session]:
        proc = self._run(
            [
                "list-sessions",
                "-F",
                LIST_SESSIONS_FORMAT,
            ],
            check=False,
        )
        if proc.returncode != 0:
            message = (proc.stderr or proc.stdout).strip() or "tmux command failed"
            if allow_missing_server and _tmux_server_missing(message):
                return []
            raise TmuxError(message)
        sessions: list[Session] = []
        for line in proc.stdout.splitlines():
            name, attached, windows, last_attached = (line.split("\t") + ["0", "0", "0"])[:4]
            sessions.append(
                Session(
                    name=name,
                    attached=int(attached),
                    windows=int(windows),
                    last_attached=int(last_attached or 0),
                )
            )
        return sorted(sessions, key=lambda session: session.last_attached, reverse=True)

    def list_windows(self, session_name: str) -> list[Window]:
        proc = self._run(["list-windows", "-t", session_name, "-F", LIST_WINDOWS_FORMAT])
        windows: list[Window] = []
        for line in proc.stdout.splitlines():
            index, name, active, layout = (line.split("\t") + ["0", "", "0", ""])[:4]
            windows.append(
                Window(
                    index=int(index or 0),
                    name=name,
                    active=bool(int(active or 0)),
                    layout=layout,
                )
            )
        return sorted(windows, key=lambda window: window.index)

    def list_panes(self, target: str | None = None) -> list[Pane]:
        args = ["list-panes"]
        if target is None:
            args.append("-a")
        else:
            args.extend(["-t", target])
        args.extend(["-F", LIST_PANES_FORMAT])
        proc = self._run(args)
        panes: list[Pane] = []
        for line in proc.stdout.splitlines():
            session_name, window_index, pane_index, pane_id, pane_pid, current_command, current_path, active = (
                line.split("\t") + ["", "0", "0", "", "0", "", "", "0"]
            )[:8]
            panes.append(
                Pane(
                    session_name=session_name,
                    pane_id=pane_id,
                    pane_pid=int(pane_pid or 0),
                    current_command=current_command,
                    window_index=int(window_index or 0),
                    pane_index=int(pane_index or 0),
                    current_path=current_path,
                    active=bool(int(active or 0)),
                )
            )
        return sorted(panes, key=lambda pane: (pane.session_name, pane.window_index, pane.pane_index))

    def capture_pane_tail(self, pane_id: str, lines: int = 40) -> str:
        proc = self._run(["capture-pane", "-p", "-t", pane_id, "-S", f"-{lines}"], check=False)
        if proc.returncode != 0:
            return ""
        return proc.stdout

    def _process_snapshot(self) -> dict[int, ProcessInfo]:
        proc = subprocess.run(
            ["ps", "-eo", "pid=,ppid=,comm=,args="],
            capture_output=True,
            text=True,
            check=False,
            env=self.env,
        )
        if proc.returncode != 0:
            return {}
        snapshot: dict[int, ProcessInfo] = {}
        for line in proc.stdout.splitlines():
            parts = line.split(None, 3)
            if len(parts) < 3:
                continue
            pid_text, ppid_text, comm = parts[:3]
            args = parts[3] if len(parts) == 4 else comm
            try:
                pid = int(pid_text)
                ppid = int(ppid_text)
            except ValueError:
                continue
            snapshot[pid] = ProcessInfo(pid=pid, ppid=ppid, comm=comm, args=args)
        return snapshot

    def process_tree(
        self,
    ) -> tuple[dict[int, ProcessInfo], dict[int, list[int]]]:
        processes = self._process_snapshot()
        children_by_pid: dict[int, list[int]] = {}
        for process in processes.values():
            children_by_pid.setdefault(process.ppid, []).append(process.pid)
        return processes, children_by_pid

    def pane_codex_process_pid(
        self,
        pane: Pane,
        processes: dict[int, ProcessInfo],
        children_by_pid: dict[int, list[int]],
    ) -> int | None:
        if pane.pane_pid <= 0:
            return None
        stack = [pane.pane_pid]
        seen: set[int] = set()
        while stack:
            pid = stack.pop()
            if pid in seen:
                continue
            seen.add(pid)
            process = processes.get(pid)
            if process is not None and _is_codex_process(process):
                return pid
            stack.extend(children_by_pid.get(pid, []))
        return None

    def pane_has_browser_process(
        self,
        pane: Pane,
        processes: dict[int, ProcessInfo],
        children_by_pid: dict[int, list[int]],
    ) -> bool:
        if pane.pane_pid <= 0:
            return False
        stack = [pane.pane_pid]
        seen: set[int] = set()
        while stack:
            pid = stack.pop()
            if pid in seen:
                continue
            seen.add(pid)
            process = processes.get(pid)
            if process is not None and _is_tm_browser_process(process):
                return True
            stack.extend(children_by_pid.get(pid, []))
        return False

    def pane_codex_thread_id(
        self,
        pane: Pane,
        processes: dict[int, ProcessInfo] | None = None,
        children_by_pid: dict[int, list[int]] | None = None,
    ) -> str | None:
        if processes is None or children_by_pid is None:
            processes, children_by_pid = self.process_tree()
        codex_pid = self.pane_codex_process_pid(pane, processes, children_by_pid)
        if codex_pid is None:
            return None
        try:
            proc = subprocess.run(
                ["lsof", "-p", str(codex_pid)],
                capture_output=True,
                text=True,
                check=False,
                env=self.env,
            )
        except FileNotFoundError:
            return None
        if proc.returncode != 0:
            return None
        return _rollout_thread_id_from_lsof_output(proc.stdout)

    def list_session_agent_statuses(self) -> dict[str, AgentStatus]:
        panes = self.list_panes()
        processes, children_by_pid = self.process_tree()

        statuses: dict[str, AgentStatus] = {}
        for pane in panes:
            if self.pane_codex_process_pid(pane, processes, children_by_pid) is None:
                continue
            current = statuses.get(pane.session_name, AgentStatus())
            is_working = _pane_text_shows_working(self.capture_pane_tail(pane.pane_id))
            statuses[pane.session_name] = AgentStatus(
                total=current.total + 1,
                working=current.working + int(is_working),
                idle=current.idle + int(not is_working),
            )
        return statuses

    def list_client_ttys(self, session_name: str) -> list[str]:
        proc = self._run(["list-clients", "-t", session_name, "-F", "#{client_tty}"], check=False)
        if proc.returncode != 0:
            return []
        return [line.strip() for line in proc.stdout.splitlines() if line.strip()]

    def has_window(self, session_name: str, window_name: str) -> bool:
        return (
            self._run(
                ["display-message", "-p", "-t", f"{session_name}:{window_name}", "#{window_id}"],
                check=False,
            ).returncode
            == 0
        )

    def switch_client(self, target_session: str, client_tty: str | None = None) -> None:
        args = ["switch-client"]
        if client_tty:
            args.extend(["-c", client_tty])
        args.extend(["-t", target_session])
        self._run(args)

    def attach_session(self, session_name: str) -> int:
        return self._run(["attach-session", "-t", session_name], check=False).returncode

    def new_session(
        self,
        session_name: str,
        detached: bool = False,
        start_directory: str | None = None,
        window_name: str | None = None,
        command: str | None = None,
    ) -> int:
        args = ["new-session"]
        if detached:
            args.append("-d")
        args.extend(["-c", start_directory or self.default_start_directory(), "-s", session_name])
        if window_name:
            args.extend(["-n", window_name])
        if command:
            args.append(command)
        return self._run(args, check=False).returncode

    def new_window(
        self,
        session_name: str,
        window_name: str,
        start_directory: str | None = None,
        command: str | None = None,
    ) -> int:
        args = ["new-window", "-d", "-t", session_name, "-n", window_name]
        args.extend(["-c", start_directory or self.default_start_directory()])
        if command:
            args.append(command)
        return self._run(args, check=False).returncode

    def split_window(
        self,
        target: str,
        start_directory: str | None = None,
        command: str | None = None,
    ) -> int:
        args = ["split-window", "-d", "-t", target]
        args.extend(["-c", start_directory or self.default_start_directory()])
        if command:
            args.append(command)
        return self._run(args, check=False).returncode

    def respawn_pane(self, target: str, command: str) -> int:
        return self._run(["respawn-pane", "-k", "-t", target, command], check=False).returncode

    def select_layout(self, target: str, layout: str) -> None:
        self._run(["select-layout", "-t", target, layout])

    def select_window(self, target: str) -> None:
        self._run(["select-window", "-t", target])

    def select_pane(self, target: str) -> None:
        self._run(["select-pane", "-t", target])

    def kill_session(self, session_name: str) -> None:
        self._run(["kill-session", "-t", session_name])

    def fallback_session(self, target_session: str) -> tuple[str, bool]:
        for session in self.list_sessions():
            if session.name != target_session:
                return session.name, False
        fallback = f"__tmp_{int(time.time())}"
        self._run(["new-session", "-d", "-c", self.default_start_directory(), "-s", fallback])
        return fallback, True


def ensure_session_exists(api: TmuxAPI, session_name: str, detached: bool = True) -> bool:
    if api.has_session(session_name):
        return False
    rc = api.new_session(session_name, detached=detached)
    if rc != 0:
        raise TmuxError(f"Unable to create session: {session_name}")
    return True


def index_browser_command() -> str:
    entrypoint = Path(__file__).resolve().with_name("main.py")
    if sys.executable:
        interpreter = shlex.quote(sys.executable)
        return f"{interpreter} {shlex.quote(str(entrypoint))} p"
    return f"/usr/bin/env python3 {shlex.quote(str(entrypoint))} p"


def ensure_index_session(api: TmuxAPI) -> bool:
    browser_command = index_browser_command()
    if not api.has_session(INDEX_SESSION_NAME):
        rc = api.new_session(
            INDEX_SESSION_NAME,
            detached=True,
            window_name=INDEX_WINDOW_NAME,
            command=browser_command,
        )
        if rc != 0:
            raise TmuxError(f"Unable to create session: {INDEX_SESSION_NAME}")
        return True
    if not api.has_window(INDEX_SESSION_NAME, INDEX_WINDOW_NAME):
        rc = api.new_window(
            INDEX_SESSION_NAME,
            INDEX_WINDOW_NAME,
            command=browser_command,
        )
        if rc != 0:
            raise TmuxError(f"Unable to create session: {INDEX_SESSION_NAME}")
        return True

    panes = api.list_panes(f"{INDEX_SESSION_NAME}:{INDEX_WINDOW_NAME}")
    processes, children_by_pid = api.process_tree()
    if any(
        api.pane_has_browser_process(pane, processes, children_by_pid)
        for pane in panes
    ):
        return False

    target_pane = panes[0].pane_id if panes else f"{INDEX_SESSION_NAME}:{INDEX_WINDOW_NAME}.0"
    rc = api.respawn_pane(target_pane, browser_command)
    if rc != 0:
        raise TmuxError(f"Unable to create session: {INDEX_SESSION_NAME}")
    return True


def attach_or_create_session(api: TmuxAPI, session_name: str) -> int:
    if session_name == INDEX_SESSION_NAME:
        ensure_index_session(api)
    inside_tmux = bool(api.env.get("TMUX"))
    client_tty = api.current_client_tty()
    if api.has_session(session_name):
        if inside_tmux:
            api.switch_client(session_name, client_tty=client_tty)
            return 0
        return api.attach_session(session_name)

    if inside_tmux:
        create_rc = api.new_session(session_name, detached=True)
        if create_rc != 0:
            return create_rc
        api.switch_client(session_name, client_tty=client_tty)
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
    if INDEX_SESSION_NAME in seen:
        raise TmuxError(f"Cannot kill managed session: {INDEX_SESSION_NAME}")
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
