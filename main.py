#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from _version import __version__
from session_tui import browse_sessions
from tmux_api import TmuxAPI, TmuxError, attach_or_create_session, ensure_index_session

ANSI_GRAY = "\033[38;5;245m"
ANSI_RESET = "\033[0m"
APP_DIR = Path(__file__).resolve().parent
INSTALL_SCRIPT = APP_DIR / "install.sh"
HELP_TEXT = """tm

flags:
  tm -h
    show this help
  tm -v
    print the installed version
  tm -u
    upgrade to the latest release

features:
  open the tmux session browser
  # tm
  tm

  open the tmux session browser in persistent mode inside tmux
  # tm p
  tm p

  attach to a named session, or create it first if needed
  # tm s <session_name>
  tm s root

  inside the browser, create a new named session
  # n
  n
"""


class UsageError(ValueError):
    """Raised for invalid CLI usage."""


def muted(text: str) -> str:
    if not sys.stdout.isatty() or "NO_COLOR" in os.environ:
        return text
    return f"{ANSI_GRAY}{text}{ANSI_RESET}"


def print_help() -> None:
    print(muted(HELP_TEXT.rstrip()))


def upgrade_app() -> int:
    if not INSTALL_SCRIPT.exists():
        print("install.sh is missing", file=sys.stderr)
        return 1
    proc = subprocess.run(
        ["/usr/bin/env", "bash", str(INSTALL_SCRIPT), "-u"],
        check=False,
        text=True,
        env=os.environ.copy(),
    )
    return proc.returncode


def parse_args(argv: Sequence[str]) -> tuple[str, str | None]:
    args = list(argv)
    if not args:
        return "browse", None
    if args == ["-h"]:
        return "help", None
    if args == ["-v"]:
        return "version", None
    if args == ["-u"]:
        return "upgrade", None
    if args == ["p"]:
        return "persistent", None
    if len(args) == 2 and args[0] == "s" and not args[1].startswith("-"):
        return "session", args[1]
    raise UsageError("Usage: tm | tm p | tm s <session_name> | tm -h | tm -v | tm -u")


def main(argv: Sequence[str] | None = None, api: TmuxAPI | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    api = TmuxAPI() if api is None else api
    try:
        command, value = parse_args(argv)
        if command == "help":
            print_help()
            return 0
        if command == "version":
            print(__version__)
            return 0
        if command == "upgrade":
            return upgrade_app()
        if command == "persistent":
            return browse_sessions(api, persistent=True)
        if command == "session":
            assert value is not None
            ensure_index_session(api)
            return attach_or_create_session(api, value)
        return browse_sessions(api)
    except UsageError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except TmuxError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
