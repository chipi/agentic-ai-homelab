#!/usr/bin/env bash
# Tests for wb-recovery with synthetic secrets only. Scratch HOME, GNUPGHOME and runtime
# dir; the passphrase comes from a file descriptor (WB_RECOVERY_PASSPHRASE_FD), never argv.
#   bash workstation/recovery/wb-recovery.test.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; CMD="$HERE/wb-recovery"; REPO="$(cd "$HERE/../.." && pwd)"
for c in gpg tar sha256sum file; do command -v "$c" >/dev/null || { echo "SKIP: $c not installed"; exit 0; }; done
T="$(mktemp -d)"; trap '[ -n "${WBR_TEST_KEEP:-}" ] && echo "kept $T" || rm -rf "$T"' EXIT
pass=0; fail=0
chk() { if eval "$2"; then echo "  ok   $1"; pass=$((pass+1)); else echo "  FAIL $1"; fail=$((fail+1)); fi; }

REPO_BEFORE=$(git -C "$REPO" status --porcelain | md5sum)
export HOME="$T/home" GNUPGHOME="$T/gnupg" XDG_RUNTIME_DIR="$T/run" WB_RECOVERY_MANIFEST="$T/home/.config/wb-recovery/manifest.tsv"
mkdir -p "$HOME/.config/wb-recovery" "$GNUPGHOME" "$XDG_RUNTIME_DIR" "$T/out"; chmod 700 "$GNUPGHOME" "$XDG_RUNTIME_DIR"
R=$RANDOM$RANDOM
S1="SYNTH-SECRET-one-$R"; S2="SYNTH-SECRET-two-$R"; S3="SYNTH-SECRET-mem-$R"; SX="SYNTH-SECRET-excluded-$R"; SC="SYNTH-SECRET-codified-$R"; SU="SYNTH-SECRET-unlisted-$R"
P="$T/live/proj"; mkdir -p "$P" "$T/live/mem/sub"
printf 'API_KEY=%s\n' "$S1" > "$P/.env"; chmod 600 "$P/.env"
ODD="$P/My Override (local) \$weird & 'q'.yml"; printf 'token: %s\n' "$S2" > "$ODD"; chmod 640 "$ODD"
printf 'note %s\n' "$S3" > "$T/live/mem/a.md"; printf 'n2\n' > "$T/live/mem/sub/b.md"
printf '%s\n' "$SX" > "$P/.env.workspace"; printf '%s\n' "$SC" > "$P/.env.example"; printf '%s\n' "$SU" > "$P/unlisted.txt"
printf 'correct horse battery staple %s\n' "$R" > "$T/pass"; printf 'wrong passphrase\n' > "$T/badpass"
manifest() {
  printf '# test manifest\n'
  printf 'REQUIRED_PRIVATE\t%s\tsecrets\n' "$P/.env"
  printf 'REQUIRED_PRIVATE\t%s\todd name\n' "$ODD"
  printf 'OPTIONAL_PRIVATE\t%s\tmemory dir\n' "$T/live/mem"
  printf 'OPTIONAL_PRIVATE\t%s\tabsent\n' "$P/not-there"
  printf 'EXCLUDED\t%s\tgenerated\n' "$P/.env.workspace"
  printf 'CODIFIED\t%s\tin git\n' "$P/.env.example"
}
manifest > "$WB_RECOVERY_MANIFEST"
wr()  { WB_RECOVERY_PASSPHRASE_FD=3 "$CMD" "$@" 3<"$T/pass"; }
wrb() { WB_RECOVERY_PASSPHRASE_FD=3 "$CMD" "$@" 3<"$T/badpass"; }
no_secrets() { ! grep -qaE "SYNTH-SECRET|correct horse" "$@"; }
no_stage() { [ -z "$(find "$XDG_RUNTIME_DIR" -maxdepth 1 -name 'wb-recovery-stage.*')" ]; }
src_sig() { (cd "$T/live" && find . -type f -printf '%p|%s|%m|%T@\n' | sort; find . -type f -exec sha256sum {} + | sort) | md5sum; }
SRC_BEFORE=$(src_sig)

echo "== inventory"
"$CMD" inventory > "$T/inv.out" 2>&1; rc=$?
chk "inventory: exit 0, lists hashes, skips the missing optional, prints no secret" \
  "[ $rc = 0 ] && grep -q 'included files: 4' '$T/inv.out' && grep -q 'skip    optional' '$T/inv.out' && grep -q \"sha256=\$(sha256sum < '$P/.env' | cut -d' ' -f1)\" '$T/inv.out' && no_secrets '$T/inv.out'"

echo "== backup"
wr backup -o "$T/out" > "$T/b.out" 2>&1; rc=$?
B=$(ls "$T"/out/*.tar.gpg 2>/dev/null | head -1)
chk "backup: exit 0, one bundle + sha256 sidecar, both 0600" "[ $rc = 0 ] && [ -f '$B' ] && [ \$(stat -c %a '$B') = 600 ] && [ \$(stat -c %a '$B.sha256') = 600 ]"
chk "backup reports 4 entries and the encrypted sha256 that the sidecar holds" "grep -q '^entries:  4' '$T/b.out' && grep -q \"^sha256:   \$(sha256sum < '$B' | cut -d' ' -f1)\" '$T/b.out'"
chk "the artifact is OpenPGP symmetric-encrypted data" "file -b '$B' | grep -qiE 'PGP|GPG' && gpg --list-packets --batch --passphrase '' '$B' 2>&1 | grep -q 'symkey enc packet'"
chk "no secret or passphrase string anywhere in the encrypted bytes" "no_secrets '$B' '$B.sha256'"
chk "no secret in backup stdout/stderr" "no_secrets '$T/b.out'"
chk "no plaintext staging left after success; no .partial file" "no_stage && [ -z \"\$(ls -A '$T/out' | grep partial)\" ]"
chk "sources untouched (contents, modes, mtimes)" "[ \"\$(src_sig)\" = '$SRC_BEFORE' ]"
chk "the passphrase is only ever passed by fd: no --passphrase <value> in the tool" "! grep -nE -- '--passphrase[[:space:]]' '$CMD' | grep -v 'passphrase-fd'"
gpg --batch --pinentry-mode loopback --passphrase-fd 3 --decrypt "$B" 3<"$T/pass" 2>/dev/null | tar -tf - | sort > "$T/members"
ODD_IN=0; grep -qxF -- "${ODD#/}" "$T/members" && ODD_IN=1   # outside eval: the name has $ & and quotes
chk "archive holds exactly MANIFEST.tsv + the 2 required + 2 optional files (odd filename included)" "[ \$(wc -l < '$T/members') = 5 ] && grep -qx MANIFEST.tsv '$T/members' && grep -qxF '${P#/}/.env' '$T/members' && [ $ODD_IN = 1 ]"
chk "EXCLUDED, CODIFIED and unlisted files are not in the archive" "! grep -qE 'env\\.workspace|env\\.example|unlisted' '$T/members'"
gpg --batch --pinentry-mode loopback --passphrase-fd 3 --decrypt "$B" 3<"$T/pass" 2>/dev/null | tar -xOf - MANIFEST.tsv > "$T/man"
chk "embedded manifest: one record per file with its real sha256, mode and size" \
  "[ \$(grep -vc '^#' '$T/man') = 4 ] && awk -F'\t' '!/^#/ && \$7 == \"${P#/}/.env\"' '$T/man' | grep -q \"^\$(sha256sum < '$P/.env' | cut -d' ' -f1)	600	\$(stat -c %s '$P/.env')	\""

echo "== verify"
wr verify "$B" > "$T/v.out" 2>&1; rc=$?
chk "correct passphrase: verified 4 entries (hash, mode, size); no secret printed" "[ $rc = 0 ] && grep -q '^verified: 4 entries' '$T/v.out' && grep -q 'encrypted sha256 ok' '$T/v.out' && no_secrets '$T/v.out'"
wrb verify "$B" > "$T/vb.out" 2>&1; rc=$?
chk "wrong passphrase: fails (exit 1), no staging left" "[ $rc = 1 ] && grep -q 'DECRYPTION FAILED' '$T/vb.out' && no_stage"
cp "$B" "$T/tampered.gpg"; sz=$(stat -c %s "$B"); printf '\xff' | dd of="$T/tampered.gpg" bs=1 seek=$((sz/2)) conv=notrunc status=none
wr verify "$T/tampered.gpg" --sha256 "$(cut -d' ' -f1 "$B.sha256")" > "$T/vt.out" 2>&1; rc=$?
chk "one flipped byte, expected sha256 given: ENCRYPTED SHA-256 MISMATCH" "[ $rc = 1 ] && grep -q 'ENCRYPTED SHA-256 MISMATCH' '$T/vt.out'"
wr verify "$T/tampered.gpg" > "$T/vt2.out" 2>&1; rc=$?
chk "one flipped byte, no expected sha256: OpenPGP integrity check still fails it" "[ $rc = 1 ] && grep -q 'DECRYPTION FAILED' '$T/vt2.out' && no_stage"
head -c $((sz - 40)) "$B" > "$T/trunc.gpg"; wr verify "$T/trunc.gpg" > "$T/vtr.out" 2>&1; rc=$?
chk "truncated bundle fails" "[ $rc = 1 ]"

mkdir -p "$T/forge/s"; printf 'not what the manifest says\n' > "$T/forge/s/f"
{ printf '# wb-recovery/1\tcreated=x\thost=x\tentries=1\n'; printf '%s\t644\t%s\t0\tx:x\tREQUIRED_PRIVATE\ts/f\n' "$(printf 'other' | sha256sum | cut -d' ' -f1)" "$(stat -c %s "$T/forge/s/f")"; } > "$T/forge/MANIFEST.tsv"
chmod 644 "$T/forge/s/f"; tar -cf - -C "$T/forge" MANIFEST.tsv s/f | gpg --batch --quiet --pinentry-mode loopback --passphrase-fd 3 --symmetric -o "$T/forged.gpg" 3<"$T/pass"
wr verify "$T/forged.gpg" > "$T/vf.out" 2>&1; rc=$?
chk "a validly encrypted bundle whose manifest lies about a hash fails verify" "[ $rc = 1 ] && grep -q 'MISMATCH between' '$T/vf.out'"
tar -cf - -C "$T/forge" MANIFEST.tsv s/f -C "$P" unlisted.txt | gpg --batch --quiet --pinentry-mode loopback --passphrase-fd 3 --symmetric -o "$T/extra.gpg" 3<"$T/pass"
wr verify "$T/extra.gpg" > "$T/ve.out" 2>&1; rc=$?
chk "a bundle with an entry its manifest does not list fails verify" "[ $rc = 1 ] && grep -q 'MISMATCH between' '$T/ve.out' && no_secrets '$T/ve.out'"

echo "== fail closed"
mv "$P/.env" "$P/.env.away"; SB=$(ls "$T/out" | wc -l)
wr backup -o "$T/out" > "$T/m.out" 2>&1; rc=$?
chk "a missing REQUIRED file: exit 1, MISSING reported, no new bundle, no staging" "[ $rc = 1 ] && grep -q 'MISSING required' '$T/m.out' && [ \$(ls '$T/out' | wc -l) = $SB ] && no_stage"
mv "$P/.env.away" "$P/.env"
ln -s "$P/.env" "$P/link.env"; { manifest; printf 'REQUIRED_PRIVATE\t%s\tlink\n' "$P/link.env"; } > "$WB_RECOVERY_MANIFEST"
wr backup -o "$T/out" > "$T/s.out" 2>&1; rc=$?
chk "a symlinked entry is refused, not followed (exit 1, no bundle)" "[ $rc = 1 ] && grep -q 'is a symlink' '$T/s.out' && [ \$(ls '$T/out' | wc -l) = $SB ]"
manifest > "$WB_RECOVERY_MANIFEST"; ln -s /etc/hostname "$T/live/mem/escape"
wr backup -o "$T/out" > "$T/s2.out" 2>&1; rc=$?
chk "a symlink inside a directory entry is refused (no escape)" "[ $rc = 1 ] && grep -q 'contains a symlink' '$T/s2.out' && [ \$(ls '$T/out' | wc -l) = $SB ]"
rm "$T/live/mem/escape"
mkdir -p "$T/ro"; chmod 500 "$T/ro"; wr backup -o "$T/ro" > "$T/ro.out" 2>&1; rc=$?
chk "gpg cannot write the output: exit 1 and still no plaintext staging left" "[ $rc = 1 ] && no_stage && [ -z \"\$(ls -A '$T/ro')\" ]"
chmod 700 "$T/ro"
printf 'BOGUS\t%s\tx\n' "$P/.env" > "$T/badman"; WB_RECOVERY_MANIFEST="$T/badman" wr backup -o "$T/out" > "$T/bm.out" 2>&1; rc=$?
chk "unknown class or relative path in the manifest is rejected" "[ $rc = 2 ] && grep -q 'unknown class' '$T/bm.out'"

echo "== restore-plan (never touches live files)"
LIVE_BEFORE=$(src_sig)
wr restore-plan "$B" > "$T/r.out" 2>&1; rc=$?
RD=$(sed -n 's/^restored into \(.*\) (private.*/\1/p' "$T/r.out")
chk "restores into a fresh private dir under the runtime dir, all files verified" "[ $rc = 0 ] && [[ '$RD' == '$XDG_RUNTIME_DIR'/wb-recovery-restore.* ]] && [ \$(stat -c %a '$RD') = 700 ] && grep -q 'every file matches' '$T/r.out'"
chk "restored files: identical content and preserved modes (600, 640)" \
  "[ -n '$RD' ] && [ -d '$RD' ] && cmp -s '$P/.env' '$RD/${P#/}/.env' && cmp -s \"\$ODD\" \"$RD/\${ODD#/}\" && [ \$(stat -c %a '$RD/${P#/}/.env') = 600 ] && [ \$(stat -c %a \"$RD/\${ODD#/}\") = 640 ]"
chk "plan says 'identical' for unchanged live files and prints no secret" "grep -q 'identical, nothing to do' '$T/r.out' && no_secrets '$T/r.out'"
chk "live files were not touched" "[ \"\$(src_sig)\" = '$LIVE_BEFORE' ]"
printf 'changed\n' >> "$P/.env"; wr restore-plan "$B" > "$T/r2.out" 2>&1; RD2=$(sed -n 's/^restored into \(.*\) (private.*/\1/p' "$T/r2.out")
chk "a changed live file is reported DIFFERS with an install line, and stays changed" "grep -q 'DIFFERS' '$T/r2.out' && grep -q 'install -D -m 600' '$T/r2.out' && tail -1 '$P/.env' | grep -qx changed"
mkdir -p "$T/full"; touch "$T/full/x"; wr restore-plan "$B" --into "$T/full" > "$T/r3.out" 2>&1; rc=$?
chk "restore into a non-empty dir is refused" "[ $rc = 2 ] && grep -q 'not an empty directory' '$T/r3.out'"
wr restore-plan "$B" --into / > "$T/r4.out" 2>&1; rc=$?
chk "restore into / is refused" "[ $rc = 2 ]"
wrb restore-plan "$B" > "$T/r5.out" 2>&1; rc=$?
chk "wrong passphrase on restore: fails and leaves no restore dir" "[ $rc = 1 ] && [ \$(find '$XDG_RUNTIME_DIR' -maxdepth 1 -name 'wb-recovery-restore.*' | wc -l) = 2 ]"
wr restore-plan "$T/forged.gpg" > "$T/r6.out" 2>&1; rc=$?
chk "restore of a bundle whose manifest lies: refused after extraction, the plaintext dir removed" \
  "[ $rc = 1 ] && grep -q 'do not match' '$T/r6.out' && [ \$(find '$XDG_RUNTIME_DIR' -maxdepth 1 -name 'wb-recovery-restore.*' | wc -l) = 2 ]"
"$CMD" discard "$RD" > /dev/null; "$CMD" discard "$RD2" > /dev/null
chk "discard removes the plaintext restore dirs" "[ ! -e '$RD' ] && [ ! -e '$RD2' ] && [ -z \"\$(find '$XDG_RUNTIME_DIR' -maxdepth 1 -name 'wb-recovery-*')\" ]"
"$CMD" discard "$T/full" > "$T/d.out" 2>&1; rc=$?
chk "discard refuses a directory it did not create" "[ $rc = 2 ] && [ -e '$T/full/x' ]"

echo "== repository hygiene"
chk "the test changed nothing in the repository (no secret, bundle or manifest entered it)" "[ \"\$(git -C '$REPO' status --porcelain | md5sum)\" = '$REPO_BEFORE' ]"
chk ".gitignore covers bundles, sidecars, partials and a private manifest next to the tool" \
  "git -C '$REPO' check-ignore -q x.tar.gpg && git -C '$REPO' check-ignore -q x.tar.gpg.sha256 && git -C '$REPO' check-ignore -q .x.tar.gpg.partial && git -C '$REPO' check-ignore -q workstation/recovery/manifest.tsv"
chk "the public example manifest names no real project path" "! grep -vE '^#' '$HERE/manifest.example.tsv' | grep -qE '/work/(orrery|ocean|chemi|abyss|bathys)'"

echo; echo "RESULT: pass=$pass fail=$fail"
[ "$fail" = 0 ]
