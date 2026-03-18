from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_installer_manages_tmux_shortcut_snippet() -> None:
    script = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert 'create_venv() {' in script
    assert '"$PYTHON_BIN" -m venv --without-pip "$VENV_DIR"' in script
    assert 'virtualenv --python "$PYTHON_BIN" --without-pip "$VENV_DIR"' in script
    assert "--tmux-key <key>" in script
    assert 'tmux_index_key=${TMUX_INDEX_KEY:-C-Insert}' in script
    assert 'TMUX_SNIPPET_FILE="$TMUX_SNIPPET_DIR/${APP}.conf"' in script
    assert 'TMUX_APP_BIN="$INSTALL_DIR/$APP"' in script
    assert 'detect_previous_tmux_index_key() {' in script
    assert 'legacy_action = "switch-client -t index"' in script
    assert 'client_tty = "#{client_tty}"' in script
    assert "current_action = f'run-shell \"{shlex.quote(app_bin)} >/dev/null 2>&1\"'" in script
    assert 'client_tty_action = f\'run-shell "TMUX_CLIENT_TTY={shlex.quote("#{client_tty}")} {shlex.quote(app_bin)} >/dev/null 2>&1"\'' in script
    assert 'key = key.strip(\'"\')' in script
    assert 'printf \'bind -n "%s" run-shell "%s"\\n\' "$tmux_index_key" "$tmux_index_run_shell_command"' in script
    assert 'previous_tmux_index_key=' in script
    assert "declare -A seen=()" in script
    assert '"M-h" \\' in script
    assert '"M-|" \\' in script
    assert '"M-\\\\\\\\" \\' in script
    assert '"M-d" \\' in script
    assert '"M--" \\' in script
    assert '"M-v" \\' in script
    assert '"M-Home" \\' in script
    assert '"M-End" \\' in script
    assert '"M-DC"; do' in script
    assert 'printf \'unbind -n "%s"\\n\' "$key"' in script
    assert 'printf \'bind -n "%s" select-pane -L\\n\' "M-h"' in script
    assert 'printf \'bind -n "%s" split-window -h -c "#{pane_current_path}"\\n\' "M-|"' in script
    assert 'printf \'bind -n "%s" split-window -v -c "#{pane_current_path}"\\n\' "M-\\\\\\\\"' in script
    assert 'printf \'bind -n "%s" kill-pane\\n\' "M-d"' in script
    assert 'source-file $TMUX_SNIPPET_FILE' in script
    assert 'exec "${VENV_DIR}/bin/python" "${SOURCE_DIR}/main.py" "\\$@"' in script
    assert 'python3 -m venv "$VENV_DIR"' not in script
    assert 'bin/pip' not in script
    assert '"unbind -n C-Insert",' in script
    assert '"bind -n C-Insert switch-client -t index",' in script
    assert '"unbind -n Insert",' in script
    assert '"bind -n Insert switch-client -t index",' in script


def test_release_workflow_stamps_version_and_publishes_bundle() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert 'printf \'__version__ = "%s"\\n\'' in workflow
    assert "tm-linux-x64.tar.gz" in workflow
    assert "cp main.py session_tui.py snapshot_state.py tmux_api.py _version.py README.md install.sh requirements.txt dist/tm/" in workflow
    assert "cp -R rgw_cli_contract dist/tm/" in workflow
