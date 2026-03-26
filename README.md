# Codex iTerm Pane Labels

Show a live task summary for each Codex pane in iTerm2.

This setup does three things:

- wraps `codex` in `zsh` so each pane starts a watcher
- reads the active Codex session for that pane
- writes a short task summary into iTerm's title channels and `user.task`

## What You Get

Each pane can show a different live label such as:

- `Fixing OAuth callback loop`
- `Adding iTerm pane title updates`
- `Reviewing failing sync job`

The label is written to:

- the iTerm badge via `\(user.task)`
- the iTerm status bar via `\(user.task)`
- the shell-driven title channels (`OSC 0`, `OSC 1`, `OSC 2`) that iTerm can use for pane, tab, and window titles

## Requirements

- macOS
- iTerm2
- `zsh`
- `python3`
- Codex installed and writing sessions under `~/.codex/sessions`
- `OPENAI_API_KEY` if you want LLM-generated summaries

Without `OPENAI_API_KEY`, the pane label still works, but it falls back to a heuristic summary.

## Quick Install

From this repo:

```zsh
./install.sh
source ~/.zshrc
```

If Codex is already running in a pane, exit that Codex process and start it again after reloading `~/.zshrc`.

## Manual Install

If you do not want to run the installer script, do it by hand:

1. Create `~/.codex` if it does not exist.
2. Copy [codex_pane_summary.py](./codex_pane_summary.py) to `~/.codex/codex_pane_summary.py`.
3. Copy [iterm-pane-labels.zsh](./iterm-pane-labels.zsh) to `~/.codex/iterm-pane-labels.zsh`.
4. Make the Python script executable:

```zsh
chmod +x ~/.codex/codex_pane_summary.py
```

5. Add this block to `~/.zshrc`:

```zsh
# >>> codex iterm pane labels >>>
if [ -f "$HOME/.codex/iterm-pane-labels.zsh" ]; then
  source "$HOME/.codex/iterm-pane-labels.zsh"
fi
# <<< codex iterm pane labels <<<
```

6. Reload your shell:

```zsh
source ~/.zshrc
```

7. Restart any already-running `codex` process in open panes.

## iTerm2 Setup

Use the same iTerm2 profile you run Codex in.

### Badge

1. Open `iTerm2 > Settings > Profiles`.
2. Select your Codex profile.
3. Open `General`.
4. Set `Badge` to:

```text
\(user.task)
```

This is the most reliable visible display because it reads the iTerm user variable directly.

### Status Bar

1. In the same profile, open `Terminal`.
2. Turn on `Show status bar` if you want a label visible inside each pane.
3. Open the status bar configuration.
4. Add a `String` component.
5. Set its expression to:

```text
\(user.task)
```

This gives each pane its own live task label in the pane itself.

### Pane, Tab, and Window Titles

The shell hook also emits updates to `OSC 0`, `OSC 1`, and `OSC 2`.

That means iTerm can pick up the live task label for:

- session or pane title
- tab title
- window title

Exact visibility depends on your iTerm layout and profile preferences. If your current iTerm setup already shows session, tab, or window titles, this hook updates those titles automatically. If you do not currently show them, the badge and status bar settings above are enough to make the labels visible.

### Recommended iTerm Setup

If you want the clearest result, use all three:

- `Badge = \(user.task)`
- status bar string component = `\(user.task)`
- your normal tab/window title display enabled in iTerm

That way each pane has:

- an always-visible in-pane label
- a tab/window title that tracks the active task

## How It Works

When you run `codex` in a pane:

1. the `zsh` wrapper starts a small background watcher for that tty
2. the watcher finds the matching Codex session file
3. it summarizes recent user asks and assistant progress
4. it writes the result back to iTerm for that pane only

The watcher polls every 4 seconds while `codex` is running in that pane.

## Files Installed

- `~/.codex/codex_pane_summary.py`
- `~/.codex/iterm-pane-labels.zsh`
- a small `source` block in `~/.zshrc`

## Manual Overrides

Set a manual label for the current shell:

```zsh
pane_task "Investigating auth redirect loop"
```

Clear it:

```zsh
pane_task_clear
```

If a repo contains a `.codex-task` file, its first line is used as a manual fallback when there is no active pane-specific summary.

## Remove

Delete:

- `~/.codex/codex_pane_summary.py`
- `~/.codex/iterm-pane-labels.zsh`

Then remove this block from `~/.zshrc`:

```text
# >>> codex iterm pane labels >>>
# <<< codex iterm pane labels <<<
```
