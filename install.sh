#!/usr/bin/env bash
set -euo pipefail

APP=tm
APP_HOME="$HOME/.${APP}"
INSTALL_DIR="$APP_HOME/bin"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION_FILE="$SOURCE_DIR/_version.py"

usage() {
  cat <<EOF
TM Installer

Usage: install.sh [options]

Options:
  -h                 Show this help and exit
  -v                 Print the source version and exit
  -v <version>       Install only if the requested version matches this checkout
  -u                 Reinstall the current checkout
  --no-modify-path   Skip editing shell rc files
EOF
}

die() {
  printf '%s\n' "$1" >&2
  exit 1
}

version_from_source() {
  sed -n 's/^__version__ = "\(.*\)"/\1/p' "$VERSION_FILE"
}

requested_version=""
show_version=false
no_modify_path=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h)
      usage
      exit 0
      ;;
    -v)
      if [[ -n "${2:-}" && "${2:0:1}" != "-" ]]; then
        requested_version="$2"
        shift 2
      else
        show_version=true
        shift
      fi
      ;;
    -u)
      shift
      ;;
    --no-modify-path)
      no_modify_path=true
      shift
      ;;
    *)
      die "Unknown option: $1"
      ;;
  esac
done

source_version="$(version_from_source)"
[[ -n "$source_version" ]] || die "Unable to read source version"

if $show_version; then
  [[ -z "$requested_version" ]] || die "-v cannot be combined with another version request"
  printf '%s\n' "$source_version"
  exit 0
fi

if [[ -n "$requested_version" ]]; then
  requested_version="${requested_version#v}"
  [[ "$requested_version" == "$source_version" ]] || die "This checkout provides version $source_version, not $requested_version"
fi

mkdir -p "$INSTALL_DIR"

cat > "$INSTALL_DIR/$APP" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec python3 "$SOURCE_DIR/main.py" "\$@"
EOF
chmod 755 "$INSTALL_DIR/$APP"

maybe_add_path() {
  local command=$1
  local shell_name
  local rc_file
  shell_name=$(basename "${SHELL:-bash}")
  case "$shell_name" in
    zsh) rc_file="$HOME/.zshrc" ;;
    fish) rc_file="$HOME/.config/fish/config.fish" ;;
    *) rc_file="$HOME/.bashrc" ;;
  esac
  mkdir -p "$(dirname "$rc_file")"
  touch "$rc_file"
  if grep -Fq "$command" "$rc_file" 2>/dev/null; then
    return
  fi
  printf '\n# TM\n%s\n' "$command" >> "$rc_file"
}

if ! $no_modify_path && [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
  if [[ $(basename "${SHELL:-bash}") == "fish" ]]; then
    maybe_add_path "fish_add_path $INSTALL_DIR"
  else
    maybe_add_path "export PATH=$INSTALL_DIR:\$PATH"
  fi
fi

printf 'Installed tm to %s/%s\n' "$INSTALL_DIR" "$APP"
