TMUX_SNIPPET_DIR="$HOME/.tmux"
TMUX_SNIPPET_FILE="$TMUX_SNIPPET_DIR/${APP}.conf"
tmux_index_key=${TMUX_INDEX_KEY:-C-Insert}
previous_tmux_index_key=""

if [[ -f "$TMUX_SNIPPET_FILE" ]]; then
  previous_tmux_index_key=$(sed -n 's/^bind -n \(.*\) switch-client -t index$/\1/p' "$TMUX_SNIPPET_FILE" | tail -n 1)
fi
