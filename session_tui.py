from __future__ import annotations

import curses
from dataclasses import dataclass, field

from tmux_api import Session, TmuxAPI, TmuxError, kill_sessions_safely


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
    "?",
    "  toggle this help",
    "q",
    "  quit",
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
    prompt_active: bool = False
    prompt_buffer: str = ""
    prompt_label: str = ""

    def current_name(self) -> str | None:
        if not self.sessions:
            return None
        return self.sessions[self.index].name

    def move(self, delta: int) -> None:
        if not self.sessions:
            return
        self.index = max(0, min(self.index + delta, len(self.sessions) - 1))

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

    def begin_prompt(self, label: str) -> None:
        self.prompt_active = True
        self.prompt_label = label
        self.prompt_buffer = ""
        self.status_message = ""

    def end_prompt(self, message: str = "") -> None:
        self.prompt_active = False
        self.prompt_label = ""
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

    def status_line(self) -> str:
        parts = [f"{len(self.sessions)} session(s)"]
        if self.marked:
            parts.append(f"{len(self.marked)} marked")
        if self.visual_mode:
            parts.append(f"{len(self.visual_indexes())} visual")
        if self.status_message:
            parts.append(self.status_message)
        return "  ".join(parts)


def _setup_curses(stdscr: curses.window) -> None:
    curses.curs_set(0)
    stdscr.keypad(True)
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
        line, attrs = _format_session_row(
            session.name,
            is_current=is_current,
            is_marked=is_marked,
            is_visual=is_visual,
            attached=bool(session.attached),
        )
        stdscr.addnstr(row, 0, line, width - 1, attrs)

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
) -> tuple[str, int]:
    cursor = ">" if is_current else " "
    mark = "*" if is_marked else " "
    visual = "+" if is_visual else " "
    attached_suffix = " (attached)" if attached else ""
    line = f"{cursor}{mark}{visual} {session_name}{attached_suffix}"

    attrs = curses.A_BOLD if is_current else curses.A_NORMAL
    if is_visual:
        attrs |= curses.A_REVERSE
    return line, attrs


def _refresh_sessions(
    api: TmuxAPI, state: SessionBrowserState, preferred: str | None = None
) -> None:
    state.sync_sessions(api.list_sessions(), preferred=preferred)


def _create_session(api: TmuxAPI, state: SessionBrowserState, session_name: str) -> None:
    if not session_name:
        state.end_prompt("Empty session name")
        return
    if api.has_session(session_name):
        state.end_prompt(f"Session exists: {session_name}")
        return
    rc = api.new_session(session_name, detached=True)
    if rc != 0:
        raise TmuxError(f"Unable to create session: {session_name}")
    _refresh_sessions(api, state, preferred=session_name)
    state.end_prompt(f"Created {session_name}")


def _enter_session(api: TmuxAPI, state: SessionBrowserState) -> int:
    current = state.current_name()
    if current is None:
        state.status_message = "No session selected"
        return 0
    if api.env.get("TMUX"):
        api.switch_client(current)
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
        return "create", value
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


def _handle_normal_key(state: SessionBrowserState, key: int) -> tuple[str | None, str | None]:
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
        return "prompt", "New session: "
    if 32 <= key <= 126:
        state.status_message = "Unknown command"
        return None, None
    return None, None


def browse_sessions(api: TmuxAPI) -> int:
    state = SessionBrowserState(sessions=api.list_sessions())

    def _run(stdscr: curses.window) -> int:
        _setup_curses(stdscr)
        while True:
            if state.show_help:
                _draw_help(stdscr, state)
                _handle_help_key(state, stdscr.getch(), stdscr.getmaxyx()[0])
                continue

            _draw_sessions(stdscr, state)
            key = stdscr.getch()

            if state.prompt_active:
                action, value = _handle_prompt_key(state, key)
                if action == "create" and value is not None:
                    _create_session(api, state, value)
                continue

            action, value = _handle_normal_key(state, key)
            if action == "quit":
                return 0
            if action == "prompt" and value is not None:
                state.begin_prompt(value)
                continue
            if action == "enter":
                return _enter_session(api, state)
            if action == "kill":
                _kill_selected(api, state)

    return curses.wrapper(_run)
