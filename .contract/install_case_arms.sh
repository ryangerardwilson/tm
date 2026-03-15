    --tmux-key)
      [[ -n "${2:-}" ]] || die "--tmux-key requires a tmux key name"
      tmux_index_key="$2"
      shift 2
      ;;
