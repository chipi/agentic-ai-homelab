#!/usr/bin/env bash
# Tests for install.sh's Linux provisioning: the persistent SSH agent, Worktrunk,
# and the ~/.bashrc block helper they share. Each case runs the real installer
# against a throwaway HOME, with a fake systemctl first on PATH (the real systemd
# user manager is never called).
#   bash workstation/install.test.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; INST="$HERE/install.sh"
for c in jq wt; do command -v "$c" >/dev/null || { echo "SKIP: $c not installed"; exit 0; }; done
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; fail=0
chk() { if eval "$2"; then echo "  ok   $1"; pass=$((pass+1)); else echo "  FAIL $1"; fail=$((fail+1)); fi; }

WT_LINE='if command -v wt >/dev/null 2>&1; then eval "$(command wt config shell init bash)"; fi'
SSH_LINE='export SSH_AUTH_SOCK="$XDG_RUNTIME_DIR/ssh-agent.socket"'
BASE=$'# Omarchy default\n[[ $- != *i* ]] && return\n'

# Fake systemctl. State per HOME in $FAKE_STATE/{available,enabled,active,fail_enable}; every call logged.
mkdir -p "$T/fake"
cat > "$T/fake/systemctl" <<'EOF'
#!/bin/sh
echo "$*" >> "$FAKE_STATE/calls"
case "$*" in
  "--user cat ssh-agent.socket")             [ -e "$FAKE_STATE/available" ] ;;
  "--user is-enabled ssh-agent.socket")      if [ -e "$FAKE_STATE/enabled" ]; then echo enabled; else echo disabled; fi ;;
  "--user is-active --quiet ssh-agent.socket") [ -e "$FAKE_STATE/active" ] ;;
  "--user enable --now ssh-agent.socket")    [ -e "$FAKE_STATE/fail_enable" ] && exit 1
                                             touch "$FAKE_STATE/enabled" "$FAKE_STATE/active" ;;
  *) exit 1 ;;
esac
EOF
chmod +x "$T/fake/systemctl"
# A PATH without wt (everything else the installer uses, plus the fake systemctl).
mkdir -p "$T/nowt"
for c in bash sh env dirname date uname basename readlink mkdir mv ln cp grep cat printf sed jq tr touch; do
  ln -sf "$(command -v "$c")" "$T/nowt/$c"
done
ln -sf "$T/fake/systemctl" "$T/nowt/systemctl"

# home <name> <bashrc|__none__> [unit: enabled(default)|disabled|none] [fail]
home() {
  H="$T/$1"; S="$T/$1.state"; mkdir -p "$H" "$S"; : > "$S/calls"
  if [ "$2" != __none__ ]; then printf '%s' "$2" > "$H/.bashrc"; chmod 640 "$H/.bashrc"; fi
  case "${3:-enabled}" in
    enabled)  touch "$S/available" "$S/enabled" "$S/active" ;;
    disabled) touch "$S/available" ;;
  esac
  [ "${4:-}" = fail ] && touch "$S/fail_enable"; return 0
}
run()  { HOME="$H" FAKE_STATE="$S" PATH="${RUNPATH:-$T/fake:$PATH}" WS_OS="${OSV:-linux}" "$INST" ${1:-} > "$H.out" 2>&1; echo $? > "$H.rc"; }
rc()   { cat "$H.rc"; }
ec()   { grep -c '^--user enable --now ssh-agent.socket$' "$S/calls"; }       # real enable invocations
sig()  { find "$H" -maxdepth 1 -name '.bashrc*' -printf '%p|%s|%m|%T@\n' | sort | md5sum; }
same_as() { cmp -s "$1" <(printf '%s' "$2"); }                                 # file == string, byte for byte
links_ok() {
  [ "$(readlink "$H/.config/worktrunk/config.toml")" = "$HERE/config/worktrunk/config.toml" ] &&
  [ "$(readlink "$H/.local/bin/wb-stream")" = "$HERE/streams/wb-stream" ] &&
  [ "$(readlink "$H/.local/bin/wb-workspace")" = "$HERE/streams/wb-workspace" ]
}

echo "== tracked Worktrunk config (rendering and hooks are tested in streams/wb-stream.test.sh and wb-workspace.test.sh)"
CFG="$HERE/config/worktrunk/config.toml"
chk "no commit generation configured (no commit keys outside comments)" "! grep -v '^[[:space:]]*#' '$CFG' | grep -q 'commit'"
chk "only worktree-path plus the two workspace hooks" \
  "[ \"\$(grep -v '^[[:space:]]*#' '$CFG' | grep -v '^[[:space:]]*\$' | grep -v '^worktree-path = ' | tr '\n' '|')\" = '[pre-start]|workspace = \"wb-workspace setup\"|[pre-remove]|workspace = \"wb-workspace teardown\"|' ] && grep -q '^worktree-path = ' '$CFG'"
chk "installer sets no WORKTRUNK_COMMIT__* override and installs no wt plugins" "! grep -q -e 'WORKTRUNK_COMMIT' -e 'wt config plugins' '$INST'"

echo "== SSH agent: fresh (unit disabled, no SSH_AUTH_SOCK line)"
ORIG="$BASE$WT_LINE"$'\n'
home ssh-fresh "$ORIG" disabled; before=$(sig)
run --dry-run
chk "dry-run: UNIT + SHELL announced, nothing written" \
  "[ $(rc) = 0 ] && grep -q '^UNIT  systemctl --user enable --now ssh-agent.socket' '$H.out' && grep -q '^SHELL append SSH_AUTH_SOCK block' '$H.out' && [ \"\$(sig)\" = '$before' ]"
chk "COUNT dry-run enable = 0" "[ \$(ec) = 0 ]"
: > "$S/calls"; run
chk "COUNT first real install enable = 1" "[ $(rc) = 0 ] && [ \$(ec) = 1 ]"
chk "block appended once in markers; mode 640 kept; backup equals original" \
  "[ \$(grep -cxF '$SSH_LINE' '$H/.bashrc') = 1 ] && grep -qx '# >>> workstation ssh-agent >>>' '$H/.bashrc' && [ \$(stat -c %a '$H/.bashrc') = 640 ] && same_as '$H'/.bashrc.bak.* \"\$ORIG\""
sed -n '/>>> workstation ssh-agent/,/<<< workstation ssh-agent/p' "$H/.bashrc" > "$T/block.sh"; printf 'echo "$SSH_AUTH_SOCK"\n' >> "$T/block.sh"
chk "sourcing the block gives the stable socket" "[ \"\$(env -i XDG_RUNTIME_DIR=/run/user/1234 \"\$(command -v bash)\" '$T/block.sh')\" = /run/user/1234/ssh-agent.socket ]"
after=$(sig); : > "$S/calls"; run
chk "rerun: OK for socket and line, .bashrc unchanged" \
  "[ $(rc) = 0 ] && grep -q '^OK    ssh-agent.socket enabled and active' '$H.out' && grep -q '^OK    SSH_AUTH_SOCK already set' '$H.out' && [ \"\$(sig)\" = '$after' ]"
chk "COUNT idempotent rerun enable = 0" "[ \$(ec) = 0 ]"

echo "== SSH agent: other states"
home ssh-live "$BASE$SSH_LINE"$'\n'"$WT_LINE"$'\n'; before=$(sig); run
chk "exact line already present (as on X3): OK, unchanged" "[ $(rc) = 0 ] && grep -q '^OK    SSH_AUTH_SOCK already set' '$H.out' && [ \"\$(sig)\" = '$before' ]"
home ssh-other "$BASE"'export SSH_AUTH_SOCK="$(gpgconf --list-dirs agent-ssh-socket)"'$'\n'"$WT_LINE"$'\n'; before=$(sig); run
chk "different SSH_AUTH_SOCK: WARN, unchanged" "[ $(rc) = 0 ] && grep -q '^WARN  ssh-agent: .* sets SSH_AUTH_SOCK differently' '$H.out' && [ \"\$(sig)\" = '$before' ]"
home ssh-commented "$BASE"'# export SSH_AUTH_SOCK=/tmp/old'$'\n'"$WT_LINE"$'\n'; run
chk "only a commented-out SSH_AUTH_SOCK: block added" "[ $(rc) = 0 ] && [ \$(grep -cxF '$SSH_LINE' '$H/.bashrc') = 1 ]"
home ssh-nobashrc __none__; run
chk "no ~/.bashrc: WARN, not created" "[ $(rc) = 0 ] && grep -q '^WARN  ssh-agent: no ' '$H.out' && [ ! -e '$H/.bashrc' ]"
home ssh-nounit "$BASE$WT_LINE"$'\n' none; before=$(sig); run
chk "no ssh-agent.socket unit: WARN, unchanged, no enable" "[ $(rc) = 0 ] && grep -q '^WARN  ssh-agent: no systemd user ssh-agent.socket' '$H.out' && [ \"\$(sig)\" = '$before' ] && [ \$(ec) = 0 ]"
home ssh-failing "$BASE$WT_LINE"$'\n' disabled fail; before=$(sig); run
chk "enable fails: exit 1, ERROR, no 'done.', .bashrc unchanged" "[ $(rc) = 1 ] && grep -q '^ERROR could not enable ssh-agent.socket' '$H.out' && ! grep -q '^done\.' '$H.out' && [ \"\$(sig)\" = '$before' ]"
chk "COUNT failed enable attempt = 1, exit nonzero" "[ \$(ec) = 1 ] && [ $(rc) != 0 ]"

echo "== Worktrunk: fresh (no wt integration yet)"
ORIG="$BASE$SSH_LINE"$'\n'
home wt-fresh "$ORIG"; before=$(sig)
run --dry-run
chk "dry-run: SHELL + both links announced, nothing written" \
  "[ $(rc) = 0 ] && grep -q '^SHELL append Worktrunk shell integration block' '$H.out' && grep -q '^LINK  .*/.config/worktrunk/config.toml' '$H.out' && grep -q '^LINK  .*/.local/bin/wb-stream' '$H.out' && [ \"\$(sig)\" = '$before' ] && [ ! -e '$H/.config/worktrunk' ] && [ ! -e '$H/.local' ]"
run
chk "real run: line appended once in markers; mode 640 kept; backup equals original" \
  "[ $(rc) = 0 ] && [ \$(grep -cxF '$WT_LINE' '$H/.bashrc') = 1 ] && grep -qx '# >>> workstation worktrunk >>>' '$H/.bashrc' && grep -qx '# <<< workstation worktrunk <<<' '$H/.bashrc' && [ \$(stat -c %a '$H/.bashrc') = 640 ] && same_as '$H'/.bashrc.bak.* \"\$ORIG\""
chk "config and wb-stream linked" "links_ok"
after=$(sig); run
chk "rerun: OK for integration and links, .bashrc unchanged, no extra backup" \
  "[ $(rc) = 0 ] && grep -q '^OK    Worktrunk shell integration already set' '$H.out' && grep -q '^OK    already linked: .*/.local/bin/wb-stream' '$H.out' && [ \"\$(sig)\" = '$after' ]"

echo "== Worktrunk: other states"
home wt-existing "$BASE$SSH_LINE"$'\n'"$WT_LINE"$'\n'; before=$(sig); run
chk "unmarked integration already present (as on X3): OK, unchanged" "[ $(rc) = 0 ] && grep -q '^OK    Worktrunk shell integration already set' '$H.out' && [ \"\$(sig)\" = '$before' ]"
home wt-indented "$BASE$SSH_LINE"$'\n'"    $WT_LINE  "$'\n'; before=$(sig); run
chk "indented/trailing-space copy counts as present" "[ $(rc) = 0 ] && [ \"\$(sig)\" = '$before' ]"
home wt-other "$BASE$SSH_LINE"$'\n''eval "$(wt config shell init bash)"'$'\n'; before=$(sig); run
chk "different wt init line: WARN, unchanged" "[ $(rc) = 0 ] && grep -q '^WARN  worktrunk: .* sets Worktrunk shell integration differently' '$H.out' && [ \"\$(sig)\" = '$before' ]"
home wt-nowt "$BASE$SSH_LINE"$'\n'; before=$(sig); RUNPATH="$T/nowt" run
chk "wt not installed: WARN with pacman hint, .bashrc unchanged, links still made" "[ $(rc) = 0 ] && grep -q '^WARN  worktrunk: wt not installed (sudo pacman -S --needed worktrunk)' '$H.out' && [ \"\$(sig)\" = '$before' ] && links_ok"

echo "== shared helper: SSH and Worktrunk blocks both needed in one run"
home both "$BASE"; run --dry-run
chk "dry-run announces the backup once" "[ $(rc) = 0 ] && [ \$(grep -c '^BACK  .*/.bashrc ->' '$H.out') = 1 ] && [ \$(grep -c '^SHELL append' '$H.out') = 2 ]"
run
chk "one backup (the original), each block once" \
  "[ $(rc) = 0 ] && [ \$(ls '$H'/.bashrc.bak.* | wc -l) = 1 ] && same_as '$H'/.bashrc.bak.* \"\$BASE\" && [ \$(grep -cxF '$WT_LINE' '$H/.bashrc') = 1 ] && [ \$(grep -cxF '$SSH_LINE' '$H/.bashrc') = 1 ]"

echo "== macOS path unchanged"
home mac "$BASE" disabled; before=$(sig); OSV=macos run
chk "no ssh-agent/Worktrunk output, no systemctl calls, .bashrc unchanged" \
  "[ $(rc) = 0 ] && ! grep -qi -e worktrunk -e wb-stream -e ssh-agent -e SSH_AUTH_SOCK '$H.out' && [ ! -s '$S/calls' ] && [ \"\$(sig)\" = '$before' ] && [ ! -e '$H/.config/worktrunk' ]"

echo; echo "RESULT: pass=$pass fail=$fail"
[ "$fail" = 0 ]
