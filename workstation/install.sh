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

# bashrc_block <tag> <what> <line> <conflict-ERE> <comment>
# Ensure <line> is in ~/.bashrc exactly once. Already there (marked or not,
# surrounding whitespace ignored): nothing changes. Another uncommented line
# matching <conflict-ERE>: warn and leave the file alone. Otherwise append a
# marked block, backing the file up once per run (BASHRC_BACKED_UP).
BASHRC_BACKED_UP=0
bashrc_block() {
  local tag=$1 what=$2 line=$3 conflict=$4 comment=$5 rc="$HOME/.bashrc" trimmed
  if [ ! -f "$rc" ]; then echo "WARN  $tag: no $rc; $what not configured"; return 0; fi
  trimmed=$(sed 's/^[[:space:]]*//; s/[[:space:]]*$//' "$rc")
  if grep -qxF -- "$line" <<<"$trimmed"; then
    echo "OK    $what already set in $rc"; return 0
  fi
  if grep -Eq -- "$conflict" "$rc"; then
    echo "WARN  $tag: $rc sets $what differently; left unchanged"; return 0
  fi
  if [ "$BASHRC_BACKED_UP" = 0 ]; then
    echo "BACK  $rc -> $rc.bak.$TS"
    if [ "$DRY" = 0 ]; then cp -p "$rc" "$rc.bak.$TS"; fi
    BASHRC_BACKED_UP=1
  fi
  echo "SHELL append $what block to $rc"
  if [ "$DRY" = 0 ]; then
    printf '\n# >>> workstation %s >>>\n# %s\n%s\n# <<< workstation %s <<<\n' \
      "$tag" "$comment" "$line" "$tag" >> "$rc"
  fi
  return 0
}

ssh_agent_shell() {
  bashrc_block ssh-agent SSH_AUTH_SOCK "$SSH_SOCK_LINE" '^[^#]*SSH_AUTH_SOCK=' \
    'systemd user ssh-agent.socket; unlock once per boot: ssh-add ~/.ssh/id_ed25519'
}

# Worktrunk (streams/README.md): Model-B worktree layout, the wb-stream,
# wb-workspace and wb-integrate commands (the config's workspace hooks call
# wb-workspace), and wt's bash integration (lets `wt switch` cd the calling shell).
# The package itself is a documented manual step (setup-new-computer.md).
WT_INIT_LINE='if command -v wt >/dev/null 2>&1; then eval "$(command wt config shell init bash)"; fi'

worktrunk() {
  link config/worktrunk/config.toml  "$HOME/.config/worktrunk/config.toml"
  link streams/wb-stream             "$HOME/.local/bin/wb-stream"
  link streams/wb-workspace          "$HOME/.local/bin/wb-workspace"
  link streams/wb-integrate          "$HOME/.local/bin/wb-integrate"
  if ! command -v wt >/dev/null 2>&1; then
    echo "WARN  worktrunk: wt not installed (sudo pacman -S --needed worktrunk); shell integration skipped"
    return 0
  fi
  bashrc_block worktrunk "Worktrunk shell integration" "$WT_INIT_LINE" '^[^#]*wt config shell init' \
    'Worktrunk: lets `wt switch` change this shell'"'"'s directory'
}

# Storage layout (storage/README.md): links wb-storage and REPORTS the layout.
# The installer never changes it: no subvolumes, no fstab, no mounts, no data
# moved, no units touched. A machine with data in /work or the Docker trees is
# migrated by hand (docs/recipes/x3-storage-separation.md).
storage() {
  link storage/wb-storage            "$HOME/.local/bin/wb-storage"
  local v
  v="$("$WS/storage/wb-storage" status --brief 2>&1)" || true
  echo "INFO  storage: ${v:-status unavailable}"
}

# tmux workspace persistence (tmux/README.md): tmux-resurrect at a pinned commit,
# the persistence policy sourced from the END of the user's tmux config by one
# marked line (the distro's config is never replaced), wb-tmux, and a systemd user
# timer for periodic saves. Never touches a running tmux server: load it with
# `tmux source-file <config>` or at the next server start.
TMUX_LOCK="${WB_TMUX_LOCK:-$WS/tmux/plugins.lock}"   # WB_TMUX_LOCK / _PLUGIN_SRC: tests only
TMUX_SRC_LINE='source-file -q ~/.config/tmux/workstation-persistence.conf'

tmux_user_conf() {   # the user config tmux loads: ~/.tmux.conf wins if it exists
  if [ -e "$HOME/.tmux.conf" ]; then echo "$HOME/.tmux.conf"
  elif [ -n "${XDG_CONFIG_HOME:-}" ] && [ -e "$XDG_CONFIG_HOME/tmux/tmux.conf" ]; then echo "$XDG_CONFIG_HOME/tmux/tmux.conf"
  else echo "$HOME/.config/tmux/tmux.conf"
  fi
}

tmux_plugins() {
  local base="$HOME/.local/share/tmux/plugins" name url commit dst got
  while read -r name url commit; do
    case $name in ''|\#*) continue ;; esac
    [ -n "${WB_TMUX_PLUGIN_SRC:-}" ] && url="$WB_TMUX_PLUGIN_SRC/$name"
    dst="$base/$name"
    if [ -d "$dst/.git" ]; then
      got=$(git -C "$dst" rev-parse HEAD 2>/dev/null || true)
      if [ "$got" = "$commit" ]; then echo "OK    tmux plugin $name at ${commit:0:12}"
      else echo "WARN  tmux plugin $name: $dst is at ${got:-?}, pinned ${commit:0:12}; left unchanged"; fi
      continue
    fi
    if [ -e "$dst" ]; then echo "WARN  tmux plugin $name: $dst exists but is not a git checkout; left unchanged"; continue; fi
    echo "CLONE tmux plugin $name ${commit:0:12} -> $dst"
    [ "$DRY" = 0 ] || continue
    mkdir -p "$base"
    if ! { git clone --quiet --no-checkout "$url" "$dst" && git -C "$dst" -c advice.detachedHead=false checkout --quiet --detach "$commit"; }; then
      echo "WARN  tmux plugin $name: could not fetch $url at ${commit:0:12}; tmux persistence is not active (wb-tmux status)"
    fi
  done < "$TMUX_LOCK"
}

# Append the source line to the tmux config once (same rules as bashrc_block).
tmux_conf_block() {
  local conf; conf=$(tmux_user_conf)
  if [ -f "$conf" ] && grep -qxF -- "$TMUX_SRC_LINE" <<<"$(sed 's/^[[:space:]]*//; s/[[:space:]]*$//' "$conf")"; then
    echo "OK    tmux persistence already sourced from $conf"; return 0
  fi
  if [ -f "$conf" ]; then
    echo "BACK  $conf -> $conf.bak.$TS"
    [ "$DRY" = 1 ] || cp -p "$conf" "$conf.bak.$TS"
  fi
  echo "TMUX  append the persistence source line to $conf"
  if [ "$DRY" = 0 ]; then
    mkdir -p "$(dirname "$conf")"
    printf '\n# >>> workstation tmux-persistence >>>\n# tmux-resurrect policy (agentic-ai-homelab workstation/tmux); keep this block last\n%s\n# <<< workstation tmux-persistence <<<\n' \
      "$TMUX_SRC_LINE" >> "$conf"
  fi
}

tmux_timer() {
  link tmux/systemd/wb-tmux-save.service "$HOME/.config/systemd/user/wb-tmux-save.service"
  link tmux/systemd/wb-tmux-save.timer   "$HOME/.config/systemd/user/wb-tmux-save.timer"
  if ! command -v systemctl >/dev/null 2>&1 || ! systemctl --user show-environment >/dev/null 2>&1; then
    echo "WARN  tmux persistence: no systemd user manager; periodic saves are off (save by hand: wb-tmux save)"
    return 0
  fi
  if [ "$(systemctl --user is-enabled wb-tmux-save.timer 2>/dev/null)" = enabled ] \
     && systemctl --user is-active --quiet wb-tmux-save.timer; then
    echo "OK    wb-tmux-save.timer enabled and active"; return 0
  fi
  echo "UNIT  systemctl --user daemon-reload; systemctl --user enable --now wb-tmux-save.timer"
  if [ "$DRY" = 0 ] && ! { systemctl --user daemon-reload && systemctl --user enable --now wb-tmux-save.timer; }; then
    echo "WARN  could not enable wb-tmux-save.timer; periodic saves are off (wb-tmux status)"
  fi
  return 0
}

tmux_persistence() {
  if ! command -v tmux >/dev/null 2>&1 || ! command -v git >/dev/null 2>&1; then
    echo "WARN  tmux persistence: tmux or git not installed; skipped"; return 0
  fi
  tmux_plugins
  link tmux/persistence.conf          "$HOME/.config/tmux/workstation-persistence.conf"
  link tmux/wb-tmux                   "$HOME/.local/bin/wb-tmux"
  tmux_conf_block
  tmux_timer
  echo "NEXT  load it into a running tmux server: tmux source-file $(tmux_user_conf)   (the installer never touches a running server)"
}

# LeanCTX project root per invocation (config/lean-ctx/README.md). The Bash hook
# rewrites cat/head/sed/tail/grep/rg/ls into one-shot `lean-ctx read|grep|ls`
# calls, which by default are served by ONE per-user daemon whose project root is
# the cwd of whichever call happened to start it; every other project and
# worktree is then refused (upstream #1695, still in 3.10.5 and 3.11.4). With
# this set, each call resolves the root from its own cwd. Agents launched from
# a shell inherit it; already running agents keep their old environment.
LEANCTX_ROOT_LINE='export __LEAN_CTX_NO_DAEMON=1'

lean_ctx_root() {
  bashrc_block lean-ctx-root "LeanCTX per-invocation project root" "$LEANCTX_ROOT_LINE" '^[^#]*__LEAN_CTX_NO_DAEMON=' \
    'one-shot lean-ctx calls take the project root from their own cwd, not the shared daemon (lean-ctx #1695)'
}

install_linux() {
  # The Mac workbench (one session, a window per project) is deliberately not
  # installed: Linux uses one tmux session per project, and a ~/.tmux.conf link
  # would shadow the distro's ~/.config/tmux/tmux.conf (tmux reads ~/.tmux.conf first).
  if ssh_agent_socket; then ssh_agent_shell; fi
  lean_ctx_root
  worktrunk
  storage
  tmux_persistence
  # recovery/README.md: the tiny encrypted recovery bundle; the manifest stays private
  link recovery/wb-recovery          "$HOME/.local/bin/wb-recovery"
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
