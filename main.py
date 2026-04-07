#!/usr/bin/env python3
from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from _version import __version__
from rgw_cli_contract import AppSpec, resolve_install_script_path, run_app
from snapshot_state import SnapshotError, restore_saved_sessions_if_needed
from session_tui import browse_sessions
from tmux_api import (
    INDEX_SESSION_NAME,
    TmuxAPI,
    TmuxError,
    attach_or_create_session,
    ensure_index_session,
    reload_managed_config,
)

APP_DIR = Path(__file__).resolve().parent
INSTALL_SCRIPT = resolve_install_script_path(__file__)
HELP_TEXT = """tm

flags:
  tm
    show this help
  tm -h
    show this help
  tm -v
    print the installed version
  tm -u
    upgrade to the latest release

commands:
  switch to the managed index session running the persistent browser
  # tm index
  tm index

  clean tm-managed bindings from the live tmux server and reapply them
  # tm reload
  tm reload

  attach to a named session, or create it first if needed
  # tm s <session_name>
  tm s root

  inside the browser, create or rename a named session
  # n | ,rn
  n
"""


class UsageError(ValueError):
    """Raised for invalid CLI usage."""


def parse_args(argv: Sequence[str]) -> tuple[str, str | None]:
    args = list(argv)
    if args == ["index"]:
        return "index", None
    if args == ["reload"]:
        return "reload", None
    if args == ["p"]:
        return "persistent", None
    if len(args) == 2 and args[0] == "s" and not args[1].startswith("-"):
        return "session", args[1]
    raise UsageError("Usage: tm index | tm reload | tm s <session_name>")


def _should_prepare_tmux(argv: Sequence[str]) -> bool:
    args = list(argv)
    if not args or args in (["-h"], ["-v"], ["-u"], ["conf"]):
        return False
    try:
        command, _value = parse_args(args)
    except UsageError:
        return False
    return command in {"index", "persistent", "session"}


def _dispatch(argv: list[str], api: TmuxAPI | None = None) -> int:
    api = TmuxAPI() if api is None else api
    try:
        command, value = parse_args(argv)
        if command == "index":
            return attach_or_create_session(api, INDEX_SESSION_NAME)
        if command == "reload":
            reload_managed_config(api)
            return 0
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
    no_args_mode="help",
)


def main(argv: Sequence[str] | None = None, api: TmuxAPI | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    active_api = TmuxAPI() if api is None else api
    if _should_prepare_tmux(args):
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
