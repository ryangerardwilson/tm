from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_installer_upgrade_checks_installed_version_with_dash_v() -> None:
    script = (ROOT / "install.sh").read_text()
    assert '"$APP" -v' in script
    assert '"$APP" --version' not in script


def test_release_workflow_stamps_version_and_publishes_bundle() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text()
    assert 'printf \'__version__ = "%s"\\n\'' in workflow
    assert "tm-linux-x64.tar.gz" in workflow
