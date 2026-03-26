# iTerm2 per-pane task labeling helpers for Codex.
autoload -Uz add-zsh-hook

export CODEX_PANE_SUMMARY_SCRIPT="$HOME/.codex/codex_pane_summary.py"
typeset -g _CODEX_PANE_WATCHER_PID=""
: "${CODEX_PANE_SUMMARY_POLL_INTERVAL:=15}"

_it2_b64() {
  printf '%s' "$1" | base64 | tr -d '\n'
}

_it2_set_user_var() {
  local name="$1"
  local value="${2//$'\n'/ }"
  printf '\033]1337;SetUserVar=%s=%s\007' "$name" "$(_it2_b64 "$value")"
}

_it2_set_title() {
  local text="${1//$'\n'/ }"
  printf '\033]0;%s\007' "$text"
  printf '\033]1;%s\007' "$text"
  printf '\033]2;%s\007' "$text"
}

pane_task() {
  local text="${*//$'\n'/ }"
  export PANE_TASK="$text"
  _it2_set_title "$text"
  _it2_set_user_var task "$text"
}

pane_task_clear() {
  unset PANE_TASK
  _it2_set_title ""
  _it2_set_user_var task ""
}

_pane_task_git_root() {
  git rev-parse --show-toplevel 2>/dev/null
}

_pane_task_git_branch() {
  git symbolic-ref --short HEAD 2>/dev/null || git rev-parse --short HEAD 2>/dev/null
}

_pane_task_file_summary() {
  local git_root
  git_root="$(_pane_task_git_root)"
  [[ -n "$git_root" ]] || return 1

  local task_file="$git_root/.codex-task"
  [[ -f "$task_file" ]] || return 1

  sed -n '1p' "$task_file"
}

_pane_task_context_summary() {
  if [[ -n "$PANE_TASK" ]]; then
    printf '%s\n' "$PANE_TASK"
    return
  fi

  local file_summary
  file_summary="$(_pane_task_file_summary)"
  if [[ -n "$file_summary" ]]; then
    printf '%s\n' "$file_summary"
    return
  fi

  if [[ -x "$CODEX_PANE_SUMMARY_SCRIPT" ]]; then
    local llm_summary
    local tty_path
    tty_path="$(tty 2>/dev/null)"
    if [[ "$tty_path" == /dev/* ]]; then
      llm_summary="$(python3 "$CODEX_PANE_SUMMARY_SCRIPT" --cwd "$PWD" --tty "$tty_path" --quick 2>/dev/null)"
    else
      llm_summary="$(python3 "$CODEX_PANE_SUMMARY_SCRIPT" --cwd "$PWD" --quick 2>/dev/null)"
    fi
    if [[ -n "$llm_summary" ]]; then
      printf '%s\n' "$llm_summary"
      return
    fi
  fi

  local git_root branch repo
  git_root="$(_pane_task_git_root)"
  if [[ -n "$git_root" ]]; then
    repo="${git_root:t}"
    branch="$(_pane_task_git_branch)"
    if [[ -n "$branch" ]]; then
      printf 'Codex: %s [%s]\n' "$repo" "$branch"
    else
      printf 'Codex: %s\n' "$repo"
    fi
    return
  fi

  printf 'Codex: %s\n' "${PWD:t}"
}

_pane_task_refresh() {
  local summary
  summary="$(_pane_task_context_summary)"
  _it2_set_title "$summary"
  _it2_set_user_var task "$summary"
}

_pane_task_precmd() {
  _pane_task_refresh
}

_pane_task_preexec() {
  local command_text="${1//$'\n'/ }"
  case "$command_text" in
    codex*|cx\ *)
      _pane_task_refresh
      ;;
  esac
}

add-zsh-hook precmd _pane_task_precmd
add-zsh-hook preexec _pane_task_preexec

_codex_pane_watcher_stop() {
  if [[ -n "$_CODEX_PANE_WATCHER_PID" ]] && kill -0 "$_CODEX_PANE_WATCHER_PID" 2>/dev/null; then
    kill "$_CODEX_PANE_WATCHER_PID" 2>/dev/null
    wait "$_CODEX_PANE_WATCHER_PID" 2>/dev/null
  fi
  _CODEX_PANE_WATCHER_PID=""
}

_codex_pane_watcher_start() {
  [[ -x "$CODEX_PANE_SUMMARY_SCRIPT" ]] || return

  local tty_path
  tty_path="$(tty 2>/dev/null)"
  [[ "$tty_path" == /dev/* ]] || return

  _codex_pane_watcher_stop
  python3 "$CODEX_PANE_SUMMARY_SCRIPT" --cwd "$PWD" --tty "$tty_path" --watch --interval "$CODEX_PANE_SUMMARY_POLL_INTERVAL" >/dev/null 2>&1 &
  _CODEX_PANE_WATCHER_PID=$!
}

_llm_pane_watcher_start_for_agent() {
  _pane_task_refresh
  _codex_pane_watcher_start
}

_llm_pane_watcher_stop_for_agent() {
  local exit_code=$1
  _codex_pane_watcher_stop
  _pane_task_refresh
  return $exit_code
}

codex() {
  _llm_pane_watcher_start_for_agent
  command codex "$@"
  local exit_code=$?
  _llm_pane_watcher_stop_for_agent $exit_code
}

claude() {
  _llm_pane_watcher_start_for_agent
  command claude "$@"
  local exit_code=$?
  _llm_pane_watcher_stop_for_agent $exit_code
}

cc() {
  _llm_pane_watcher_start_for_agent
  command claude "$@"
  local exit_code=$?
  _llm_pane_watcher_stop_for_agent $exit_code
}

cx() {
  local summary="$1"
  shift
  pane_task "$summary"
  _pane_task_refresh
  command codex "$@"
  local exit_code=$?
  _llm_pane_watcher_stop_for_agent $exit_code
}
