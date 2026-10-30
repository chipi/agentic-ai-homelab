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
export INFRA_CHECKOUT="$T/no-infra"   # no chipi/infra checkout unless a case names one
pass=0; fail=0
chk() { if eval "$2"; then echo "  ok   $1"; pass=$((pass+1)); else echo "  FAIL $1"; fail=$((fail+1)); fi; }

WT_LINE='if command -v wt >/dev/null 2>&1; then eval "$(command wt config shell init bash)"; fi'
SSH_LINE='export SSH_AUTH_SOCK="$XDG_RUNTIME_DIR/ssh-agent.socket"'
LCTX_LINE='export __LEAN_CTX_NO_DAEMON=1'
BASE0=$'# Omarchy default\n[[ $- != *i* ]] && return\n'
BASE="$BASE0$LCTX_LINE"$'\n'      # the X3 after this installer: the LeanCTX root line already set

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
  "--user show-environment")                 [ ! -e "$FAKE_STATE/no_user_manager" ] ;;
  "--user is-enabled wb-tmux-save.timer")    if [ -e "$FAKE_STATE/timer" ]; then echo enabled; else echo disabled; fi ;;
  "--user is-active --quiet wb-tmux-save.timer") [ -e "$FAKE_STATE/timer" ] ;;
  "--user daemon-reload")                    : ;;
  "--user enable --now wb-tmux-save.timer")  touch "$FAKE_STATE/timer" ;;
  *) exit 1 ;;
esac
EOF
chmod +x "$T/fake/systemctl"
# Storage status (storage/wb-storage) reads a scratch root and a fake findmnt, never
# the live host. FAKE_MOUNTS lines: "<mountpoint> <fstype> <options> <uuid>".
cat > "$T/fake/findmnt" <<'EOF'
#!/bin/sh
cols=; mp=
while [ $# -gt 0 ]; do case $1 in -o) cols=$2; shift ;; --mountpoint) mp=$2; shift ;; esac; shift; done
awk -v mp="$mp" -v cols="$cols" '$1 == mp { n = split(cols, c, ","); out = ""
  for (i = 1; i <= n; i++) { v = (c[i] == "FSTYPE") ? $2 : (c[i] == "OPTIONS") ? $3 : (c[i] == "UUID") ? $4 : ""; out = out (i > 1 ? " " : "") v }
  print out; found = 1 } END { exit found ? 0 : 1 }' "$FAKE_MOUNTS"
EOF
chmod +x "$T/fake/findmnt"
# sroot <name>: a scratch storage root with an Omarchy-like root fstab entry and mount.
SUUID="0f0f0f0f-1111-4222-8333-444455556666"; SOPTS="rw,relatime,compress=zstd:3,ssd,space_cache=v2,subvol=/@"
sroot() {
  SR="$T/$1.sroot"; mkdir -p "$SR/etc"
  printf 'UUID=%s\t/\tbtrfs\t%s\t0 0\n' "$SUUID" "$SOPTS" > "$SR/etc/fstab"
  printf '/ btrfs %s %s\n' "$SOPTS" "$SUUID" > "$SR.mounts"
}
ssig() { (cd "$SR" && find . -printf '%p|%y|%s|%m|%T@|%i\n' | sort; find . -type f -exec md5sum {} + | sort) | md5sum; }
sroot default
# tmux persistence: a local stand-in for the tmux-resurrect repository and a lock
# file pinning its commit, so no case reaches the network.
PSRC="$T/plugin-src"; git init -q "$PSRC/tmux-resurrect"
echo 'run-shell true' > "$PSRC/tmux-resurrect/resurrect.tmux"
git -C "$PSRC/tmux-resurrect" add . && git -C "$PSRC/tmux-resurrect" -c user.name=t -c user.email=t@t commit -qm one
PIN=$(git -C "$PSRC/tmux-resurrect" rev-parse HEAD)
echo two >> "$PSRC/tmux-resurrect/resurrect.tmux"; git -C "$PSRC/tmux-resurrect" -c user.name=t -c user.email=t@t commit -qam two
printf '# test lock\ntmux-resurrect https://example.invalid/tmux-resurrect.git %s\n' "$PIN" > "$T/plugins.lock"
TSRC_LINE='source-file -q ~/.config/tmux/workstation-persistence.conf'
OMARCHY_TMUX=$'# Omarchy tmux.conf\nset -g prefix C-Space\nset -g status-right "#h "\n'
# A PATH without wt (everything else the installer uses, plus the fake systemctl).
mkdir -p "$T/nowt"
for c in bash sh env dirname date uname basename readlink mkdir mv ln cp grep cat printf sed jq tr touch awk find paste cmp id; do
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
run()  { HOME="$H" FAKE_STATE="$S" PATH="${RUNPATH:-$T/fake:$PATH}" WS_OS="${OSV:-linux}" \
         WB_STORAGE_ROOT="$SR" WB_STORAGE_FINDMNT="$T/fake/findmnt" FAKE_MOUNTS="$SR.mounts" \
         WB_TMUX_PLUGIN_SRC="$PSRC" WB_TMUX_LOCK="$T/plugins.lock" \
         "$INST" ${1:-} > "$H.out" 2>&1; echo $? > "$H.rc"; }
rc()   { cat "$H.rc"; }
ec()   { grep -c '^--user enable --now ssh-agent.socket$' "$S/calls"; }       # real enable invocations
sig()  { find "$H" -maxdepth 1 -name '.bashrc*' -printf '%p|%s|%m|%T@\n' | sort | md5sum; }
same_as() { cmp -s "$1" <(printf '%s' "$2"); }                                 # file == string, byte for byte
links_ok() {
  [ "$(readlink "$H/.config/worktrunk/config.toml")" = "$HERE/config/worktrunk/config.toml" ] &&
  [ "$(readlink "$H/.local/bin/wb-stream")" = "$HERE/streams/wb-stream" ] &&
  [ "$(readlink "$H/.local/bin/wb-workspace")" = "$HERE/streams/wb-workspace" ] &&
  [ "$(readlink "$H/.local/bin/wb-integrate")" = "$HERE/streams/wb-integrate" ]
}

echo "== tracked Worktrunk config (rendering and hooks are tested in streams/wb-stream.test.sh and wb-workspace.test.sh)"
CFG="$HERE/config/worktrunk/config.toml"
chk "no commit generation configured (no commit keys outside comments)" "! grep -v '^[[:space:]]*#' '$CFG' | grep -q 'commit'"
chk "only worktree-path, the setup hook, and the ordered pre-remove pipeline (live-check, then teardown)" \
  "[ \"\$(grep -v '^[[:space:]]*#' '$CFG' | grep -v '^[[:space:]]*\$' | grep -v '^worktree-path = ' | tr '\n' '|')\" = '[pre-start]|workspace = \"wb-workspace setup\"|[[pre-remove]]|live-check = \"wb-workspace live-check\"|[[pre-remove]]|workspace = \"wb-workspace teardown\"|' ] && grep -q '^worktree-path = ' '$CFG'"
chk "installer sets no WORKTRUNK_COMMIT__* override and installs no wt plugins" "! grep -q -e 'WORKTRUNK_COMMIT' -e 'wt config plugins' '$INST'"
LCX="$HERE/config/lean-ctx/config.toml"
chk "LeanCTX allowlist covers wt, wb-stream, wb-workspace, wb-integrate" \
  "ok=1; for c in wt wb-stream wb-workspace wb-integrate; do grep -qE \"^[[:space:]]*\\\"\$c\\\",\" '$LCX' || ok=0; done; [ \$ok = 1 ]"

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

echo "== LeanCTX: per-invocation project root (config/lean-ctx/README.md)"
home lc-fresh "$BASE0$SSH_LINE"$'\n'"$WT_LINE"$'\n'; ORIG="$BASE0$SSH_LINE"$'\n'"$WT_LINE"$'\n'; before=$(sig)
run --dry-run
chk "dry-run: SHELL append announced, .bashrc unchanged" "[ $(rc) = 0 ] && grep -q '^SHELL append LeanCTX per-invocation project root block' '$H.out' && [ \"\$(sig)\" = '$before' ]"
run
chk "real run: the line is added once, in markers; backup equals the original" \
  "[ $(rc) = 0 ] && [ \$(grep -cxF '$LCTX_LINE' '$H/.bashrc') = 1 ] && grep -qx '# >>> workstation lean-ctx-root >>>' '$H/.bashrc' && same_as '$H'/.bashrc.bak.* \"\$ORIG\""
sed -n '/>>> workstation lean-ctx-root/,/<<< workstation lean-ctx-root/p' "$H/.bashrc" > "$T/lc.sh"; printf 'echo "${__LEAN_CTX_NO_DAEMON:-unset}"\n' >> "$T/lc.sh"
chk "sourcing the block exports it to child processes (agents, their tool shells)" "[ \"\$(env -i \"\$(command -v bash)\" -c '. $T/lc.sh >/dev/null; bash -c \"echo \\\${__LEAN_CTX_NO_DAEMON:-unset}\"')\" = 1 ]"
after=$(sig); run
chk "rerun: OK, .bashrc unchanged" "[ $(rc) = 0 ] && grep -q '^OK    LeanCTX per-invocation project root already set' '$H.out' && [ \"\$(sig)\" = '$after' ]"
home lc-other "$BASE0"'export __LEAN_CTX_NO_DAEMON=0'$'\n'"$SSH_LINE"$'\n'"$WT_LINE"$'\n'; before=$(sig); run
chk "a different existing setting: WARN, left unchanged" "[ $(rc) = 0 ] && grep -q '^WARN  lean-ctx-root: .* sets LeanCTX per-invocation project root differently' '$H.out' && [ \"\$(sig)\" = '$before' ]"
LCC="$HERE/config/lean-ctx/config.toml"
chk "no access broadening in the tracked LeanCTX config: no path_jail=false, no pinned project_root, allow_paths empty, no extra/symlink roots" \
  "! grep -qE '^[[:space:]]*(path_jail[[:space:]]*=[[:space:]]*false|project_root[[:space:]]*=|extra_roots|allow_symlink_roots|read_only_roots)' '$LCC' && grep -qx 'allow_paths = \[\]' '$LCC'"
chk "the fix is not a global root: installer sets no LEAN_CTX_PROJECT_ROOT, LEAN_CTX_EXTRA_ROOTS or path_jail override" \
  "! grep -v '^[[:space:]]*#' '$INST' | grep -qE 'LEAN_CTX_PROJECT_ROOT|LEAN_CTX_EXTRA_ROOTS|LEAN_CTX_ALLOW_PATH|path_jail'"

echo "== storage layout: reported, never changed (storage/README.md)"
sroot populated
mkdir -p "$SR/work/orrery/main/.git" "$SR/var/lib/docker" "$SR/var/lib/containerd/io.containerd.content.v1.content"
echo src > "$SR/work/orrery/main/README.md"; echo id > "$SR/var/lib/docker/engine-id"; echo blob > "$SR/var/lib/containerd/io.containerd.content.v1.content/b"
home st-populated "$BASE$SSH_LINE"$'\n'"$WT_LINE"$'\n'; sbefore=$(ssig)
run --dry-run
chk "populated /work + Docker trees (as on X3), dry-run: reports needs-migration, storage root unchanged" \
  "[ $(rc) = 0 ] && grep -q '^INFO  storage: needs-migration: .*docs/recipes/x3-storage-separation.md' '$H.out' && [ \"\$(ssig)\" = '$sbefore' ] && [ ! -e '$H/.local/bin/wb-storage' ]"
run
chk "populated, real run: same report; nothing moved, copied, deleted or written under the storage root" \
  "[ $(rc) = 0 ] && grep -q '^INFO  storage: needs-migration' '$H.out' && [ \"\$(ssig)\" = '$sbefore' ]"
chk "real run links wb-recovery and installs no recovery manifest (that stays private, by hand)" \
  "[ \"\$(readlink '$H/.local/bin/wb-recovery')\" = '$HERE/recovery/wb-recovery' ] && [ ! -e '$H/.config/wb-recovery' ]"
chk "real run links wb-storage; installs no drop-ins and adds no fstab entry" \
  "[ \"\$(readlink '$H/.local/bin/wb-storage')\" = '$HERE/storage/wb-storage' ] && [ ! -e '$SR/etc/systemd' ] && [ \$(grep -c . '$SR/etc/fstab') = 1 ]"
sroot fresh; home st-fresh "$BASE$SSH_LINE"$'\n'"$WT_LINE"$'\n'; sbefore=$(ssig); run
chk "fresh machine: reports 'fresh' but does not establish the layout itself" \
  "[ $(rc) = 0 ] && grep -q '^INFO  storage: fresh: ' '$H.out' && [ \"\$(ssig)\" = '$sbefore' ] && [ ! -e '$SR/work' ]"
sroot default

echo "== tmux persistence: tracked policy (tmux/README.md)"
PC="$HERE/tmux/persistence.conf"; LOCK="$HERE/tmux/plugins.lock"
pc_set() { grep -v '^[[:space:]]*#' "$PC" | grep -E "^set -g $1 "; }
chk "policy: @resurrect-processes 'false' (no program is ever restored), set exactly once" \
  "[ \"\$(pc_set @resurrect-processes)\" = \"set -g @resurrect-processes 'false'\" ] && [ \$(grep -c '@resurrect-processes' '$PC') = 1 ]"
chk "policy: no process lists, :all:, restore strategies, default-process overrides or continuum" \
  "! grep -v '^[[:space:]]*#' '$PC' | grep -qiE ':all:|@resurrect-strategy|@resurrect-default-processes|continuum|claude|codex|opencode|node|npm|pnpm|bun|python|uv|docker'"
chk "policy: pane contents never captured; scrub hook set" \
  "[ \"\$(pc_set @resurrect-capture-pane-contents)\" = \"set -g @resurrect-capture-pane-contents 'off'\" ] && pc_set @resurrect-hook-post-save-layout | grep -q 'wb-tmux scrub'"
chk "policy: snapshots in durable user state (\$HOME/.local/share), not /tmp, /run or a project tree" \
  "[ \"\$(pc_set @resurrect-dir)\" = \"set -g @resurrect-dir '\\\$HOME/.local/share/tmux/resurrect'\" ]"
chk "lock: exactly tmux-resurrect, pinned to a full 40-hex commit (no TPM, no continuum)" \
  "[ \"\$(grep -v '^#' '$LOCK' | grep -c .)\" = 1 ] && grep -v '^#' '$LOCK' | grep -qE '^tmux-resurrect https://github.com/tmux-plugins/tmux-resurrect.git [0-9a-f]{40}\$'"
chk "no project names in the portable tmux code, config or units (outside comments)" \
  "! cat '$HERE/tmux/wb-tmux' '$PC' '$LOCK' '$HERE'/tmux/systemd/* | grep -v '^[[:space:]]*#' | grep -qiE 'orrery|chemigram|abyss|oceancanvas|bathys|agentic-ai-homelab|/work/'"
chk "timer runs the guarded autosave mode" "grep -qx 'ExecStart=%h/.local/bin/wb-tmux save --auto' '$HERE/tmux/systemd/wb-tmux-save.service'"

echo "== tmux persistence: install (Omarchy-like ~/.config/tmux/tmux.conf)"
home tx-fresh "$BASE$SSH_LINE"$'\n'"$WT_LINE"$'\n'; mkdir -p "$H/.config/tmux"; printf '%s' "$OMARCHY_TMUX" > "$H/.config/tmux/tmux.conf"
tsig() { find "$H/.config/tmux" "$H/.local/share/tmux" "$H/.config/systemd" -printf '%p|%s|%T@\n' 2>/dev/null | sort | md5sum; }
before=$(tsig); run --dry-run
chk "dry-run: CLONE, TMUX and UNIT announced; nothing written; no timer enabled" \
  "[ $(rc) = 0 ] && grep -q '^CLONE tmux plugin tmux-resurrect' '$H.out' && grep -q '^TMUX  append' '$H.out' && grep -q '^UNIT  .*wb-tmux-save.timer' '$H.out' && [ \"\$(tsig)\" = '$before' ] && ! grep -q 'enable --now wb-tmux-save' '$S/calls'"
run
chk "real run: plugin cloned at the PINNED commit (not the source's newer HEAD)" \
  "[ $(rc) = 0 ] && [ \"\$(git -C '$H/.local/share/tmux/plugins/tmux-resurrect' rev-parse HEAD)\" = '$PIN' ]"
chk "real run: source line appended once, as the config's last block; original backed up byte-for-byte" \
  "[ \$(grep -cxF '$TSRC_LINE' '$H/.config/tmux/tmux.conf') = 1 ] && [ \"\$(grep -v '^#' '$H/.config/tmux/tmux.conf' | grep . | tail -1)\" = '$TSRC_LINE' ] && same_as '$H'/.config/tmux/tmux.conf.bak.* \"\$OMARCHY_TMUX\""
chk "real run: Omarchy's own lines kept unchanged in front of the block" \
  "[ \"\$(head -c \$(printf '%s' \"\$OMARCHY_TMUX\" | wc -c) '$H/.config/tmux/tmux.conf' | md5sum)\" = \"\$(printf '%s' \"\$OMARCHY_TMUX\" | md5sum)\" ]"
chk "real run: policy, wb-tmux and both units linked; timer enabled once" \
  "[ \"\$(readlink '$H/.config/tmux/workstation-persistence.conf')\" = '$PC' ] && [ \"\$(readlink '$H/.local/bin/wb-tmux')\" = '$HERE/tmux/wb-tmux' ] && [ \"\$(readlink '$H/.config/systemd/user/wb-tmux-save.timer')\" = '$HERE/tmux/systemd/wb-tmux-save.timer' ] && [ \$(grep -c '^--user enable --now wb-tmux-save.timer\$' '$S/calls') = 1 ]"
chk "never touches a running tmux server: prints the source-file step instead" "grep -q '^NEXT  load it into a running tmux server: tmux source-file ' '$H.out'"
after=$(tsig); : > "$S/calls"; run
chk "rerun: OK for plugin, block and timer; nothing changed; no new backup; no enable" \
  "[ $(rc) = 0 ] && grep -q '^OK    tmux plugin tmux-resurrect at' '$H.out' && grep -q '^OK    tmux persistence already sourced' '$H.out' && grep -q '^OK    wb-tmux-save.timer enabled and active' '$H.out' && [ \"\$(tsig)\" = '$after' ] && [ \$(ls '$H'/.config/tmux/tmux.conf.bak.* | wc -l) = 1 ] && ! grep -q 'enable --now wb-tmux' '$S/calls'"
git -C "$H/.local/share/tmux/plugins/tmux-resurrect" -c advice.detachedHead=false checkout -q master 2>/dev/null || git -C "$H/.local/share/tmux/plugins/tmux-resurrect" -c advice.detachedHead=false checkout -q main
moved=$(git -C "$H/.local/share/tmux/plugins/tmux-resurrect" rev-parse HEAD); run
chk "plugin checkout at another commit: WARN, left exactly where it is" \
  "grep -q '^WARN  tmux plugin tmux-resurrect: .* left unchanged' '$H.out' && [ \"\$(git -C '$H/.local/share/tmux/plugins/tmux-resurrect' rev-parse HEAD)\" = '$moved' ] && [ '$moved' != '$PIN' ]"

echo "== tmux persistence: other configs"
home tx-dotfile "$BASE"; printf 'set -g mouse on\n' > "$H/.tmux.conf"; run
chk "~/.tmux.conf present (tmux loads it first): the block goes there, ~/.config/tmux/tmux.conf not created" \
  "[ \$(grep -cxF '$TSRC_LINE' '$H/.tmux.conf') = 1 ] && [ ! -e '$H/.config/tmux/tmux.conf' ]"
home tx-none "$BASE"; run
chk "no tmux config at all: ~/.config/tmux/tmux.conf created with only the block" \
  "[ -f '$H/.config/tmux/tmux.conf' ] && [ \$(grep -cxF '$TSRC_LINE' '$H/.config/tmux/tmux.conf') = 1 ] && [ -z \"\$(ls '$H'/.config/tmux/tmux.conf.bak.* 2>/dev/null)\" ]"
home tx-nouser "$BASE"; touch "$S/no_user_manager"; run
chk "no systemd user manager: WARN, units still linked, no enable attempted" \
  "[ $(rc) = 0 ] && grep -q '^WARN  tmux persistence: no systemd user manager' '$H.out' && [ -L '$H/.config/systemd/user/wb-tmux-save.timer' ] && ! grep -q 'enable --now wb-tmux' '$S/calls'"

echo "== product skills from a chipi/infra checkout"
for s in ci-watch infra-only; do
  mkdir -p "$T/infra/skills/$s"; printf -- '---\nname: %s\ndescription: x\n---\n' "$s" > "$T/infra/skills/$s/SKILL.md"
done
home sk-none "$BASE"; run
chk "no infra checkout: SKIP line, homelab's own ci-watch linked from this repo" \
  "[ $(rc) = 0 ] && grep -q '^SKIP  chipi/infra skills' '$H.out' && [ \"\$(readlink '$H/.claude/skills/ci-watch')\" = '$HERE/claude/skills/ci-watch' ]"
home sk-infra "$BASE"; INFRA_CHECKOUT="$T/infra" run
chk "infra checkout: its skills linked; the same-named homelab skill not linked; others unchanged" \
  "[ $(rc) = 0 ] && [ \"\$(readlink '$H/.claude/skills/ci-watch')\" = '$T/infra/skills/ci-watch' ] && [ \"\$(readlink '$H/.claude/skills/infra-only')\" = '$T/infra/skills/infra-only' ] && grep -q '^INFRA ci-watch' '$H.out' && [ \"\$(readlink '$H/.claude/skills/ship')\" = '$HERE/claude/skills/ship' ]"
INFRA_CHECKOUT="$T/infra" run
chk "rerun with infra: already linked, no skill backed up (the two loops never relink each other)" \
  "[ $(rc) = 0 ] && grep -q \"^OK    already linked: $H/.claude/skills/ci-watch\$\" '$H.out' && [ -z \"\$(ls -d '$H'/.claude/skills/*.bak.* 2>/dev/null)\" ]"
# A skill backup left in ~/.claude/skills is itself loaded as a skill (same name, other copy).
home sk-move "$BASE"; run; INFRA_CHECKOUT="$T/infra" run
chk "homelab link re-pointed to the infra checkout, no backup left in ~/.claude/skills" \
  "[ $(rc) = 0 ] && [ \"\$(readlink '$H/.claude/skills/ci-watch')\" = '$T/infra/skills/ci-watch' ] && grep -q '^RELINK.*/.claude/skills/ci-watch' '$H.out' && [ -z \"\$(ls -d '$H'/.claude/skills/*.bak.* 2>/dev/null)\" ]"
run
chk "undo: no infra checkout re-points it back to homelab's copy, no backup left" \
  "[ $(rc) = 0 ] && [ \"\$(readlink '$H/.claude/skills/ci-watch')\" = '$HERE/claude/skills/ci-watch' ] && [ -z \"\$(ls -d '$H'/.claude/skills/*.bak.* 2>/dev/null)\" ]"

echo "== only directories with a SKILL.md are skills"
NS="$HERE/claude/skills/zz-test-not-a-skill"
mkdir -p "$NS"; trap 'rm -rf "$T" "$NS"' EXIT
home sk-nonskill "$BASE"; run
chk "a directory without SKILL.md under skills/ is not linked" \
  "[ $(rc) = 0 ] && [ ! -e '$H/.claude/skills/zz-test-not-a-skill' ] && [ ! -L '$H/.claude/skills/zz-test-not-a-skill' ] && [ -L '$H/.claude/skills/ship' ]"
rm -rf "$NS"

echo "== macOS path unchanged"
home mac "$BASE" disabled; before=$(sig); OSV=macos run
chk "no ssh-agent/Worktrunk/storage output, no systemctl calls, .bashrc unchanged" \
  "[ $(rc) = 0 ] && ! grep -qi -e worktrunk -e wb-stream -e wb-storage -e 'storage:' -e ssh-agent -e SSH_AUTH_SOCK '$H.out' && [ ! -s '$S/calls' ] && [ \"\$(sig)\" = '$before' ] && [ ! -e '$H/.config/worktrunk' ]"

echo; echo "RESULT: pass=$pass fail=$fail"
[ "$fail" = 0 ]
