import os
import subprocess
import tempfile
from pathlib import Path
import unittest


INSTALLER = Path(__file__).resolve().parent / "install.sh"
if not INSTALLER.exists():
    INSTALLER = Path(__file__).resolve().parents[1] / "install.sh"


class InstallContractTests(unittest.TestCase):
    def _write_executable(self, path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)

    def _run_installer(self, home_dir: Path, *args: str, path_prefix: Path | None = None) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["HOME"] = str(home_dir)
        if path_prefix is not None:
            env["PATH"] = f"{path_prefix}:{env['PATH']}"
        return subprocess.run(
            ["/usr/bin/bash", str(INSTALLER), *args],
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )

    def test_dash_v_without_argument_prints_latest_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            home_dir = tmp_path / "home"
            bin_dir.mkdir()
            home_dir.mkdir()

            self._write_executable(
                bin_dir / "curl",
                "#!/usr/bin/bash\n"
                "if [[ \"$*\" == *\"releases/latest\"* ]]; then\n"
                "  printf 'https://github.com/ryangerardwilson/tm/releases/tag/v0.1.21\\n'\n"
                "  exit 0\n"
                "fi\n"
                "echo unexpected curl call >&2\n"
                "exit 1\n",
            )

            result = self._run_installer(home_dir, "-v", path_prefix=bin_dir)

            self.assertEqual(result.stdout.strip(), "0.1.21")

    def test_upgrade_same_version_uses_dash_v(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            home_dir = tmp_path / "home"
            bin_dir.mkdir()
            home_dir.mkdir()

            self._write_executable(
                bin_dir / "curl",
                "#!/usr/bin/bash\n"
                "if [[ \"$*\" == *\"releases/latest\"* ]]; then\n"
                "  printf 'https://github.com/ryangerardwilson/tm/releases/tag/v0.1.21\\n'\n"
                "  exit 0\n"
                "fi\n"
                "echo unexpected curl call >&2\n"
                "exit 1\n",
            )
            self._write_executable(
                bin_dir / "tm",
                "#!/usr/bin/bash\n"
                "if [[ \"$1\" == \"-v\" ]]; then\n"
                "  printf '0.1.21\\n'\n"
                "  exit 0\n"
                "fi\n"
                "echo unexpected invocation >&2\n"
                "exit 1\n",
            )

            result = self._run_installer(home_dir, "-u", "--tmux-key", "F8", path_prefix=bin_dir)

            self.assertIn("already installed", result.stdout)
            self.assertTrue((home_dir / ".local" / "bin" / "tm").exists())
            primary_conf = (home_dir / ".config" / "tmux" / "tmux.conf").read_text(encoding="utf-8")
            self.assertIn('bind -n "F8" run-shell', primary_conf)
            self.assertIn('bind q run-shell', primary_conf)
            self.assertIn('\\"/tmp', primary_conf)
            self.assertIn('\\" reload >/dev/null 2>&1', primary_conf)
            self.assertIn("set -g prefix C-Space", primary_conf)
            self.assertIn('bind -n "M-|" split-window -v -c "#{pane_current_path}"', primary_conf)
            self.assertIn('bind -n "M-\\\\" split-window -h -c "#{pane_current_path}"', primary_conf)
            self.assertIn('bind -n "M-c" kill-pane', primary_conf)
            self.assertIn("bind -n M-p copy-mode", primary_conf)
            self.assertIn('set -g status-style "bg=default,fg=default"', primary_conf)
            self.assertIn("source-file ~/.config/omarchy/current/theme/tmux.conf", primary_conf)
            self.assertFalse((home_dir / ".config" / "tmux" / "tm.conf").exists())
            self.assertFalse((home_dir / ".tmux" / "tm.conf").exists())
            self.assertFalse((home_dir / ".tmux.conf").exists())

    def test_local_source_install_writes_managed_launchers(self):
        with tempfile.TemporaryDirectory() as tmp:
            home_dir = Path(tmp)
            bashrc_path = home_dir / ".bashrc"
            bashrc_path.write_text("# existing shell config\n", encoding="utf-8")
            tmux_primary_conf = home_dir / ".config" / "tmux" / "tmux.conf"
            tmux_primary_conf.parent.mkdir(parents=True)
            tmux_primary_conf.write_text(
                "set -g prefix C-b\n"
                "bind r source-file ~/.tmux.conf\n",
                encoding="utf-8",
            )
            legacy_root_conf = home_dir / ".tmux.conf"
            legacy_root_conf.write_text(
                "# Managed by tm installer.\n"
                "source-file ~/.config/tmux/tmux.conf\n",
                encoding="utf-8",
            )
            legacy_snippet = home_dir / ".tmux" / "tm.conf"
            legacy_snippet.parent.mkdir()
            legacy_snippet.write_text('bind -n "F12" run-shell "legacy"\n', encoding="utf-8")
            managed_include = home_dir / ".config" / "tmux" / "tm.conf"
            managed_include.write_text('bind -n "F7" run-shell "old"\n', encoding="utf-8")

            result = self._run_installer(home_dir, "-b", str(INSTALLER.parent), "--tmux-key", "F9", "-n")

            internal_launcher = home_dir / ".tm" / "bin" / "tm"
            self.assertTrue(internal_launcher.exists())
            internal_text = internal_launcher.read_text(encoding="utf-8")
            self.assertIn('exec "', internal_text)
            self.assertIn("/.tm/venv/bin/python", internal_text)
            self.assertIn("/.tm/app/source/main.py", internal_text)
            self.assertEqual(
                bashrc_path.read_text(encoding="utf-8"),
                "# existing shell config\n",
            )
            public_launcher = home_dir / ".local" / "bin" / "tm"
            self.assertTrue(public_launcher.exists())
            public_text = public_launcher.read_text(encoding="utf-8")
            self.assertIn("# Managed by rgw_cli_contract local-bin launcher", public_text)
            self.assertIn(f'exec "{internal_launcher}" "$@"', public_text)
            version = subprocess.run(
                [str(public_launcher), "-v"],
                capture_output=True,
                text=True,
                env={**os.environ, "HOME": str(home_dir)},
                check=True,
            )
            self.assertEqual(version.stdout.strip(), "0.0.0")
            self.assertIn(f"Manually add to ~/.bashrc if needed: export PATH={public_launcher.parent}:$PATH", result.stdout)
            self.assertFalse(legacy_root_conf.exists())
            self.assertFalse(legacy_snippet.exists())
            self.assertFalse(managed_include.exists())
            primary_conf_text = tmux_primary_conf.read_text(encoding="utf-8")
            self.assertIn('bind -n "F9" run-shell', primary_conf_text)
            self.assertIn(f'\\"{public_launcher}\\"', primary_conf_text)
            self.assertIn("set -g prefix C-Space", primary_conf_text)
            self.assertIn("bind q run-shell", primary_conf_text)
            self.assertIn(f'\\"{public_launcher}\\" reload >/dev/null 2>&1', primary_conf_text)
            self.assertIn("bind -n M-p copy-mode", primary_conf_text)
            self.assertIn('bind -n "M-|" split-window -v -c "#{pane_current_path}"', primary_conf_text)
            self.assertIn('bind -n "M-\\\\" split-window -h -c "#{pane_current_path}"', primary_conf_text)
            self.assertIn('bind -n "M-c" kill-pane', primary_conf_text)
            self.assertIn("source-file ~/.config/omarchy/current/theme/tmux.conf", primary_conf_text)
            self.assertNotIn("legacy", primary_conf_text)
            self.assertNotIn("source-file ~/.config/tmux/tm.conf", primary_conf_text)

    def test_local_source_install_preserves_non_tm_root_tmux_conf(self):
        with tempfile.TemporaryDirectory() as tmp:
            home_dir = Path(tmp)
            root_conf = home_dir / ".tmux.conf"
            root_conf.write_text("set -g status on\n", encoding="utf-8")

            self._run_installer(home_dir, "-b", str(INSTALLER.parent), "-n")

            self.assertEqual(root_conf.read_text(encoding="utf-8"), "set -g status on\n")


if __name__ == "__main__":
    unittest.main()
