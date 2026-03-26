#!/usr/bin/env zsh

set -euo pipefail

SCRIPT_DIR="${0:A:h}"
CODEX_HOME="$HOME/.codex"
TARGET_SCRIPT="$CODEX_HOME/codex_pane_summary.py"
TARGET_HOOK="$CODEX_HOME/iterm-pane-labels.zsh"
ZSHRC="$HOME/.zshrc"
START_MARKER="# >>> llm iterm pane labels >>>"
END_MARKER="# <<< llm iterm pane labels <<<"

mkdir -p "$CODEX_HOME"

cp "$SCRIPT_DIR/codex_pane_summary.py" "$TARGET_SCRIPT"
cp "$SCRIPT_DIR/iterm-pane-labels.zsh" "$TARGET_HOOK"
chmod +x "$TARGET_SCRIPT"

touch "$ZSHRC"

if ! grep -Fq "$START_MARKER" "$ZSHRC"; then
  {
    printf '\n%s\n' "$START_MARKER"
    printf 'if [ -f "$HOME/.codex/iterm-pane-labels.zsh" ]; then\n'
    printf '  source "$HOME/.codex/iterm-pane-labels.zsh"\n'
    printf 'fi\n'
    printf '%s\n' "$END_MARKER"
  } >> "$ZSHRC"
fi

printf 'Installed:\n'
printf '  %s\n' "$TARGET_SCRIPT"
printf '  %s\n' "$TARGET_HOOK"
printf '\nNext steps:\n'
printf '  source ~/.zshrc\n'
printf '  restart any already-running codex process in open panes\n'
