#!/usr/bin/env bash
# Restore the operator's global agent config onto a machine by symlinking home
# locations into this repo (dotfiles pattern — same as ~/bin -> infra/dgx/bin).
# Idempotent. Any existing real file is backed up before it is replaced.
# Secret-bearing config is NOT symlinked — see the printed template list.
# Full bootstrap sequence: ./setup-new-computer.md
# Cross-platform: macOS and Linux share every agent-config link; only the
# OS-specific block (install_macos / install_linux below) differs.
set -euo pipefail

WS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"     # workstation/ dir
# USAGE: ./install.sh [--dry-run]
#   Preview first, ALWAYS:  ./install.sh --dry-run   (or:  DRY=1 ./install.sh)
#   A bare `./install.sh` RUNS FOR REAL — it backs up each live file to
#   *.bak.<ts> and replaces it with a symlink into this repo. There is no
#   confirm prompt, so run --dry-run first and read the BACK/LINK lines.
DRY="${DRY:-0}"                       # honour `DRY=1 ./install.sh` too
[ "${1:-}" = "--dry-run" ] && DRY=1
TS="$(date +%Y%m%d-%H%M%S)"
# Platform: detected from uname. WS_OS=macos|linux overrides it, so either
# platform's plan can be previewed from the other (pair it with --dry-run).
case "$(uname -s)" in
  Darwin) _os=macos ;;
  Linux)  _os=linux ;;
  *)      _os=unknown ;;
esac
OS="${WS_OS:-$_os}"
case "$OS" in
  macos|linux) ;;
  *) echo "unsupported platform: $OS (set WS_OS=macos|linux)" >&2; exit 1 ;;
esac

link() {  # link <workstation-relative-src> <absolute-home-target>
  local src="$WS/$1" dst="$2"
  if [ ! -e "$src" ]; then echo "SKIP (missing in repo): $1"; return; fi
  if [ "$DRY" = 0 ]; then mkdir -p "$(dirname "$dst")"; fi
  if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then
    echo "OK    already linked: $dst"; return
  fi
  if [ -e "$dst" ] || [ -L "$dst" ]; then
    echo "BACK  $dst -> $dst.bak.$TS"
    if [ "$DRY" = 0 ]; then mv "$dst" "$dst.bak.$TS"; fi
  fi
  echo "LINK  $dst -> $src"
  if [ "$DRY" = 0 ]; then ln -s "$src" "$dst"; fi
  return 0
}

# Add the template's ~/.claude/hooks/* entries to an existing settings.json
# (e.g. one written by `lean-ctx setup`). A hook whose command is already
# present is left alone; nothing else in the file changes.
HOOK_MERGE='reduce ($t[0].hooks | to_entries[] | .key as $e | .value[] | .matcher as $m
                   | .hooks[] | select(.command | contains("/.claude/hooks/"))
                   | {e: $e, m: $m, h: .}) as $x (.;
  if any(.hooks[$x.e][]?.hooks[]?; .command == $x.h.command) then .
  else .hooks[$x.e] += [{matcher: $x.m, hooks: [$x.h]}] end)'

SETTINGS="$HOME/.claude/settings.json"
SETTINGS_MERGED=""

die() { echo "ERROR $*" >&2; echo "nothing was changed." >&2; exit 1; }

# Everything that can fail runs here, before the first mutation (and under
# --dry-run too), so a failing run leaves the machine untouched.
preflight() {
  command -v jq >/dev/null 2>&1 \
    || die "jq is required (wires the Claude hooks into $SETTINGS); install it and re-run"
  [ -f "$SETTINGS" ] || return 0   # fresh machine: the template copy brings the hooks
  jq -e 'type == "object"' "$SETTINGS" >/dev/null 2>&1 \
    || die "$SETTINGS is not valid settings JSON (expected an object); fix it and re-run"
  SETTINGS_MERGED="$(jq --slurpfile t "$WS/claude/settings.json.example" "$HOOK_MERGE" "$SETTINGS" 2>/dev/null)" \
    || die "$SETTINGS is not valid settings JSON; fix it and re-run"
}

wire_hooks() {
  local s="$SETTINGS"
  if [ ! -f "$s" ]; then echo "WARN  hooks: no $s yet (copy the template below)"; return 0; fi
  if [ "$(jq -cS . "$s")" = "$(printf '%s\n' "$SETTINGS_MERGED" | jq -cS .)" ]; then
    echo "OK    hooks already wired: $s"; return 0
  fi
  echo "BACK  $s -> $s.bak.$TS"
  echo "HOOK  wire workstation hooks into $s"
  if [ "$DRY" = 0 ]; then
    cp -p "$s" "$s.bak.$TS"
    printf '%s\n' "$SETTINGS_MERGED" > "$s"    # in-place write keeps the file's mode and owner
  fi
  return 0
}

install_macos() {
  # workbench — persistent tmux session for phone/SSH access (workbench/README.md).
  # The LaunchAgent still needs a one-off bootstrap after linking:
  #   launchctl bootstrap user/$(id -u) ~/Library/LaunchAgents/com.chipi.workbench.plist
  link workbench/wb                  "$HOME/bin/wb"
  link workbench/wb-session.sh       "$HOME/bin/wb-session.sh"
  link workbench/tmux.conf           "$HOME/.tmux.conf"
  link workbench/com.chipi.workbench.plist "$HOME/Library/LaunchAgents/com.chipi.workbench.plist"
}

# Persistent per-user ssh-agent (README.md → SSH agent): the distro's systemd
# user socket, plus a stable SSH_AUTH_SOCK for interactive bash. Never starts
# an agent by hand and never touches keys; `ssh-add` stays a manual step.
SSH_SOCK_LINE='export SSH_AUTH_SOCK="$XDG_RUNTIME_DIR/ssh-agent.socket"'

ssh_agent_socket() {
  if ! command -v systemctl >/dev/null 2>&1 \
     || ! systemctl --user cat ssh-agent.socket >/dev/null 2>&1; then
    echo "WARN  ssh-agent: no systemd user ssh-agent.socket available; skipped"
    return 1
  fi
  if [ "$(systemctl --user is-enabled ssh-agent.socket 2>/dev/null)" = enabled ] \
     && systemctl --user is-active --quiet ssh-agent.socket; then
    echo "OK    ssh-agent.socket enabled and active"; return 0
  fi
  echo "UNIT  systemctl --user enable --now ssh-agent.socket"
  if [ "$DRY" = 0 ] && ! systemctl --user enable --now ssh-agent.socket; then
    echo "ERROR could not enable ssh-agent.socket; fix and re-run (earlier steps are already applied)" >&2
    exit 1
  fi
  return 0
}

ssh_agent_shell() {
  local rc="$HOME/.bashrc"
  if [ ! -f "$rc" ]; then echo "WARN  ssh-agent: no $rc; SSH_AUTH_SOCK not configured"; return 0; fi
  if grep -Eq '^[[:space:]]*export SSH_AUTH_SOCK="\$XDG_RUNTIME_DIR/ssh-agent\.socket"[[:space:]]*$' "$rc"; then
    echo "OK    SSH_AUTH_SOCK already set in $rc"; return 0
  fi
  if grep -Eq '^[^#]*SSH_AUTH_SOCK=' "$rc"; then
    echo "WARN  ssh-agent: $rc sets SSH_AUTH_SOCK differently; left unchanged"; return 0
  fi
  echo "BACK  $rc -> $rc.bak.$TS"
  echo "SHELL append SSH_AUTH_SOCK block to $rc"
  if [ "$DRY" = 0 ]; then
    cp -p "$rc" "$rc.bak.$TS"
    printf '\n# >>> workstation ssh-agent >>>\n# systemd user ssh-agent.socket; unlock once per boot: ssh-add ~/.ssh/id_ed25519\n%s\n# <<< workstation ssh-agent <<<\n' \
      "$SSH_SOCK_LINE" >> "$rc"
  fi
  return 0
}

install_linux() {
  # The Mac workbench (one session, a window per project) is deliberately not
  # installed: Linux uses one tmux session per project, and a ~/.tmux.conf link
  # would shadow the distro's ~/.config/tmux/tmux.conf (tmux reads ~/.tmux.conf first).
  if ssh_agent_socket; then ssh_agent_shell; fi
}

preflight

echo "workstation: $WS"
echo "platform:    $OS"
if [ "$DRY" = 1 ]; then
  echo "== DRY-RUN — preview only, nothing is changed (BACK/LINK lines are hypothetical) =="
else
  echo "**************************************************************************"
  echo "** REAL RUN — backing up live files to *.bak.$TS and SYMLINKING them.  **"
  echo "** No undo prompt. Ctrl-C now and re-run with --dry-run to preview.     **"
  echo "**************************************************************************"
fi
echo "== symlinking tracked, non-secret config =="
link config/AGENTS.md              "$HOME/.config/AGENTS.md"
link config/lean-ctx/config.toml   "$HOME/.config/lean-ctx/config.toml"
link config/ponytail/config.json   "$HOME/.config/ponytail/config.json"
link claude/CLAUDE.md              "$HOME/.claude/CLAUDE.md"
"install_$OS"
for _sk in "$WS"/claude/skills/*/; do
  [ -d "$_sk" ] || continue
  _n="$(basename "$_sk")"
  link "claude/skills/$_n" "$HOME/.claude/skills/$_n"
done
for _ag in "$WS"/claude/agents/*.md; do
  [ -e "$_ag" ] || continue
  _n="$(basename "$_ag")"
  link "claude/agents/$_n" "$HOME/.claude/agents/$_n"
done
for _hk in "$WS"/claude/hooks/*; do
  [ -e "$_hk" ] || continue
  _n="$(basename "$_hk")"
  link "claude/hooks/$_n" "$HOME/.claude/hooks/$_n"
done
for _wf in "$WS"/claude/workflows/*; do
  [ -e "$_wf" ] || continue
  _n="$(basename "$_wf")"
  link "claude/workflows/$_n" "$HOME/.claude/workflows/$_n"
done
wire_hooks

echo
echo "== secret-bearing templates — copy + fill by hand (NOT symlinked) =="
echo "   config/opencode/opencode.json.example  ->  ~/.config/opencode/opencode.json"
echo "     (set your DGX tailnet host; OpenRouter key goes in the shell env, not here)"
echo "   claude/settings.json.example           ->  ~/.claude/settings.json"
echo "     (set the ponytail <VERSION>; permissions.allow re-accrues via /fewer-permission-prompts;"
echo "      the secrets-guard PreToolUse hook resolves to the symlinked ~/.claude/hooks/secrets-guard.sh)"
echo
echo "done. Safe to re-run; replaced files are backed up as *.bak.$TS"
