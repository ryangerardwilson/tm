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

MUTED='\033[0;2m'
RED='\033[0;31m'
ORANGE='\033[38;5;214m'
NC='\033[0m'

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
      --tmux-key <key>       Bind the index-session shortcut in tmux (default: M-i)

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
  local color="${NC}"
  [[ "$level" == "error" ]] && color="${RED}"
  echo -e "${color}${message}${NC}"
}

die() {
  print_message error "$1"
  exit 1
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
tmux_index_key=${TMUX_INDEX_KEY:-M-i}
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
      [[ -n "${2:-}" ]] || { echo -e "${RED}Error: -b requires a path${NC}"; exit 1; }
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
      echo -e "${ORANGE}Warning: Unknown option '$1'${NC}" >&2
      shift
      ;;
  esac
done

case "$tmux_index_key" in
  M-d|M-h|M--)
    die "--tmux-key ${tmux_index_key} conflicts with reserved tmux root bindings (M-d, M-h, M--, M-\\)"
    ;;
esac
if [[ "$tmux_index_key" == "M-\\" ]]; then
  die "--tmux-key ${tmux_index_key} conflicts with reserved tmux root bindings (M-d, M-h, M--, M-\\)"
fi

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
      print_message info "${MUTED}${APP} version ${NC}${requested_version}${MUTED} already installed${NC}"
      exit 0
    fi
  fi
fi

command -v python3 >/dev/null 2>&1 || { print_message error "'python3' is required but not installed."; exit 1; }
mkdir -p "$INSTALL_DIR" "$APP_DIR"
tmp_dir="${TMPDIR:-/tmp}/${APP}_install_$$"
rm -rf "$tmp_dir"
mkdir -p "$tmp_dir"
trap 'rm -rf "$tmp_dir"' EXIT

if [[ -n "$binary_path" ]]; then
  [[ -e "$binary_path" ]] || { print_message error "Source bundle not found: $binary_path"; exit 1; }
  print_message info "\n${MUTED}Installing ${NC}${APP}${MUTED} from local source: ${NC}${binary_path}"
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
      print_message info  "${MUTED}See available releases: ${NC}https://github.com/${REPO}/releases"
      exit 1
    fi
  fi

  if command -v "${APP}" >/dev/null 2>&1; then
    installed_version="$(${APP} -v 2>/dev/null || true)"
    installed_version="${installed_version#v}"
    if [[ -n "$installed_version" && "$installed_version" == "$specific_version" ]]; then
      print_message info "${MUTED}${APP} version ${NC}${specific_version}${MUTED} already installed${NC}"
      exit 0
    fi
  fi

  url="https://github.com/${REPO}/releases/download/v${specific_version}/${FILENAME}"
  print_message info "\n${MUTED}Installing ${NC}${APP} ${MUTED}version: ${NC}${specific_version}"
  curl -# -L -o "$tmp_dir/$FILENAME" "$url"
  extract_source "$tmp_dir/$FILENAME" "$SOURCE_DIR"
fi

[[ -f "${SOURCE_DIR}/main.py" ]] || die "Source bundle missing main.py"
[[ -f "${SOURCE_DIR}/_version.py" ]] || die "Source bundle missing _version.py"

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --disable-pip-version-check -U pip >/dev/null
if [[ -f "${SOURCE_DIR}/requirements.txt" ]]; then
  "$VENV_DIR/bin/pip" install --disable-pip-version-check -r "${SOURCE_DIR}/requirements.txt" >/dev/null
fi

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
    echo "unbind -n 'M-\\'"
    declare -A seen=()
    local key
    for key in "$tmux_index_key" "$previous_tmux_index_key" "M--" "M-d" "M-h" "M-i" "M-v" "C-i" "Tab" "C-DC" "C-Home" "C-End" "C-Insert" "Insert" "F8" "F9" "F12"; do
      [[ -n "$key" ]] || continue
      if [[ -n "${seen[$key]:-}" ]]; then
        continue
      fi
      seen["$key"]=1
      printf 'unbind -n %s\n' "$key"
    done
    printf 'bind -n %s switch-client -t index\n' "$tmux_index_key"
    echo 'bind -n M-h select-pane -L'
    echo "bind -n 'M-\\' split-window -h"
    echo 'bind -n M-- split-window -v'
    echo 'bind -n M-d kill-pane'
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

reload_running_tmux_snippet() {
  if command -v tmux >/dev/null 2>&1 && tmux ls >/dev/null 2>&1; then
    tmux source-file "$TMUX_SNIPPET_FILE" >/dev/null 2>&1 || true
  fi
}

reload_running_tmux_snippet

add_to_path() {
  local config_file=$1
  local command=$2

  if grep -Fxq "$command" "$config_file" 2>/dev/null; then
    print_message info "${MUTED}PATH entry already present in ${NC}$config_file"
  elif [[ -w "$config_file" ]]; then
    {
      echo ""
      echo "# ${APP}"
      echo "$command"
    } >> "$config_file"
    print_message info "${MUTED}Added ${NC}${APP}${MUTED} to PATH in ${NC}$config_file"
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
      print_message info "${MUTED}No shell config file found. Manually add:${NC}"
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

print_message info "${MUTED}Run:${NC} ${APP} -h"
