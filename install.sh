#!/usr/bin/env bash
set -euo pipefail

APP=tm
REPO="ryangerardwilson/tm"
APP_HOME="$HOME/.${APP}"
INSTALL_DIR="$APP_HOME/bin"
APP_DIR="$APP_HOME/app"
VENV_DIR="$APP_HOME/venv"
FILENAME="${APP}-linux-x64.tar.gz"
TMUX_SNIPPET_DIR="$HOME/.tmux"
TMUX_SNIPPET_FILE="$TMUX_SNIPPET_DIR/${APP}.conf"

MUTED='\033[0;2m'
RED='\033[0;31m'
NC='\033[0m'

usage() {
  cat <<EOF
${APP^^} Installer

Usage: install.sh [options]

Options:
  -h                         Show this help and exit
  -v [<version>]             Install a specific release (e.g. 0.1.0 or v0.1.0)
                             Without an argument, print the latest release version and exit
  -u                         Reinstall the latest release if it is newer (upgrade)
      --tmux-key <key>       Bind the index-session shortcut in tmux (default: C-Insert)
  -b, --binary <path>        Install from a local release bundle
      --no-modify-path       Skip editing shell rc files
EOF
}

info() { echo -e "${MUTED}$1${NC}"; }
die() { echo -e "${RED}$1${NC}" >&2; exit 1; }

requested_version=${VERSION:-}
binary_path=""
no_modify_path=false
show_latest=false
upgrade=false
tmux_index_key=${TMUX_INDEX_KEY:-C-Insert}
previous_tmux_index_key=""

if [[ -f "$TMUX_SNIPPET_FILE" ]]; then
  previous_tmux_index_key=$(sed -n 's/^bind -n \(.*\) switch-client -t index$/\1/p' "$TMUX_SNIPPET_FILE" | tail -n 1)
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    -v)
      if [[ -n "${2:-}" && "${2:0:1}" != "-" ]]; then
        requested_version="$2"
        shift 2
      else
        show_latest=true
        shift
      fi
      ;;
    -u|--upgrade)
      upgrade=true
      shift
      ;;
    -b|--binary)
      [[ -n "${2:-}" ]] || die "--binary requires a path"
      binary_path="$2"
      shift 2
      ;;
    --tmux-key)
      [[ -n "${2:-}" ]] || die "--tmux-key requires a tmux key name"
      tmux_index_key="$2"
      shift 2
      ;;
    --no-modify-path)
      no_modify_path=true
      shift
      ;;
    --version)
      info "--version is deprecated. Use -v instead."
      if [[ -n "${2:-}" && "${2:0:1}" != "-" ]]; then
        requested_version="$2"
        shift 2
      else
        show_latest=true
        shift
      fi
      ;;
    --upgrade)
      info "--upgrade is deprecated. Use -u instead."
      upgrade=true
      shift
      ;;
    *)
      die "Unknown option: $1"
      ;;
  esac
done

_latest_version=""
latest_version_from_redirect() {
  command -v curl >/dev/null 2>&1 || die "'curl' is required"
  curl -fsSL -o /dev/null -w '%{url_effective}' "https://github.com/${REPO}/releases/latest" \
    | sed -n 's#.*/releases/tag/v\([^/?#[:space:]]*\).*#\1#p'
}
get_latest_version() {
  if [[ -z "${_latest_version}" ]]; then
    if command -v gh >/dev/null 2>&1; then
      _latest_version=$(gh release view --repo "${REPO}" --json tagName --jq '.tagName' 2>/dev/null || true)
      _latest_version="${_latest_version#v}"
    fi
    if [[ -z "${_latest_version}" ]]; then
      _latest_version="$(latest_version_from_redirect || true)"
    fi
    [[ -n "${_latest_version}" ]] || die "Unable to determine latest release"
  fi
  printf '%s\n' "${_latest_version}"
}

if $show_latest; then
  [[ "$upgrade" == false && -z "$binary_path" && -z "$requested_version" ]] || \
    die "-v (no arg) cannot be combined with other options"
  get_latest_version
  exit 0
fi

if $upgrade; then
  [[ -z "$binary_path" ]] || die "-u cannot be used with -b/--binary"
  [[ -z "$requested_version" ]] || die "-u cannot be combined with -v"
  latest=$(get_latest_version)
  if command -v "$APP" >/dev/null 2>&1; then
    installed=$("$APP" -v 2>/dev/null || true)
    installed="${installed#v}"
    if [[ -n "$installed" && "$installed" == "$latest" ]]; then
      info "${APP} ${latest} already installed"
      exit 0
    fi
  fi
  requested_version="$latest"
fi

[[ -n "$binary_path" || "$(uname -s)" == "Linux" ]] || die "Unsupported OS: $(uname -s)"
[[ -n "$binary_path" || "$(uname -m)" == "x86_64" ]] || die "Unsupported arch: $(uname -m)"
command -v curl >/dev/null 2>&1 || die "'curl' is required"
command -v tar >/dev/null 2>&1 || die "'tar' is required"
command -v python3 >/dev/null 2>&1 || die "'python3' is required"

mkdir -p "$INSTALL_DIR"

if [[ -n "$binary_path" ]]; then
  [[ -f "$binary_path" ]] || die "Bundle not found: $binary_path"
  info "Installing ${APP^^} from local release bundle"
  tmp_dir=$(mktemp -d "${TMPDIR:-/tmp}/${APP}.XXXXXX")
  cp "$binary_path" "$tmp_dir/$FILENAME"
else
  if [[ -z "$requested_version" ]]; then
    version_label=$(get_latest_version)
    url="https://github.com/${REPO}/releases/latest/download/${FILENAME}"
  else
    requested_version="${requested_version#v}"
    version_label="$requested_version"
    url="https://github.com/${REPO}/releases/download/v${requested_version}/${FILENAME}"
    http_status=$(curl -sI -o /dev/null -w "%{http_code}" \
      "https://github.com/${REPO}/releases/tag/v${requested_version}")
    [[ "$http_status" != "404" ]] || die "Release v${requested_version} not found"
  fi

  if command -v "$APP" >/dev/null 2>&1 && [[ -n "${version_label:-}" ]]; then
    installed=$("$APP" -v 2>/dev/null || true)
    installed="${installed#v}"
    if [[ -n "$installed" && "$installed" == "$version_label" ]]; then
      info "${APP} ${version_label} already installed"
      exit 0
    fi
  fi

  info "Installing ${APP^^} version ${version_label}"
  tmp_dir=$(mktemp -d "${TMPDIR:-/tmp}/${APP}.XXXXXX")
  curl -# -L -o "$tmp_dir/$FILENAME" "$url"
fi

tar -xzf "$tmp_dir/$FILENAME" -C "$tmp_dir"
[[ -f "$tmp_dir/${APP}/main.py" ]] || die "Archive missing ${APP}/main.py"
[[ -f "$tmp_dir/${APP}/_version.py" ]] || die "Archive missing ${APP}/_version.py"
[[ -f "$tmp_dir/${APP}/install.sh" ]] || die "Archive missing ${APP}/install.sh"

rm -rf "$APP_DIR"
mkdir -p "$APP_DIR"
mv "$tmp_dir/${APP}" "$APP_DIR"
rm -rf "$tmp_dir"

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --disable-pip-version-check -U pip
if [[ -f "$APP_DIR/${APP}/requirements.txt" ]]; then
  "$VENV_DIR/bin/pip" install --disable-pip-version-check -r "$APP_DIR/${APP}/requirements.txt"
fi

cat > "$INSTALL_DIR/$APP" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec "${HOME}/.${APP}/venv/bin/python" "${HOME}/.${APP}/app/${APP}/main.py" "\$@"
EOF
chmod 755 "$INSTALL_DIR/$APP"

write_tmux_snippet() {
  mkdir -p "$TMUX_SNIPPET_DIR"
  {
    echo "# Managed by tm install.sh"
    declare -A seen=()
    local key
    for key in "$tmux_index_key" "$previous_tmux_index_key" "C-i" "Tab" "C-Insert" "Insert" "F8" "F9" "F12"; do
      [[ -n "$key" ]] || continue
      if [[ -n "${seen[$key]:-}" ]]; then
        continue
      fi
      seen["$key"]=1
      printf 'unbind -n %s\n' "$key"
    done
    printf 'bind -n %s switch-client -t index\n' "$tmux_index_key"
  } > "$TMUX_SNIPPET_FILE"
}

ensure_tmux_config_sources_snippet() {
  local tmux_conf="$HOME/.tmux.conf"
  local source_line="source-file $TMUX_SNIPPET_FILE"
  local tmp

  if [[ ! -e "$tmux_conf" ]]; then
    touch "$tmux_conf"
  fi

  tmp=$(mktemp "${TMPDIR:-/tmp}/${APP}-tmux-conf.XXXXXX")
  python3 - "$tmux_conf" "$tmp" "$source_line" <<'PY'
from pathlib import Path
import sys

tmux_conf = Path(sys.argv[1])
tmp = Path(sys.argv[2])
source_line = sys.argv[3]
legacy_lines = {
    "unbind -n C-Insert",
    "bind -n C-Insert switch-client -t index",
    "unbind -n Insert",
    "bind -n Insert switch-client -t index",
}

existing = tmux_conf.read_text() if tmux_conf.exists() else ""
lines = [line for line in existing.splitlines() if line.strip() not in legacy_lines]
while lines and lines[-1] == "":
    lines.pop()
if source_line not in lines:
    if lines:
        lines.append("")
    lines.append(f"# {Path(source_line.split(maxsplit=1)[1]).stem.upper()}")
    lines.append(source_line)
tmp.write_text("\n".join(lines) + "\n")
PY
  mv "$tmp" "$tmux_conf"
}

write_tmux_snippet
ensure_tmux_config_sources_snippet
info "Managed tmux index shortcut with key ${tmux_index_key}"

maybe_add_path() {
  local command=$1
  local rc_files=()
  local shell_name
  shell_name=$(basename "${SHELL:-bash}")
  case "$shell_name" in
    zsh) rc_files=("$HOME/.zshrc" "$HOME/.zshenv" "$HOME/.config/zsh/.zshrc") ;;
    bash) rc_files=("$HOME/.bashrc" "$HOME/.bash_profile" "$HOME/.profile") ;;
    fish) rc_files=("$HOME/.config/fish/config.fish") ;;
    *) rc_files=("$HOME/.profile") ;;
  esac
  for rc in "${rc_files[@]}"; do
    if [[ ! -e "$rc" ]]; then
      mkdir -p "$(dirname "$rc")"
      touch "$rc"
    fi
    [[ -w "$rc" ]] || continue
    if grep -Fq "$command" "$rc" 2>/dev/null; then
      return
    fi
    printf '\n# %s\n%s\n' "${APP^^}" "$command" >> "$rc"
    info "Added ${APP^^} to PATH in $rc"
    return
  done
  info "Add to PATH manually: $command"
}

if ! $no_modify_path && [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
  if [[ $(basename "${SHELL:-bash}") == "fish" ]]; then
    maybe_add_path "fish_add_path $INSTALL_DIR"
  else
    maybe_add_path "export PATH=$INSTALL_DIR:\$PATH"
  fi
fi

info "Installed ${APP^^} to $INSTALL_DIR/$APP"
info "Run: ${APP} -h"
