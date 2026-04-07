# tm

`tm` is a small tmux session browser.

This replaces shell-function glue and custom tmux chooser bindings with a real terminal app.

## Install

Install the latest tagged release with:

```bash
curl -fsSL https://raw.githubusercontent.com/ryangerardwilson/tm/main/install.sh | bash
```

The installer keeps app state under `~/.tm`, publishes the user-facing command
at `~/.local/bin/tm`, and overwrites `~/.config/tmux/tmux.conf` with the
repo-managed tmux config on every install or upgrade.

If `~/.local/bin` is not already on your `PATH`, add it once to `~/.bashrc`
and reload your shell:

```bash
export PATH="$HOME/.local/bin:$PATH"
source ~/.bashrc
```

The public launcher is `~/.local/bin/tm`. The internal runtime still lives
under `~/.tm/bin/tm`, with the release bundle in `~/.tm/app`.

Installer shortcuts:

- `./install.sh -h`: installer help
- `./install.sh -v`: print the latest release version
- `./install.sh -v 0.1.0`: install a specific release
- `./install.sh -u`: upgrade to the latest release if newer
- `./install.sh --tmux-key F8 -u`: override the tmux index shortcut if you want a different key

The installer never edits shell startup files automatically. If `~/.local/bin`
is already on your `PATH`, no shell change is needed.

`tm` owns the full contents of `~/.config/tmux/tmux.conf`. Persistent tmux
config changes should be made in the `tm` repo and then installed or upgraded
through `tm`, not hand-edited in `~/.config/tmux/tmux.conf`.

`tm` does not depend on `~/.tmux.conf`. During install or upgrade it removes
tm-managed legacy shims such as `~/.tmux.conf`, `~/.tmux/tm.conf`, and
`~/.config/tmux/tm.conf` so Omarchy and tmux both converge on the same
`~/.config/tmux/tmux.conf` source of truth.

The managed config keeps the index-session shortcut repo-owned instead of
hand-maintained. That shortcut runs the installed `tm` command, so the managed
`index` session is recreated first if it is missing. The default shortcut key
is `M-i`. You can still override it with `--tmux-key <key>` if you want a
different tmux key name.

The managed prefix-`q` reload now runs `tm reload`, which first unbinds the
tm-managed key set from the live tmux server and then re-sources
`~/.config/tmux/tmux.conf`. Use that after upgrading `tm` if your current tmux
server was started with an older binding set.

The managed tmux config keeps the index-session shortcut and the pane, window,
session, copy-mode, and status-bar setup repo-owned while still sourcing the
active Omarchy theme from `~/.config/omarchy/current/theme/tmux.conf`.

## Usage

```bash
tm
tm -h
tm index
tm reload
tm s root
tm -v
tm -u
```

`tm -v` prints the installed runtime version. Source checkouts keep `_version.py`
at `0.0.0`; tagged release artifacts stamp the real release version during the
release workflow.

### Index Session

```bash
tm index
```

`tm index` switches to the managed `index` session outside tmux or switches your current tmux client to it inside tmux. Bare `tm` now shows help.

The persistent index browser writes an automatic restore snapshot once per hour in the background.
Every `tm` invocation also ensures the managed `index` session exists and that its `index` window is running `tm p`.

Core actions:

- `j` / `k` or arrow keys: move
- `l`: switch to the selected session
- `m`: mark or unmark the current session
- `v`: toggle visual selection for a contiguous range
- `x`: kill the current session, marked sessions, or the visual selection
- `n`: create a new named session
- `,rn`: rename the current session
- `?`: toggle help
- `q`: quit the picker

Outside tmux, `l` attaches to the selected session. Inside tmux, it switches the current client to that session.
In the managed `index` session, the picker stays running in its original tmux pane after a switch and refreshes the session list, so ordering is updated when you jump back to it later.
Sessions with actively working Codex panes show the same compact animated pulse used in `loc`.

## Automatic Restore

If a saved snapshot exists and there are no live non-index tmux sessions, `tm` restores the snapshot automatically on the next `tm` startup.

Restore behavior:

- recreates tmux sessions, windows, and pane splits from the latest snapshot
- resumes Codex panes with `codex resume <thread_id>` when the running Codex thread ID was captured
- reopens non-Codex panes as shells in the saved working directory

This restores tmux layout and Codex conversations. It does not checkpoint arbitrary in-memory process state mid-flight.

### Direct Session

```bash
tm s root
```

If `root` already exists, `tm` attaches to it outside tmux or switches the current client to it inside tmux. If it does not exist yet, `tm` creates `root` first and then takes you there.

When killing sessions, `tm` moves attached clients off the target session(s) before killing them. If there is no other session available, it creates a temporary fallback session so the kill can complete safely.
