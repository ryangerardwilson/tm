# Repository Guidelines

## Workspace Defaults
- Follow `/home/ryan/Documents/agent_context/CLI_TUI_STYLE_GUIDE.md` for CLI/TUI taste and help shape.
- Follow `/home/ryan/Documents/agent_context/CANONICAL_REFERENCE_IMPLEMENTATION_FOR_CLI_AND_TUI_APPS.md` for executable contract details such as `-h`, `-v`, `-u`, installer behavior, and regression expectations.
- This file only records `tm`-specific constraints or deliberate deviations.

## Product Boundary
- `tm` is a narrow tmux utility, not a general tmux wrapper.
- Keep one primary flow: `tm` opens a curses session browser.
- From inside the browser:
  - `l` switches or attaches to the selected session
  - `n` creates a new named session
  - `x` kills the current, marked, or visual selection
- Do not grow this into a broad session manager unless explicitly asked.

## Interface Rules
- Keep the default flow fast and shell-native.
- Bare `tm` is the deliberate no-arg exception to the workspace default help behavior and must open the curses session browser.
- `tm k` should stay dense, grayscale, and keyboard-first.
- Favor `j`/`k`, arrow keys, `m`, `v`, `x`, `?`, and `q`.
- Error text should stay short and explicit.

## Implementation Guardrails
- Keep the code stdlib-only.
- Keep tmux subprocess calls isolated in `tmux_api.py`.
- Preserve safe kill semantics by moving attached clients to another session before killing the target.
- If killing the final non-fallback session requires a temporary session, create it explicitly rather than guessing around tmux internals.

## Installer Deviation
- Until `tm` has a published release workflow, `install.sh` is intentionally source-checkout-first and installs a shim that points at this checkout.
- Keep that behavior explicit in help and README; do not pretend a GitHub release path exists until it actually does.
