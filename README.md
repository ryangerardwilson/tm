# tm

`tm` is a small tmux session browser.

This replaces shell-function glue and custom tmux chooser bindings with a real terminal app.

## Install

For now `tm` installs from the local checkout:

```bash
cd ~/Apps/tm
./install.sh
```

That writes a shim to `~/.tm/bin/tm`. If `~/.tm/bin` is on your `PATH`, you can run `tm` from any shell.

## Usage

```bash
tm
tm -h
tm s root
tm -v
tm -u
```

### Browser

```bash
tm
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

### Direct Session

```bash
tm s root
```

If `root` already exists, `tm` attaches to it outside tmux or switches the current client to it inside tmux. If it does not exist yet, `tm` creates `root` first and then takes you there.

When killing sessions, `tm` moves attached clients off the target session(s) before killing them. If there is no other session available, it creates a temporary fallback session so the kill can complete safely.
