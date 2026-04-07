# Repository Guidelines

## Workspace Defaults
- Follow `/home/ryan/Documents/agent_context/CLI_TUI_STYLE_GUIDE.md` for CLI/TUI taste and help shape.
- Follow `/home/ryan/Documents/agent_context/CANONICAL_REFERENCE_IMPLEMENTATION_FOR_CLI_AND_TUI_APPS.md` for executable contract details such as `-h`, `-v`, `-u`, installer behavior, and regression expectations.
- This file only records `tm`-specific constraints or deliberate deviations.

## Product Boundary
- `tm` is a narrow tmux utility, not a general tmux wrapper.
- Keep one primary flow: `tm` takes the user to the managed `index` session running the persistent curses browser.
- From inside the browser:
  - `l` switches or attaches to the selected session
  - `n` creates a new named session
  - `x` kills the current, marked, or visual selection
- Automatic restore may rebuild tmux layouts and reopen Codex panes, but it should stay focused on tmux session recovery rather than arbitrary process checkpointing.
- Do not grow this into a broad session manager unless explicitly asked.

## Interface Rules
- Keep the default flow fast and shell-native.
- Bare `tm` should use the workspace default help behavior.
- `tm index` must switch or attach to the managed `index` session.
- `tm reload` must remove tm-managed bindings from the live tmux server and then re-source `~/.config/tmux/tmux.conf`.
- Any `tm` invocation that targets sessions or the persistent browser must ensure the managed `index` session exists and that its `index` window is running `tm p`.
- `tm k` should stay dense, grayscale, and keyboard-first.
- Favor `j`/`k`, arrow keys, `m`, `v`, `x`, `?`, and `q`.
- Error text should stay short and explicit.

## Implementation Guardrails
- Keep the code stdlib-only.
- Keep tmux subprocess calls isolated in `tmux_api.py`.
- Keep restore snapshots under `~/.tm/state/` and treat them as internal state, not a user-edited config surface.
- Preserve safe kill semantics by moving attached clients to another session before killing the target.
- If killing the final non-fallback session requires a temporary session, create it explicitly rather than guessing around tmux internals.
- Restored non-Codex panes should come back as shells in the saved working directory unless the app has an exact, low-risk resume primitive for that process type.
- Keep tm narrow as an app, but let it own the full managed tmux layer at `~/.config/tmux/tmux.conf` when the user wants tm-driven bindings and defaults.
- Preserve Omarchy compatibility by sourcing `~/.config/omarchy/current/theme/tmux.conf` from the managed tmux config instead of duplicating theme values in the repo.

## Release Contract
- Keep `tm` aligned with the workspace release contract.
- `install.sh` installs tagged release bundles into `~/.tm/app`, keeps the internal launcher at `~/.tm/bin/tm`, and publishes the user-facing command at `~/.local/bin/tm`.
- `install.sh` owns the full tmux config at `~/.config/tmux/tmux.conf` and should regenerate that file from `tmux.conf.template` on every install or upgrade.
- `install.sh` should remove tm-managed legacy files such as `~/.config/tmux/tm.conf`, `~/.tmux/tm.conf`, and tm-managed `~/.tmux.conf` shims so Omarchy and fresh tmux reloads converge on the same config path.
- Do not hand-edit the managed tmux config except for short-lived local testing. After testing, move the change into `~/Apps/tm/`, then use the app install or release-upgrade path so `~/.config/tmux/tmux.conf` is regenerated from the app.
- Tagged builds stamp `_version.py` in the release artifact; the checked-in file stays at `0.0.0`.
