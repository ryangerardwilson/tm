from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_installer_manages_tmux_primary_config() -> None:
    script = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert 'PUBLIC_BIN_DIR="$HOME/.local/bin"' in script
    assert 'PUBLIC_LAUNCHER="$PUBLIC_BIN_DIR/${APP}"' in script
    assert "--tmux-key <key>" in script
    assert 'tmux_index_key=${TMUX_INDEX_KEY:-M-i}' in script
    assert 'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"' in script
    assert 'TMUX_CONFIG_DIR="$HOME/.config/tmux"' in script
    assert 'TMUX_PRIMARY_CONF="$TMUX_CONFIG_DIR/tmux.conf"' in script
    assert 'TMUX_ROOT_CONF="$HOME/.tmux.conf"' in script
    assert 'TMUX_LEGACY_SNIPPET_FILE="${TMUX_LEGACY_SNIPPET_DIR}/tm.conf"' in script
    assert 'write_public_launcher() {' in script
    assert 'resolve_tmux_template_path() {' in script
    assert 'write_tmux_primary_conf() {' in script
    assert 'remove_legacy_tmux_files() {' in script
    assert 'tmux.conf.template' in script
    assert 'rendered = rendered.replace("__TMUX_INDEX_KEY__", tmux_index_key)' in script
    assert 'rendered = rendered.replace("__TM_PUBLIC_LAUNCHER__", public_launcher)' in script
    assert 'rm -f "$TMUX_CONFIG_DIR/tm.conf"' in script
    assert 'grep -Eq' in script
    assert 'python3 -m venv "$VENV_DIR"' in script
    assert '"$VENV_DIR/bin/pip" install --disable-pip-version-check -r "${SOURCE_DIR}/requirements.txt"' in script
    assert 'exec "${VENV_DIR}/bin/python" "${SOURCE_DIR}/main.py" "\\$@"' in script
    assert 'config_candidates=' not in script
    assert 'touch "$bashrc"' not in script
    assert '>> "$bashrc"' not in script
    assert 'write_tmux_snippet() {' not in script
    assert 'TMUX_MANAGED_CONF=' not in script
    assert 'write_tmux_managed_conf() {' not in script
    assert 'ensure_tmux_primary_conf_sources_managed_conf() {' not in script
    assert 'write_tmux_root_conf() {' not in script


def test_release_workflow_stamps_version_and_publishes_bundle() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert 'printf \'__version__ = "%s"\\n\'' in workflow
    assert "tm-linux-x64.tar.gz" in workflow
    assert "cp main.py session_tui.py snapshot_state.py tmux_api.py _version.py README.md install.sh requirements.txt tmux.conf.template dist/tm/" in workflow
    assert "cp -R rgw_cli_contract dist/tm/" in workflow


def test_tmux_template_manages_full_tmux_layer_and_omarchy_theme() -> None:
    template = (ROOT / "tmux.conf.template").read_text(encoding="utf-8")
    assert 'unbind -n "__TMUX_INDEX_KEY__"' in template
    assert 'bind -n "__TMUX_INDEX_KEY__" run-shell "TMUX_CLIENT_TTY=' in template
    assert "set -g prefix C-Space" in template
    assert "set -g prefix2 M-a" in template
    assert 'bind q run-shell "\\"__TM_PUBLIC_LAUNCHER__\\" reload >/dev/null 2>&1"' in template
    assert "bind -n M-p copy-mode" in template
    assert 'bind -n "M-|" split-window -v -c "#{pane_current_path}"' in template
    assert 'bind -n "M-\\\\" split-window -h -c "#{pane_current_path}"' in template
    assert 'bind -n "M-c" kill-pane' in template
    assert "unbind -T copy-mode-vi M-j" in template
    assert "unbind -T copy-mode-vi M-k" in template
    assert 'set -g status-style "bg=default,fg=default"' in template
    assert "source-file ~/.config/omarchy/current/theme/tmux.conf" in template
    assert "source-file ~/.config/tmux/tm.conf" not in template
