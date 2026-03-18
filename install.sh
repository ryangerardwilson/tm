#!/usr/bin/env bash
set -euo pipefail

APP=tm
REPO="ryangerardwilson/tm"
APP_HOME="$HOME/.${APP}"
INSTALL_DIR="$APP_HOME/bin"
APP_DIR="$APP_HOME/app"
SOURCE_DIR="$APP_DIR/source"
VENV_DIR="$APP_HOME/venv"
FILENAME="tm-linux-x64.tar.gz"

usage() {
  cat <<EOF
${APP} Installer

Usage: install.sh [options]

Options:
  -h                         Show this help and exit
  -v [<version>]             Print the latest release version, or install a specific one
  -u                         Upgrade to the latest release only when newer
  -b <path>                  Install from a local checkout or source bundle
  -n                         Do not modify shell config to add to PATH
      --tmux-key <key>       Bind the index-session shortcut in tmux (default: C-Insert)

      --help                 Compatibility alias for -h
      --version [<version>]  Compatibility alias for -v
      --upgrade              Compatibility alias for -u
      --binary <path>        Compatibility alias for -b
      --no-modify-path       Compatibility alias for -n
EOF
}

requested_version=${VERSION:-}
show_latest=false
upgrade=false
no_modify_path=false
binary_path=""
latest_version_cache=""

print_message() {
  local level=$1
  local message=$2
  printf '%b\n' "$message"
}

die() {
  print_message error "$1"
  exit 1
}

create_venv() {
  local venv_log="$tmp_dir/venv-create.log"

  rm -rf "$VENV_DIR"
  if "$PYTHON_BIN" -m venv --without-pip "$VENV_DIR" >"$venv_log" 2>&1; then
    return 0
  fi

  rm -rf "$VENV_DIR"
  if command -v virtualenv >/dev/null 2>&1; then
    if virtualenv --python "$PYTHON_BIN" --without-pip "$VENV_DIR" >"$venv_log" 2>&1; then
      return 0
    fi
  fi

  if [[ -s "$venv_log" ]]; then
    cat "$venv_log" >&2
  fi
  if command -v virtualenv >/dev/null 2>&1; then
    die "Unable to create virtual environment with python3 -m venv or virtualenv."
  fi
  die "Unable to create virtual environment with python3 -m venv. Install python3-venv or virtualenv."
}

extract_source() {
  local src_path="$1"
  local out_dir="$2"

  rm -rf "$out_dir"
  mkdir -p "$out_dir"

  if [[ -d "$src_path" ]]; then
    cp -R "$src_path"/. "$out_dir"/
  else
    command -v tar >/dev/null 2>&1 || die "'tar' is required but not installed."
    tar -xzf "$src_path" -C "$tmp_dir"
    local extracted
    extracted="$(find "$tmp_dir" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
    [[ -n "$extracted" ]] || die "Failed to extract source bundle"
    cp -R "$extracted"/. "$out_dir"/
  fi

  rm -rf "$out_dir/.git" "$out_dir/.ruff_cache" "$out_dir/.pytest_cache"
  find "$out_dir" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
}

get_latest_version() {
  command -v curl >/dev/null 2>&1 || die "'curl' is required but not installed."
  if [[ -z "$latest_version_cache" ]]; then
    local release_url
    local tag
    release_url="$(curl -fsSL -o /dev/null -w "%{url_effective}" "https://github.com/${REPO}/releases/latest")" \
      || die "Unable to determine latest release"
    tag="${release_url##*/}"
    tag="${tag#v}"
    [[ -n "$tag" && "$tag" != "latest" ]] || die "Unable to determine latest release"
    latest_version_cache="$tag"
  fi
  printf '%s\n' "$latest_version_cache"
}

TMUX_SNIPPET_DIR="$HOME/.tmux"
TMUX_SNIPPET_FILE="$TMUX_SNIPPET_DIR/${APP}.conf"
TMUX_APP_BIN="$INSTALL_DIR/$APP"
tmux_index_key=${TMUX_INDEX_KEY:-C-Insert}
previous_tmux_index_key=""
tmux_index_run_shell_command="$(
  python3 - "$TMUX_APP_BIN" <<'PY'
import shlex
import sys

client_tty = "#{client_tty}"
print(f"TMUX_CLIENT_TTY={shlex.quote(client_tty)} {shlex.quote(sys.argv[1])} >/dev/null 2>&1")
PY
)"

detect_previous_tmux_index_key() {
  python3 - "$1" "$2" <<'PY'
from pathlib import Path
import shlex
import sys

snippet_path = Path(sys.argv[1])
app_bin = sys.argv[2]
legacy_action = "switch-client -t index"
current_action = f'run-shell "{shlex.quote(app_bin)} >/dev/null 2>&1"'
client_tty_action = f'run-shell "TMUX_CLIENT_TTY={shlex.quote("#{client_tty}")} {shlex.quote(app_bin)} >/dev/null 2>&1"'

for raw_line in reversed(snippet_path.read_text(encoding="utf-8").splitlines()):
    line = raw_line.strip()
    if not line.startswith("bind -n "):
        continue
    try:
        key, action = line[len("bind -n ") :].split(" ", 1)
    except ValueError:
        continue
    if action in {legacy_action, current_action, client_tty_action}:
        print(key)
        break
PY
}

if [[ -f "$TMUX_SNIPPET_FILE" ]]; then
  previous_tmux_index_key="$(detect_previous_tmux_index_key "$TMUX_SNIPPET_FILE" "$TMUX_APP_BIN")"
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    -v|--version)
      if [[ -n "${2:-}" && "${2:0:1}" != "-" ]]; then
        requested_version="${2#v}"
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
      [[ -n "${2:-}" ]] || { echo "Error: -b requires a path"; exit 1; }
      binary_path="$2"
      shift 2
      ;;
    -n|--no-modify-path)
      no_modify_path=true
      shift
      ;;
    --tmux-key)
      [[ -n "${2:-}" ]] || die "--tmux-key requires a tmux key name"
      tmux_index_key="$2"
      shift 2
      ;;

    *)
      echo "Warning: Unknown option '$1'" >&2
      shift
      ;;
  esac
done

if $show_latest; then
  [[ "$upgrade" == false && -z "$binary_path" && -z "$requested_version" ]] || \
    die "-v (no arg) cannot be combined with other options"
  get_latest_version
  exit 0
fi

if $upgrade; then
  [[ -z "$binary_path" ]] || die "-u cannot be used with -b"
  [[ -z "$requested_version" ]] || die "-u cannot be combined with -v <version>"
  requested_version="$(get_latest_version)"
  if command -v "${APP}" >/dev/null 2>&1; then
    installed_version="$(${APP} -v 2>/dev/null || true)"
    installed_version="${installed_version#v}"
    if [[ -n "$installed_version" && "$installed_version" == "$requested_version" ]]; then
      print_message info "${APP} version ${requested_version} already installed"
      exit 0
    fi
  fi
fi

command -v python3 >/dev/null 2>&1 || { print_message error "'python3' is required but not installed."; exit 1; }
PYTHON_BIN="$(command -v python3)"
mkdir -p "$INSTALL_DIR" "$APP_DIR"
tmp_dir="${TMPDIR:-/tmp}/${APP}_install_$$"
rm -rf "$tmp_dir"
mkdir -p "$tmp_dir"
trap 'rm -rf "$tmp_dir"' EXIT

if [[ -n "$binary_path" ]]; then
  [[ -e "$binary_path" ]] || { print_message error "Source bundle not found: $binary_path"; exit 1; }
  print_message info "\nInstalling ${APP} from local source: ${binary_path}"
  extract_source "$binary_path" "$SOURCE_DIR"
  specific_version="local"
else
  command -v curl >/dev/null 2>&1 || { print_message error "'curl' is required but not installed."; exit 1; }

  if [[ -z "$requested_version" ]]; then
    specific_version="$(get_latest_version)"
  else
    requested_version="${requested_version#v}"
    specific_version="${requested_version}"
    http_status=$(curl -sI -o /dev/null -w "%{http_code}" "https://github.com/${REPO}/releases/tag/v${requested_version}")
    if [[ "$http_status" == "404" ]]; then
      print_message error "Release v${requested_version} not found"
      print_message info "See available releases: https://github.com/${REPO}/releases"
      exit 1
    fi
  fi

  if command -v "${APP}" >/dev/null 2>&1; then
    installed_version="$(${APP} -v 2>/dev/null || true)"
    installed_version="${installed_version#v}"
    if [[ -n "$installed_version" && "$installed_version" == "$specific_version" ]]; then
      print_message info "${APP} version ${specific_version} already installed"
      exit 0
    fi
  fi

  url="https://github.com/${REPO}/releases/download/v${specific_version}/${FILENAME}"
  print_message info "\nInstalling ${APP} version: ${specific_version}"
  curl -# -L -o "$tmp_dir/$FILENAME" "$url"
  extract_source "$tmp_dir/$FILENAME" "$SOURCE_DIR"
fi

[[ -f "${SOURCE_DIR}/main.py" ]] || die "Source bundle missing main.py"
[[ -f "${SOURCE_DIR}/_version.py" ]] || die "Source bundle missing _version.py"

create_venv

cat > "${INSTALL_DIR}/${APP}" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec "${VENV_DIR}/bin/python" "${SOURCE_DIR}/main.py" "\$@"
EOF
chmod 755 "${INSTALL_DIR}/${APP}"

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
    printf 'bind -n %s run-shell "%s"\n' "$tmux_index_key" "$tmux_index_run_shell_command"
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

add_to_path() {
  local config_file=$1
  local command=$2

  if grep -Fxq "$command" "$config_file" 2>/dev/null; then
    print_message info "PATH entry already present in $config_file"
  elif [[ -w "$config_file" ]]; then
    {
      echo ""
      echo "# ${APP}"
      echo "$command"
    } >> "$config_file"
    print_message info "Added ${APP} to PATH in $config_file"
  else
    print_message info "Add this to your shell config:"
    print_message info "  $command"
  fi
}

if [[ "$no_modify_path" != "true" ]]; then
  if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
    XDG_CONFIG_HOME=${XDG_CONFIG_HOME:-$HOME/.config}
    current_shell=$(basename "${SHELL:-bash}")

    case "$current_shell" in
      zsh)  config_candidates=("$HOME/.zshrc" "$HOME/.zshenv" "$XDG_CONFIG_HOME/zsh/.zshrc" "$XDG_CONFIG_HOME/zsh/.zshenv") ;;
      bash) config_candidates=("$HOME/.bashrc" "$HOME/.bash_profile" "$HOME/.profile" "$XDG_CONFIG_HOME/bash/.bashrc" "$XDG_CONFIG_HOME/bash/.bash_profile") ;;
      fish) config_candidates=("$HOME/.config/fish/config.fish") ;;
      *)    config_candidates=("$HOME/.profile" "$HOME/.bashrc") ;;
    esac

    config_file=""
    for f in "${config_candidates[@]}"; do
      if [[ -f "$f" ]]; then
        config_file="$f"
        break
      fi
    done

    if [[ -z "$config_file" ]]; then
      print_message info "No shell config file found. Manually add:"
      print_message info "  export PATH=$INSTALL_DIR:\$PATH"
    else
      if [[ "$current_shell" == "fish" ]]; then
        add_to_path "$config_file" "fish_add_path $INSTALL_DIR"
      else
        add_to_path "$config_file" "export PATH=$INSTALL_DIR:\$PATH"
      fi
    fi
  fi
fi

print_message info "Run: ${APP} -h"
