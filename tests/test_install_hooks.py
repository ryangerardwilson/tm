from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_installer_manages_tmux_shortcut_snippet() -> None:
    script = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert "--tmux-key <key>" in script
    assert 'tmux_index_key=${TMUX_INDEX_KEY:-M-i}' in script
    assert 'die "--tmux-key ${tmux_index_key} conflicts with reserved tmux root bindings (M-d, M-h, M--, M-\\\\)"' in script
    assert 'if [[ "$tmux_index_key" == "M-\\\\" ]]; then' in script
    assert 'TMUX_SNIPPET_FILE="$TMUX_SNIPPET_DIR/${APP}.conf"' in script
    assert "printf 'bind -n %s switch-client -t index\\n' \"$tmux_index_key\"" in script
    assert 'previous_tmux_index_key=' in script
    assert 'echo "unbind -n \'M-\\\\\'"' in script
    assert 'for key in "$tmux_index_key" "$previous_tmux_index_key" "M--" "M-d" "M-h" "M-i" "M-v" "C-i" "Tab" "C-DC" "C-Home" "C-End" "C-Insert" "Insert" "F8" "F9" "F12"; do' in script
    assert 'source-file $TMUX_SNIPPET_FILE' in script
    assert "echo 'bind -n M-h select-pane -L'" in script
    assert 'echo "bind -n \'M-\\\\\' split-window -h"' in script
    assert "echo 'bind -n M-- split-window -v'" in script
    assert "echo 'bind -n M-d kill-pane'" in script
    assert 'tmux ls >/dev/null 2>&1' in script
    assert 'tmux source-file "$TMUX_SNIPPET_FILE" >/dev/null 2>&1 || true' in script


def test_release_workflow_stamps_version_and_publishes_bundle() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert 'printf \'__version__ = "%s"\\n\'' in workflow
    assert "tm-linux-x64.tar.gz" in workflow
    assert "cp main.py session_tui.py snapshot_state.py tmux_api.py _version.py README.md install.sh requirements.txt dist/tm/" in workflow
