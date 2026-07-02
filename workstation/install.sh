#!/usr/bin/env bash
# Restore the operator's global agent config onto a machine by symlinking home
# locations into this repo (dotfiles pattern — same as ~/bin -> infra/dgx/bin).
# Idempotent. Any existing real file is backed up before it is replaced.
# Secret-bearing config is NOT symlinked — see the printed template list.
# Full bootstrap sequence: ./setup-new-computer.md
set -euo pipefail

WS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"     # workstation/ dir
DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1
TS="$(date +%Y%m%d-%H%M%S)"

link() {  # link <workstation-relative-src> <absolute-home-target>
  local src="$WS/$1" dst="$2"
  if [ ! -e "$src" ]; then echo "SKIP (missing in repo): $1"; return; fi
  mkdir -p "$(dirname "$dst")"
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

echo "workstation: $WS   (dry-run=$DRY)"
echo "== symlinking tracked, non-secret config =="
link config/AGENTS.md              "$HOME/.config/AGENTS.md"
link config/lean-ctx/config.toml   "$HOME/.config/lean-ctx/config.toml"
link config/ponytail/config.json   "$HOME/.config/ponytail/config.json"
link claude/CLAUDE.md              "$HOME/.claude/CLAUDE.md"
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

echo
echo "== secret-bearing templates — copy + fill by hand (NOT symlinked) =="
echo "   config/opencode/opencode.json.example  ->  ~/.config/opencode/opencode.json"
echo "     (set your DGX tailnet host; OpenRouter key goes in the shell env, not here)"
echo "   claude/settings.json.example           ->  ~/.claude/settings.json"
echo "     (set the ponytail <VERSION>; permissions.allow re-accrues via /fewer-permission-prompts;"
echo "      the secrets-guard PreToolUse hook resolves to the symlinked ~/.claude/hooks/secrets-guard.sh)"
echo
echo "done. Safe to re-run; replaced files are backed up as *.bak.$TS"
