from __future__ import annotations

from pathlib import Path

import main


def test_parse_args_help_variants() -> None:
    assert main.parse_args([]) == ("browse", None)
    assert main.parse_args(["p"]) == ("persistent", None)
    assert main.parse_args(["-h"]) == ("help", None)
    assert main.parse_args(["-v"]) == ("version", None)
    assert main.parse_args(["-u"]) == ("upgrade", None)
    assert main.parse_args(["s", "root"]) == ("session", "root")


def test_parse_args_rejects_unknown_shape() -> None:
    try:
        main.parse_args(["-x"])
    except main.UsageError as exc:
        assert str(exc) == "Usage: tm | tm p | tm s <session_name> | tm -h | tm -v | tm -u"
    else:
        raise AssertionError("UsageError not raised")


def test_parse_args_rejects_removed_nav_command() -> None:
    try:
        main.parse_args(["nav"])
    except main.UsageError as exc:
        assert str(exc) == "Usage: tm | tm p | tm s <session_name> | tm -h | tm -v | tm -u"
    else:
        raise AssertionError("UsageError not raised")


def test_main_no_args_opens_browser(monkeypatch) -> None:
    calls: list[object] = []
    ensured: list[object] = []

    class FakeAPI:
        pass

    def fake_browse(api):  # type: ignore[no-untyped-def]
        calls.append(api)
        return 0

    def fake_ensure_index(api):  # type: ignore[no-untyped-def]
        ensured.append(api)
        return True

    api = FakeAPI()
    monkeypatch.setattr(main, "browse_sessions", fake_browse)
    monkeypatch.setattr(main, "ensure_index_session", fake_ensure_index)
    assert main.main([], api=api) == 0
    assert calls == [api]
    assert ensured == []


def test_main_named_session_uses_attach_or_create(monkeypatch) -> None:
    calls: list[tuple[object, str]] = []
    ensured: list[object] = []

    class FakeAPI:
        pass

    def fake_attach_or_create(api, session_name):  # type: ignore[no-untyped-def]
        calls.append((api, session_name))
        return 0

    def fake_ensure_index(api):  # type: ignore[no-untyped-def]
        ensured.append(api)
        return True

    api = FakeAPI()
    monkeypatch.setattr(main, "attach_or_create_session", fake_attach_or_create)
    monkeypatch.setattr(main, "ensure_index_session", fake_ensure_index)
    assert main.main(["s", "root"], api=api) == 0
    assert calls == [(api, "root")]
    assert ensured == [api]


def test_main_persistent_mode_opens_browser_with_flag(monkeypatch) -> None:
    calls: list[tuple[object, bool]] = []

    class FakeAPI:
        pass

    def fake_browse(api, persistent=False):  # type: ignore[no-untyped-def]
        calls.append((api, persistent))
        return 0

    api = FakeAPI()
    monkeypatch.setattr(main, "browse_sessions", fake_browse)
    assert main.main(["p"], api=api) == 0
    assert calls == [(api, True)]


def test_upgrade_app_uses_installer(monkeypatch) -> None:
    calls: list[list[str]] = []

    class Proc:
        returncode = 0

    def fake_run(args, check, text, env):  # type: ignore[no-untyped-def]
        calls.append(args)
        return Proc()

    monkeypatch.setattr(main.subprocess, "run", fake_run)
    rc = main.upgrade_app()
    assert rc == 0
    assert calls == [["/usr/bin/env", "bash", str(Path(main.__file__).resolve().parent / "install.sh"), "-u"]]
