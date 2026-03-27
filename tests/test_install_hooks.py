from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_installer_manages_tmux_shortcut_snippet() -> None:
    script = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert 'PUBLIC_BIN_DIR="$HOME/.local/bin"' in script
    assert 'PUBLIC_LAUNCHER="$PUBLIC_BIN_DIR/${APP}"' in script
    assert "--tmux-key <key>" in script
    assert 'tmux_index_key=${TMUX_INDEX_KEY:-M-i}' in script
    assert 'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"' in script
    assert 'TMUX_SNIPPET_FILE="${TMUX_SNIPPET_DIR}/tm.conf"' in script
    assert 'write_public_launcher() {' in script
    assert 'resolve_tmux_template_path() {' in script
    assert 'write_tmux_root_conf() {' in script
    assert 'remove_legacy_tmux_snippet() {' in script
    assert 'tmux.conf.template' in script
    assert 'rendered = rendered.replace("__TMUX_INDEX_KEY__", tmux_index_key)' in script
    assert 'rendered = rendered.replace("__TM_PUBLIC_LAUNCHER__", public_launcher)' in script
    assert 'rm -f "$TMUX_SNIPPET_FILE"' in script
    assert 'rmdir "$TMUX_SNIPPET_DIR" 2>/dev/null || true' in script
    assert 'python3 -m venv "$VENV_DIR"' in script
    assert '"$VENV_DIR/bin/pip" install --disable-pip-version-check -r "${SOURCE_DIR}/requirements.txt"' in script
    assert 'exec "${VENV_DIR}/bin/python" "${SOURCE_DIR}/main.py" "\\$@"' in script
    assert 'config_candidates=' not in script
    assert 'touch "$bashrc"' not in script
    assert '>> "$bashrc"' not in script
    assert 'ensure_tmux_config_sources_snippet() {' not in script
    assert 'write_tmux_snippet() {' not in script


def test_release_workflow_stamps_version_and_publishes_bundle() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert 'printf \'__version__ = "%s"\\n\'' in workflow
    assert "tm-linux-x64.tar.gz" in workflow
    assert "cp main.py session_tui.py snapshot_state.py tmux_api.py _version.py README.md install.sh requirements.txt tmux.conf.template dist/tm/" in workflow
    assert "cp -R rgw_cli_contract dist/tm/" in workflow


def test_tmux_template_owns_reload_and_managed_bindings() -> None:
    template = (ROOT / "tmux.conf.template").read_text(encoding="utf-8")
    assert 'bind -n "__TMUX_INDEX_KEY__" run-shell "TMUX_CLIENT_TTY=' in template
    assert 'bind -n M-p copy-mode' in template
    assert 'bind -n "M-|" split-window -v -c "#{pane_current_path}"' in template
