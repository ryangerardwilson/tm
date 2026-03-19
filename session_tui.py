from __future__ import annotations

import curses
import time
from dataclasses import dataclass, field, replace

from snapshot_state import SNAPSHOT_INTERVAL_SECONDS, SnapshotError, write_runtime_snapshot
from tmux_api import (
    INDEX_SESSION_NAME,
    AgentStatus,
    Session,
    TmuxAPI,
    TmuxError,
    ensure_index_session,
    kill_sessions_safely,
)


HELP_LINES = [
    "tm",
    "",
    "j / k or arrows",
    "  move",
    "l",
    "  switch to the current session",
    "m",
    "  mark or unmark the current session",
    "v",
    "  toggle visual mode for a contiguous selection",
    "x",
    "  kill the current session, marked sessions, or visual selection",
    "n",
    "  create a new named session",
    ",rn",
    "  rename the current session",
    "?",
    "  toggle this help",
    "q",
    "  quit",
]

ANIMATION_TIMEOUT_MS = 60
AGENT_STATUS_REFRESH_TICKS = 16
LEADER_KEY = ord(",")
LEADER_RENAME_SEQUENCE = "rn"
AGENT_WORKING_FRAMES = [
    " ◐◐◐◐◐◐",
    " ◓◓◓◓◓◓",
    " ◑◑◑◑◑◑",
    " ◒◒◒◒◒◒",
    " ◐◓◑◒◐◓",
    " ◓◑◒◐◓◑",
    " ◑◒◐◓◑◒",
    " ◒◐◓◑◒◐",
]


@dataclass
class SessionBrowserState:
    sessions: list[Session]
    index: int = 0
    marked: set[str] = field(default_factory=set)
    visual_mode: bool = False
    visual_anchor: int | None = None
    show_help: bool = False
    help_scroll: int = 0
    status_message: str = ""
    leader_active: bool = False
    leader_buffer: str = ""
    prompt_active: bool = False
    prompt_buffer: str = ""
    prompt_label: str = ""
    prompt_action: str = ""
    animation_step: int = 0
    agent_refresh_tick: int = 0

    def current_name(self) -> str | None:
        if not self.sessions:
            return None
        return self.sessions[self.index].name

    def move(self, delta: int) -> None:
        if not self.sessions:
            return
        self.index = (self.index + delta) % len(self.sessions)

    def visual_indexes(self) -> set[int]:
        if not self.visual_mode or self.visual_anchor is None:
            return set()
        start = min(self.visual_anchor, self.index)
        end = max(self.visual_anchor, self.index)
        return set(range(start, end + 1))

    def selected_names(self) -> list[str]:
        if self.visual_mode:
            return [self.sessions[idx].name for idx in sorted(self.visual_indexes())]
        if self.marked:
            return [session.name for session in self.sessions if session.name in self.marked]
        current = self.current_name()
        return [current] if current else []

    def toggle_mark(self) -> None:
        current = self.current_name()
        if current is None:
            return
        if current in self.marked:
            self.marked.remove(current)
        else:
            self.marked.add(current)
        if self.index < len(self.sessions) - 1:
            self.index += 1

    def toggle_visual(self) -> None:
        if self.visual_mode:
            self.visual_mode = False
            self.visual_anchor = None
            return
        if not self.sessions:
            return
        self.visual_mode = True
        self.visual_anchor = self.index

    def reset_visual(self) -> None:
        self.visual_mode = False
        self.visual_anchor = None

    def begin_leader(self) -> None:
        self.leader_active = True
        self.leader_buffer = ""
        self.status_message = ""

    def reset_leader(self, message: str = "") -> None:
        self.leader_active = False
        self.leader_buffer = ""
        if message:
            self.status_message = message

    def begin_prompt(self, label: str, action: str, initial_value: str = "") -> None:
        self.reset_leader()
        self.prompt_active = True
        self.prompt_label = label
        self.prompt_action = action
        self.prompt_buffer = initial_value
        self.status_message = ""

    def end_prompt(self, message: str = "") -> None:
        self.prompt_active = False
        self.prompt_label = ""
        self.prompt_action = ""
        self.prompt_buffer = ""
        self.status_message = message

    def sync_sessions(self, sessions: list[Session], preferred: str | None = None) -> None:
        self.sessions = sessions
        names = {session.name for session in sessions}
        self.marked.intersection_update(names)
        if self.visual_mode and self.visual_anchor is not None:
            if not sessions:
                self.reset_visual()
            else:
                self.visual_anchor = max(0, min(self.visual_anchor, len(sessions) - 1))
        if not sessions:
            self.index = 0
            self.reset_visual()
            return
        target = preferred or self.current_name()
        if target and target in names:
            self.index = next(i for i, session in enumerate(sessions) if session.name == target)
        else:
            self.index = max(0, min(self.index, len(sessions) - 1))

    def sync_agent_statuses(self, statuses: dict[str, AgentStatus]) -> None:
        default = AgentStatus()
        self.sessions = [
            replace(
                session,
                agent_total=statuses.get(session.name, default).total,
                agent_working=statuses.get(session.name, default).working,
                agent_idle=statuses.get(session.name, default).idle,
            )
            for session in self.sessions
        ]

    def status_line(self) -> str:
        parts = [f"{len(self.sessions)} session(s)"]
        if self.marked:
            parts.append(f"{len(self.marked)} marked")
        if self.visual_mode:
            parts.append(f"{len(self.visual_indexes())} visual")
        if self.leader_active:
            parts.append(f",{self.leader_buffer}")
        if self.status_message:
            parts.append(self.status_message)
        return "  ".join(parts)


def _setup_curses(stdscr: curses.window) -> None:
    curses.curs_set(0)
    stdscr.keypad(True)
    stdscr.timeout(ANIMATION_TIMEOUT_MS)
    try:
        curses.noecho()
        curses.raw()
        curses.nonl()
    except curses.error:
        pass
    try:
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, -1, -1)
        stdscr.bkgd(" ", curses.color_pair(1))
    except curses.error:
        pass


def _draw_help(stdscr: curses.window, state: SessionBrowserState) -> None:
    stdscr.erase()
    height, width = stdscr.getmaxyx()
    stdscr.addnstr(0, 0, "tm", width - 1, curses.A_BOLD)
    max_visible = max(1, height - 2)
    start = min(state.help_scroll, max(0, len(HELP_LINES) - max_visible))
    for row, line in enumerate(HELP_LINES[start : start + max_visible], start=1):
        stdscr.addnstr(row, 0, line, width - 1)
    stdscr.addnstr(height - 1, 0, "? close", width - 1)
    stdscr.refresh()


def _draw_sessions(stdscr: curses.window, state: SessionBrowserState) -> None:
    stdscr.erase()
    height, width = stdscr.getmaxyx()
    stdscr.addnstr(0, 0, "tm", width - 1, curses.A_BOLD)

    start_row = 2
    visible = max(1, height - start_row - 2)
    top = min(max(state.index - visible + 1, 0), max(len(state.sessions) - visible, 0))
    visual_indexes = state.visual_indexes()

    if not state.sessions:
        stdscr.addnstr(start_row, 0, "No tmux sessions", width - 1)

    for offset, session in enumerate(state.sessions[top : top + visible]):
        row = start_row + offset
        session_index = top + offset
        is_current = session_index == state.index
        is_marked = session.name in state.marked
        is_visual = session_index in visual_indexes
        line, agent_suffix, attrs = _format_session_row(
            session.name,
            is_current=is_current,
            is_marked=is_marked,
            is_visual=is_visual,
            attached=bool(session.attached),
            agent_total=session.agent_total,
            agent_working=session.agent_working,
            agent_idle=session.agent_idle,
            animation_step=state.animation_step,
        )
        base_line, suffix_line = _fit_row_segments(line, agent_suffix, width - 1)
        stdscr.addnstr(row, 0, base_line, width - 1, attrs)
        if suffix_line and len(base_line) < width - 1:
            stdscr.addnstr(
                row,
                len(base_line),
                suffix_line,
                width - 1 - len(base_line),
                attrs,
            )

    if state.prompt_active:
        prompt = f"{state.prompt_label}{state.prompt_buffer}"
        stdscr.addnstr(height - 1, 0, prompt, width - 1)
    else:
        stdscr.addnstr(height - 1, 0, state.status_line(), width - 1)
    stdscr.refresh()


def _format_session_row(
    session_name: str,
    *,
    is_current: bool,
    is_marked: bool,
    is_visual: bool,
    attached: bool,
    agent_total: int = 0,
    agent_working: int = 0,
    agent_idle: int = 0,
    animation_step: int = 0,
) -> tuple[str, str, int]:
    cursor = ">" if is_current else " "
    mark = "*" if is_marked else " "
    visual = "+" if is_visual else " "
    attached_suffix = " (attached)" if attached else ""
    agent_suffix = ""
    if agent_working:
        agent_suffix = _agent_working_frame(animation_step)
    line = f"{cursor}{mark}{visual} {session_name}{attached_suffix}"

    attrs = curses.A_BOLD if is_current else curses.A_NORMAL
    if is_visual:
        attrs |= curses.A_REVERSE
    return line, agent_suffix, attrs


def _agent_working_frame(animation_step: int) -> str:
    return AGENT_WORKING_FRAMES[animation_step % len(AGENT_WORKING_FRAMES)]


def _fit_row_segments(base_line: str, agent_suffix: str, width: int) -> tuple[str, str]:
    if width <= 0:
        return "", ""
    if not agent_suffix:
        return _truncate_text(base_line, width), ""

    suffix_line = agent_suffix[:width]
    if len(suffix_line) >= width:
        return "", suffix_line
    return _truncate_text(base_line, width - len(suffix_line)), suffix_line


def _truncate_text(text: str, width: int) -> str:
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    return f"{text[: width - 3]}..."


def _refresh_sessions(
    api: TmuxAPI, state: SessionBrowserState, preferred: str | None = None
) -> None:
    ensure_index_session(api)
    state.sync_sessions(_visible_sessions(api.list_sessions()), preferred=preferred)
    _refresh_agent_statuses(api, state)


def _refresh_agent_statuses(api: TmuxAPI, state: SessionBrowserState) -> None:
    state.sync_agent_statuses(api.list_session_agent_statuses())


def _visible_sessions(sessions: list[Session]) -> list[Session]:
    return [session for session in sessions if session.name != INDEX_SESSION_NAME]


def _session_name_validation_error(api: TmuxAPI, session_name: str) -> str | None:
    if session_name == INDEX_SESSION_NAME:
        return f"Reserved session: {session_name}"
    if api.has_session(session_name):
        return f"Session exists: {session_name}"
    return None


def _create_session(api: TmuxAPI, state: SessionBrowserState, session_name: str) -> None:
    if not session_name:
        state.end_prompt("Empty session name")
        return
    validation_error = _session_name_validation_error(api, session_name)
    if validation_error:
        state.end_prompt(validation_error)
        return
    rc = api.new_session(session_name, detached=True)
    if rc != 0:
        raise TmuxError(f"Unable to create session: {session_name}")
    _refresh_sessions(api, state, preferred=session_name)
    _save_snapshot_now(api, state)
    state.end_prompt(f"Created {session_name}")


def _rename_selected_session(api: TmuxAPI, state: SessionBrowserState, session_name: str) -> None:
    current = state.current_name()
    if current is None:
        state.end_prompt("No session selected")
        return
    if not session_name:
        state.end_prompt("Empty session name")
        return
    if session_name == current:
        state.end_prompt("Name unchanged")
        return
    validation_error = _session_name_validation_error(api, session_name)
    if validation_error:
        state.end_prompt(validation_error)
        return

    was_marked = current in state.marked
    api.rename_session(current, session_name)
    if was_marked:
        state.marked.remove(current)
        state.marked.add(session_name)
    _refresh_sessions(api, state, preferred=session_name)
    _save_snapshot_now(api, state)
    state.end_prompt(f"Renamed {current} to {session_name}")


def _enter_session(api: TmuxAPI, state: SessionBrowserState, persistent: bool = False) -> int | None:
    current = state.current_name()
    if current is None:
        state.status_message = "No session selected"
        return 0
    if api.env.get("TMUX"):
        api.switch_client(current)
        if persistent:
            _refresh_sessions(api, state, preferred=current)
            state.status_message = f"Switched to {current}"
            return None
        return 0
    return api.attach_session(current)


def _kill_selected(api: TmuxAPI, state: SessionBrowserState) -> None:
    targets = state.selected_names()
    if not targets:
        state.status_message = "No session selected"
        return
    preferred = next(
        (session.name for session in state.sessions if session.name not in set(targets)),
        None,
    )
    kill_sessions_safely(api, targets)
    _refresh_sessions(api, state, preferred=preferred)
    _save_snapshot_now(api, state)
    state.reset_visual()
    state.marked.clear()
    if len(targets) == 1:
        state.status_message = f"Killed {targets[0]}"
    else:
        state.status_message = f"Killed {len(targets)} sessions"


def _handle_prompt_key(
    state: SessionBrowserState, key: int
) -> tuple[str | None, str | None]:
    if key in (27,):
        state.end_prompt("Cancelled")
        return None, None
    if key in (10, 13, curses.KEY_ENTER):
        value = state.prompt_buffer.strip()
        return state.prompt_action, value
    if key in (curses.KEY_BACKSPACE, 127, 8):
        state.prompt_buffer = state.prompt_buffer[:-1]
        return None, None
    if 32 <= key <= 126:
        state.prompt_buffer += chr(key)
    return None, None


def _handle_help_key(state: SessionBrowserState, key: int, max_y: int) -> None:
    max_visible = max(1, max_y - 2)
    max_scroll = max(0, len(HELP_LINES) - max_visible)
    if key in (ord("?"), 27, ord("q")):
        state.show_help = False
        state.help_scroll = 0
        return
    if key in (curses.KEY_UP, ord("k")):
        state.help_scroll = max(0, state.help_scroll - 1)
        return
    if key in (curses.KEY_DOWN, ord("j")):
        state.help_scroll = min(max_scroll, state.help_scroll + 1)


def _handle_leader_key(state: SessionBrowserState, key: int) -> tuple[str | None, str | None]:
    if key in (27,):
        state.reset_leader("Cancelled")
        return None, None
    if not 32 <= key <= 126:
        state.reset_leader("Unknown command")
        return None, None

    state.leader_buffer += chr(key)
    if LEADER_RENAME_SEQUENCE.startswith(state.leader_buffer):
        if state.leader_buffer == LEADER_RENAME_SEQUENCE:
            current = state.current_name()
            state.reset_leader()
            if current is None:
                state.status_message = "No session selected"
                return None, None
            return "prompt-rename", current
        return None, None

    state.reset_leader("Unknown command")
    return None, None


def _handle_normal_key(state: SessionBrowserState, key: int) -> tuple[str | None, str | None]:
    if state.leader_active:
        return _handle_leader_key(state, key)
    if key == ord("?"):
        state.show_help = True
        state.help_scroll = 0
        return None, None
    if key in (ord("q"), 27):
        return "quit", None
    if key in (curses.KEY_DOWN, ord("j")):
        state.move(1)
        return None, None
    if key in (curses.KEY_UP, ord("k")):
        state.move(-1)
        return None, None
    if key == ord("l"):
        return "enter", None
    if key == ord("m"):
        state.toggle_mark()
        return None, None
    if key == ord("v"):
        state.toggle_visual()
        return None, None
    if key == ord("x"):
        return "kill", None
    if key == ord("n"):
        return "prompt-create", None
    if key == LEADER_KEY:
        state.begin_leader()
        return None, None
    if 32 <= key <= 126:
        state.status_message = "Unknown command"
        return None, None
    return None, None


def _save_snapshot_now(api: TmuxAPI, state: SessionBrowserState) -> None:
    try:
        write_runtime_snapshot(api)
    except (SnapshotError, TmuxError) as exc:
        state.status_message = str(exc)


def _maybe_write_hourly_snapshot(
    api: TmuxAPI,
    state: SessionBrowserState,
    persistent: bool,
    last_snapshot_at: float | None,
    now: float | None = None,
) -> float | None:
    if not persistent:
        return last_snapshot_at
    current_time = time.monotonic() if now is None else now
    if last_snapshot_at is not None and current_time - last_snapshot_at < SNAPSHOT_INTERVAL_SECONDS:
        return last_snapshot_at
    _save_snapshot_now(api, state)
    return current_time


def browse_sessions(api: TmuxAPI, persistent: bool = False) -> int:
    ensure_index_session(api)
    state = SessionBrowserState(sessions=[])
    _refresh_sessions(api, state)

    def _run(stdscr: curses.window) -> int:
        last_snapshot_at: float | None = None
        _setup_curses(stdscr)
        while True:
            last_snapshot_at = _maybe_write_hourly_snapshot(
                api,
                state,
                persistent,
                last_snapshot_at,
            )
            if state.show_help:
                _draw_help(stdscr, state)
                _handle_help_key(state, stdscr.getch(), stdscr.getmaxyx()[0])
                continue

            _draw_sessions(stdscr, state)
            key = stdscr.getch()
            if key == -1:
                state.animation_step = (state.animation_step + 1) % 3
                state.agent_refresh_tick = (
                    state.agent_refresh_tick + 1
                ) % AGENT_STATUS_REFRESH_TICKS
                if state.agent_refresh_tick == 0:
                    _refresh_agent_statuses(api, state)
                continue

            if state.prompt_active:
                action, value = _handle_prompt_key(state, key)
                if action == "create" and value is not None:
                    _create_session(api, state, value)
                if action == "rename" and value is not None:
                    _rename_selected_session(api, state, value)
                continue

            action, value = _handle_normal_key(state, key)
            if action == "quit":
                return 0
            if action == "prompt-create":
                state.begin_prompt("New session: ", action="create")
                continue
            if action == "prompt-rename" and value is not None:
                state.begin_prompt("Rename session: ", action="rename", initial_value=value)
                continue
            if action == "enter":
                rc = _enter_session(api, state, persistent=persistent)
                if rc is not None:
                    return rc
                continue
            if action == "kill":
                _kill_selected(api, state)

    return curses.wrapper(_run)
