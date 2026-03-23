from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_installer_manages_tmux_shortcut_snippet() -> None:
    script = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert 'PUBLIC_BIN_DIR="$HOME/.local/bin"' in script
    assert 'PUBLIC_LAUNCHER="$PUBLIC_BIN_DIR/${APP}"' in script
    assert "--tmux-key <key>" in script
    assert 'tmux_index_key=${TMUX_INDEX_KEY:-M-i}' in script
    assert 'TMUX_SNIPPET_FILE="${TMUX_SNIPPET_DIR}/tm.conf"' in script
    assert 'TMUX_RUN_SHELL_COMMAND="TMUX_CLIENT_TTY=' in script
    assert 'write_public_launcher() {' in script
    assert 'write_tmux_snippet() {' in script
    assert 'ensure_tmux_config_sources_snippet() {' in script
    assert 'previous_tmux_index_key=' in script
    assert "declare -A seen=()" in script
    assert 'printf \'unbind -n "%s"\\n\' "$key"' in script
    assert 'printf \'bind -n "%s" run-shell "%s"\\n\' "$tmux_index_key" "$tmux_run_shell_escaped"' in script
    assert 'printf \'%s\\n\' \'bind -n "M-h" select-pane -L\'' in script
    assert 'printf \'%s\\n\' \'bind -n "M-|" split-window -h -c "#{pane_current_path}"\'' in script
    assert 'printf \'%s\\n\' \'bind -n "M-\\\\" split-window -v -c "#{pane_current_path}"\'' in script
    assert 'printf \'%s\\n\' \'bind -n "M-d" kill-pane\'' in script
    assert 'source-file $TMUX_SNIPPET_FILE' in script
    assert 'python3 -m venv "$VENV_DIR"' in script
    assert '"$VENV_DIR/bin/pip" install --disable-pip-version-check -r "${SOURCE_DIR}/requirements.txt"' in script
    assert 'exec "${VENV_DIR}/bin/python" "${SOURCE_DIR}/main.py" "\\$@"' in script
    assert 'config_candidates=' not in script
    assert 'touch "$bashrc"' not in script
    assert '>> "$bashrc"' not in script
    assert "'unbind -n C-Insert'," in script
    assert "'bind -n C-Insert switch-client -t index'," in script
    assert "'unbind -n Insert'," in script
    assert "'bind -n Insert switch-client -t index'," in script


def test_release_workflow_stamps_version_and_publishes_bundle() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert 'printf \'__version__ = "%s"\\n\'' in workflow
    assert "tm-linux-x64.tar.gz" in workflow
    assert "cp main.py session_tui.py snapshot_state.py tmux_api.py _version.py README.md install.sh requirements.txt dist/tm/" in workflow
    assert "cp -R rgw_cli_contract dist/tm/" in workflow
