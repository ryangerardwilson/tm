# tm

`tm` is a small tmux session browser.

This replaces shell-function glue and custom tmux chooser bindings with a real terminal app.

## Install

Install the latest tagged release with:

```bash
curl -fsSL https://raw.githubusercontent.com/ryangerardwilson/tm/main/install.sh | bash
```

That installs `tm` into `~/.tm/bin/tm` and the release bundle into `~/.tm/app`.
If `~/.tm/bin` is on your `PATH`, you can run `tm` from any shell.

Installer shortcuts:

- `./install.sh -h`: installer help
- `./install.sh -v`: print the latest release version
- `./install.sh -v 0.1.0`: install a specific release
- `./install.sh -u`: upgrade to the latest release if newer
- `./install.sh --tmux-key F8 -u`: override the tmux index shortcut if you want a different key

The installer manages a small tmux snippet at `~/.tmux/tm.conf` and ensures `~/.tmux.conf`
sources it, so the index-session shortcut is repo-managed instead of hand-maintained.
The default shortcut key is `C-Insert`. You can still override it with `--tmux-key <key>` if you
want a different tmux key name.

## Usage

```bash
tm
tm p
tm -h
tm s root
tm -v
tm -u
```

`tm -v` prints the installed runtime version. Source checkouts keep `_version.py`
at `0.0.0`; tagged release artifacts stamp the real release version during the
release workflow.

### Browser

```bash
tm
```

Persistent browser mode inside tmux:

```bash
tm p
```

Core actions:

- `j` / `k` or arrow keys: move
- `l`: switch to the selected session
- `m`: mark or unmark the current session
- `v`: toggle visual selection for a contiguous range
- `x`: kill the current session, marked sessions, or the visual selection
- `n`: create a new named session
- `?`: toggle help
- `q`: quit the picker

Outside tmux, `l` attaches to the selected session. Inside tmux, it switches the current client to that session.
In `tm p`, the picker stays running in its original tmux pane after a switch and refreshes the session list, so ordering is updated when you jump back to it later.

### Direct Session

```bash
tm s root
```

If `root` already exists, `tm` attaches to it outside tmux or switches the current client to it inside tmux. If it does not exist yet, `tm` creates `root` first and then takes you there.

When killing sessions, `tm` moves attached clients off the target session(s) before killing them. If there is no other session available, it creates a temporary fallback session so the kill can complete safely.
