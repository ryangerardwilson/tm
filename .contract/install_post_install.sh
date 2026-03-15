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
