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
PUBLIC_BIN_DIR="$HOME/.local/bin"
PUBLIC_LAUNCHER="$PUBLIC_BIN_DIR/${APP}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"


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
  printf '%b\n' "$message"
}

die() {
  print_message error "$1"
  exit 1
}

installed_command_path() {
  if command -v "${APP}" >/dev/null 2>&1; then
    command -v "${APP}"
    return 0
  fi
  if [[ -x "${INSTALL_DIR}/${APP}" ]]; then
    printf '%s\n' "${INSTALL_DIR}/${APP}"
    return 0
  fi
  if [[ -x "${PUBLIC_LAUNCHER}" ]]; then
    printf '%s\n' "${PUBLIC_LAUNCHER}"
    return 0
  fi
  return 1
}

read_installed_version() {
  local installed_cmd
  installed_cmd="$(installed_command_path)" || return 0
  "$installed_cmd" -v 2>/dev/null || true
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
TMUX_SNIPPET_FILE="${TMUX_SNIPPET_DIR}/tm.conf"
TMUX_ROOT_CONF="$HOME/.tmux.conf"
tmux_index_key=${TMUX_INDEX_KEY:-M-i}

write_public_launcher() {
  if [[ -e "$PUBLIC_LAUNCHER" && ! -L "$PUBLIC_LAUNCHER" && ! -f "$PUBLIC_LAUNCHER" ]]; then
    die "Refusing to overwrite non-file launcher: $PUBLIC_LAUNCHER"
  fi

  if [[ -L "$PUBLIC_LAUNCHER" ]]; then
    local resolved
    resolved="$(readlink -f "$PUBLIC_LAUNCHER" 2>/dev/null || true)"
    if [[ "$resolved" != "${INSTALL_DIR}/${APP}" ]]; then
      die "Refusing to overwrite existing symlink launcher: $PUBLIC_LAUNCHER"
    fi
  elif [[ -f "$PUBLIC_LAUNCHER" ]] && ! grep -Fq '# Managed by rgw_cli_contract local-bin launcher' "$PUBLIC_LAUNCHER" 2>/dev/null; then
    die "Refusing to overwrite existing launcher: $PUBLIC_LAUNCHER"
  fi

  mkdir -p "$PUBLIC_BIN_DIR"
  cat > "${PUBLIC_LAUNCHER}" <<EOF
#!/usr/bin/env bash
# Managed by rgw_cli_contract local-bin launcher
set -euo pipefail
exec "${INSTALL_DIR}/${APP}" "\$@"
EOF
  chmod 755 "${PUBLIC_LAUNCHER}"
}

resolve_tmux_template_path() {
  local candidate
  for candidate in "${SOURCE_DIR}/tmux.conf.template" "${SCRIPT_DIR}/tmux.conf.template"; do
    if [[ -f "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  die "Managed tmux template not found"
}

write_tmux_root_conf() {
  command -v python3 >/dev/null 2>&1 || die "'python3' is required but not installed."
  local template_path
  template_path="$(resolve_tmux_template_path)"
  python3 - "$template_path" "$TMUX_ROOT_CONF" "$tmux_index_key" "$PUBLIC_LAUNCHER" <<'PY'
from pathlib import Path
import sys

template_path = Path(sys.argv[1])
target_path = Path(sys.argv[2])
tmux_index_key = sys.argv[3]
public_launcher = sys.argv[4]

rendered = template_path.read_text(encoding="utf-8")
rendered = rendered.replace("__TMUX_INDEX_KEY__", tmux_index_key)
rendered = rendered.replace("__TM_PUBLIC_LAUNCHER__", public_launcher)
target_path.write_text(rendered, encoding="utf-8")
PY
}

remove_legacy_tmux_snippet() {
  rm -f "$TMUX_SNIPPET_FILE"
  rmdir "$TMUX_SNIPPET_DIR" 2>/dev/null || true
}

finalize_install() {
  write_public_launcher
  write_tmux_root_conf
  remove_legacy_tmux_snippet
}

print_manual_shell_steps() {
  local printed=false
  if [[ ":$PATH:" != *":$PUBLIC_BIN_DIR:"* ]]; then
    print_message info "Manually add to ~/.bashrc if needed: export PATH=$PUBLIC_BIN_DIR:\$PATH"
    printed=true
  fi
  if [[ "$printed" == "true" ]]; then
    print_message info "Reload your shell: source ~/.bashrc"
  fi
}

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
  installed_version="$(read_installed_version)"
  installed_version="${installed_version#v}"
  if [[ -n "$installed_version" && "$installed_version" == "$requested_version" ]]; then
    finalize_install
    print_manual_shell_steps
    print_message info "${APP} version ${requested_version} already installed"
    exit 0
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

  installed_version="$(read_installed_version)"
  installed_version="${installed_version#v}"
  if [[ -n "$installed_version" && "$installed_version" == "$specific_version" ]]; then
    finalize_install
    print_manual_shell_steps
    print_message info "${APP} version ${specific_version} already installed"
    exit 0
  fi

  url="https://github.com/${REPO}/releases/download/v${specific_version}/${FILENAME}"
  print_message info "\nInstalling ${APP} version: ${specific_version}"
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

finalize_install

print_manual_shell_steps
print_message info "Run: ${APP} -h"
