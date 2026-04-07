from __future__ import annotations

from pathlib import Path

import main


def test_parse_args_help_variants() -> None:
    assert main.parse_args(["index"]) == ("index", None)
    assert main.parse_args(["reload"]) == ("reload", None)
    assert main.parse_args(["p"]) == ("persistent", None)
    assert main.parse_args(["s", "root"]) == ("session", "root")


def test_parse_args_rejects_unknown_shape() -> None:
    try:
        main.parse_args(["-x"])
    except main.UsageError as exc:
        assert str(exc) == "Usage: tm index | tm reload | tm s <session_name>"
    else:
        raise AssertionError("UsageError not raised")


def test_parse_args_rejects_removed_nav_command() -> None:
    try:
        main.parse_args(["nav"])
    except main.UsageError as exc:
        assert str(exc) == "Usage: tm index | tm reload | tm s <session_name>"
    else:
        raise AssertionError("UsageError not raised")


def test_main_index_switches_to_index_session(monkeypatch) -> None:
    calls: list[tuple[object, str]] = []
    ensured: list[object] = []
    restored: list[object] = []

    class FakeAPI:
        pass

    def fake_attach_or_create(api, session_name):  # type: ignore[no-untyped-def]
        calls.append((api, session_name))
        return 0

    def fake_ensure_index(api):  # type: ignore[no-untyped-def]
        ensured.append(api)
        return True

    def fake_restore(api):  # type: ignore[no-untyped-def]
        restored.append(api)
        return None

    api = FakeAPI()
    monkeypatch.setattr(main, "attach_or_create_session", fake_attach_or_create)
    monkeypatch.setattr(main, "ensure_index_session", fake_ensure_index)
    monkeypatch.setattr(main, "restore_saved_sessions_if_needed", fake_restore)
    assert main.main(["index"], api=api) == 0
    assert calls == [(api, "index")]
    assert ensured == [api]
    assert restored == [api]


def test_main_named_session_uses_attach_or_create(monkeypatch) -> None:
    calls: list[tuple[object, str]] = []
    ensured: list[object] = []
    restored: list[object] = []

    class FakeAPI:
        pass

    def fake_attach_or_create(api, session_name):  # type: ignore[no-untyped-def]
        calls.append((api, session_name))
        return 0

    def fake_ensure_index(api):  # type: ignore[no-untyped-def]
        ensured.append(api)
        return True

    def fake_restore(api):  # type: ignore[no-untyped-def]
        restored.append(api)
        return None

    api = FakeAPI()
    monkeypatch.setattr(main, "attach_or_create_session", fake_attach_or_create)
    monkeypatch.setattr(main, "ensure_index_session", fake_ensure_index)
    monkeypatch.setattr(main, "restore_saved_sessions_if_needed", fake_restore)
    assert main.main(["s", "root"], api=api) == 0
    assert calls == [(api, "root")]
    assert ensured == [api, api]
    assert restored == [api]


def test_main_persistent_mode_opens_browser_with_flag(monkeypatch) -> None:
    calls: list[tuple[object, bool]] = []
    ensured: list[object] = []
    restored: list[object] = []

    class FakeAPI:
        pass

    def fake_browse(api, persistent=False):  # type: ignore[no-untyped-def]
        calls.append((api, persistent))
        return 0

    def fake_ensure_index(api):  # type: ignore[no-untyped-def]
        ensured.append(api)
        return True

    def fake_restore(api):  # type: ignore[no-untyped-def]
        restored.append(api)
        return None

    api = FakeAPI()
    monkeypatch.setattr(main, "ensure_index_session", fake_ensure_index)
    monkeypatch.setattr(main, "restore_saved_sessions_if_needed", fake_restore)
    monkeypatch.setattr(main, "browse_sessions", fake_browse)
    assert main.main(["p"], api=api) == 0
    assert calls == [(api, True)]
    assert ensured == [api]
    assert restored == [api]


def test_main_delegates_upgrade_to_contract_runtime(monkeypatch) -> None:
    recorded: dict[str, object] = {}
    ensured: list[object] = []
    restored: list[object] = []

    def fake_run_app(spec, argv, dispatch):  # type: ignore[no-untyped-def]
        recorded["spec"] = spec
        recorded["argv"] = argv
        recorded["dispatch"] = dispatch
        return 0

    def fake_ensure_index(api):  # type: ignore[no-untyped-def]
        ensured.append(api)
        return True

    def fake_restore(api):  # type: ignore[no-untyped-def]
        restored.append(api)
        return None

    monkeypatch.setattr(main, "run_app", fake_run_app)
    monkeypatch.setattr(main, "ensure_index_session", fake_ensure_index)
    monkeypatch.setattr(main, "restore_saved_sessions_if_needed", fake_restore)
    rc = main.main(["-u"])
    assert rc == 0
    assert recorded["spec"] == main.APP_SPEC
    assert recorded["argv"] == ["-u"]
    assert callable(recorded["dispatch"])
    assert ensured == []
    assert restored == []


def test_main_no_args_uses_help_runtime_without_tmux_bootstrap(monkeypatch) -> None:
    recorded: dict[str, object] = {}
    ensured: list[object] = []
    restored: list[object] = []

    def fake_run_app(spec, argv, dispatch):  # type: ignore[no-untyped-def]
        recorded["spec"] = spec
        recorded["argv"] = argv
        recorded["dispatch"] = dispatch
        return 0

    def fake_ensure_index(api):  # type: ignore[no-untyped-def]
        ensured.append(api)
        return True

    def fake_restore(api):  # type: ignore[no-untyped-def]
        restored.append(api)
        return None

    monkeypatch.setattr(main, "run_app", fake_run_app)
    monkeypatch.setattr(main, "ensure_index_session", fake_ensure_index)
    monkeypatch.setattr(main, "restore_saved_sessions_if_needed", fake_restore)
    rc = main.main([])
    assert rc == 0
    assert recorded["spec"] == main.APP_SPEC
    assert recorded["argv"] == []
    assert callable(recorded["dispatch"])
    assert ensured == []
    assert restored == []


def test_main_reload_uses_reload_helper_without_tmux_bootstrap(monkeypatch) -> None:
    reloaded: list[object] = []
    ensured: list[object] = []
    restored: list[object] = []

    class FakeAPI:
        pass

    def fake_reload(api):  # type: ignore[no-untyped-def]
        reloaded.append(api)
        return None

    def fake_ensure_index(api):  # type: ignore[no-untyped-def]
        ensured.append(api)
        return True

    def fake_restore(api):  # type: ignore[no-untyped-def]
        restored.append(api)
        return None

    api = FakeAPI()
    monkeypatch.setattr(main, "reload_managed_config", fake_reload)
    monkeypatch.setattr(main, "ensure_index_session", fake_ensure_index)
    monkeypatch.setattr(main, "restore_saved_sessions_if_needed", fake_restore)
    assert main.main(["reload"], api=api) == 0
    assert reloaded == [api]
    assert ensured == []
    assert restored == []
