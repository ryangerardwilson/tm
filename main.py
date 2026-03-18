#!/usr/bin/env python3
from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from _version import __version__
from rgw_cli_contract import AppSpec, resolve_install_script_path, run_app
from snapshot_state import SnapshotError, restore_saved_sessions_if_needed
from session_tui import browse_sessions
from tmux_api import INDEX_SESSION_NAME, TmuxAPI, TmuxError, attach_or_create_session, ensure_index_session

APP_DIR = Path(__file__).resolve().parent
INSTALL_SCRIPT = resolve_install_script_path(__file__)
HELP_TEXT = """tm

flags:
  tm -h
    show this help
  tm -v
    print the installed version
  tm -u
    upgrade to the latest release

features:
  switch to the managed index session running the persistent browser
  # tm
  tm

  attach to a named session, or create it first if needed
  # tm s <session_name>
  tm s root

  inside the browser, create a new named session
  # n
  n
"""


class UsageError(ValueError):
    """Raised for invalid CLI usage."""


def parse_args(argv: Sequence[str]) -> tuple[str, str | None]:
    args = list(argv)
    if not args:
        return "index", None
    if args == ["p"]:
        return "persistent", None
    if len(args) == 2 and args[0] == "s" and not args[1].startswith("-"):
        return "session", args[1]
    raise UsageError("Usage: tm | tm s <session_name>")


def _dispatch(argv: list[str], api: TmuxAPI | None = None) -> int:
    api = TmuxAPI() if api is None else api
    try:
        command, value = parse_args(argv)
        if command == "index":
            return attach_or_create_session(api, INDEX_SESSION_NAME)
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


APP_SPEC = AppSpec(
    app_name="tm",
    version=__version__,
    help_text=HELP_TEXT,
    install_script_path=INSTALL_SCRIPT,
    no_args_mode="dispatch",
)


def main(argv: Sequence[str] | None = None, api: TmuxAPI | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    active_api = TmuxAPI() if api is None else api
    try:
        ensure_index_session(active_api)
        restore_saved_sessions_if_needed(active_api)
    except TmuxError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except SnapshotError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return run_app(APP_SPEC, args, lambda dispatch_argv: _dispatch(dispatch_argv, active_api))


if __name__ == "__main__":
    raise SystemExit(main())
