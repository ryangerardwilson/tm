from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_installer_upgrade_checks_installed_version_with_dash_v() -> None:
    script = (ROOT / "install.sh").read_text()
    assert '"$APP" -v' in script
    assert '"$APP" --version' not in script


def test_installer_manages_tmux_shortcut_snippet() -> None:
    script = (ROOT / "install.sh").read_text()
    assert '--tmux-key <key>' in script
    assert 'tmux_index_key=${TMUX_INDEX_KEY:-C-Insert}' in script
    assert 'TMUX_SNIPPET_FILE="$TMUX_SNIPPET_DIR/${APP}.conf"' in script
    assert "printf 'bind -n %s switch-client -t index\\n' \"$tmux_index_key\"" in script
    assert 'previous_tmux_index_key=' in script
    assert 'for key in "$tmux_index_key" "$previous_tmux_index_key" "C-i" "Tab" "C-Insert" "Insert" "F8" "F9" "F12"; do' in script
    assert 'source-file $TMUX_SNIPPET_FILE' in script


def test_installer_requires_archive_to_include_install_script() -> None:
    script = (ROOT / "install.sh").read_text()
    assert '[[ -f "$tmp_dir/${APP}/install.sh" ]] || die "Archive missing ${APP}/install.sh"' in script


def test_release_workflow_stamps_version_and_publishes_bundle() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text()
    assert 'printf \'__version__ = "%s"\\n\'' in workflow
    assert "tm-linux-x64.tar.gz" in workflow
    assert "cp main.py session_tui.py tmux_api.py _version.py README.md install.sh dist/tm/" in workflow
