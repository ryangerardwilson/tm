from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_installer_manages_tmux_shortcut_snippet() -> None:
    script = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert "--tmux-key <key>" in script
    assert 'tmux_index_key=${TMUX_INDEX_KEY:-M-i}' in script
    assert 'TMUX_SNIPPET_FILE="$TMUX_SNIPPET_DIR/${APP}.conf"' in script
    assert "printf 'bind -n %s switch-client -t index\\n' \"$tmux_index_key\"" in script
    assert 'previous_tmux_index_key=' in script
    assert 'for key in "$tmux_index_key" "$previous_tmux_index_key" "M-i" "C-i" "Tab" "C-Insert" "Insert" "F8" "F9" "F12"; do' in script
    assert 'source-file $TMUX_SNIPPET_FILE' in script
    assert 'tmux ls >/dev/null 2>&1' in script
    assert 'tmux source-file "$TMUX_SNIPPET_FILE" >/dev/null 2>&1 || true' in script


def test_release_workflow_stamps_version_and_publishes_bundle() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert 'printf \'__version__ = "%s"\\n\'' in workflow
    assert "tm-linux-x64.tar.gz" in workflow
    assert "cp main.py session_tui.py snapshot_state.py tmux_api.py _version.py README.md install.sh requirements.txt dist/tm/" in workflow
