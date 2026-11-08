#!/usr/bin/env bash
# shellcheck disable=SC2034  # head, before, after and rc are read inside the eval'd check strings
# Test deploy/mini-deploy.sh in a throwaway sandbox: a bare "origin" and a clone as the checkout,
# with test hooks. Cases: pass, red gate -> rollback, dirty refused, no new commits, a failing
# pre-pull hook does not block, a diverged checkout, hooks see PREV/NOW, the temp copy is removed.
# Run: bash deploy/test_mini_deploy.sh deploy/mini-deploy.sh
set -u
SCRIPT="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
export HOME="$T/home"; mkdir -p "$HOME"; export TMPDIR="$T/tmp"; mkdir -p "$TMPDIR"
git config --global user.email t@t; git config --global user.name t; git config --global init.defaultBranch main
fails=0
check() { if eval "$2"; then echo "ok   $1"; else echo "FAIL $1"; fails=$((fails+1)); fi; }

git init -q --bare "$T/origin.git"
git clone -q "$T/origin.git" "$T/work"
cd "$T/work" || exit 1
mkdir -p deploy/hooks/pre-pull.d deploy/hooks/gate.d deploy/hooks/rollback.d
cp "$SCRIPT" deploy/mini-deploy.sh
printf 'echo "pre PREV=$PREV"\n' > deploy/hooks/pre-pull.d/10-pre.sh
printf '[ -f "$CHECKOUT/RED" ] && { echo "gate red at $NOW"; exit 3; }; echo "gate green PREV=$PREV NOW=$NOW"\n' > deploy/hooks/gate.d/10-gate.sh
printf 'echo "rolled back from $NOW to $PREV" >> "$HOME/rollback.log"\n' > deploy/hooks/rollback.d/10-log.sh
echo 1 > f; git add -A; git commit -qm one; git push -q origin main
git clone -q "$T/origin.git" "$T/checkout"
export HOMELAB_CHECKOUT="$T/checkout"
push() { (cd "$T/work" && echo "$1" > f && { [ "${2:-}" = red ] && touch RED || rm -f RED; } && git add -A && git commit -qm "$1" && git push -q origin main); }
run() { bash "$T/checkout/deploy/mini-deploy.sh" > "$T/out" 2>&1; echo $?; }

# 1. a green change deploys
push two
rc=$(run); head="$(git -C "$T/checkout" log -1 --format=%s)"
check "green: exit 0" '[ "$rc" = 0 ]'
check "green: DEPLOY PASS line" 'grep -q "^DEPLOY PASS (" "$T/out"'
check "green: checkout moved to the new commit" '[ "$head" = two ]'
check "green: gate saw PREV and NOW" 'grep -q "gate green PREV=[0-9a-f]* NOW=[0-9a-f]*" "$T/out"'
check "green: pre-pull hook ran with PREV" 'grep -q "pre PREV=[0-9a-f]" "$T/out"'
check "green: no copy left behind" '[ -z "$(ls "$TMPDIR" | grep mini-deploy)" ]'

# 2. a red change rolls back
before="$(git -C "$T/checkout" rev-parse --short HEAD)"
push three red
rc=$(run); after="$(git -C "$T/checkout" rev-parse --short HEAD)"
check "red: exit non-zero" '[ "$rc" != 0 ]'
check "red: DEPLOY FAIL rolled back" 'grep -q "^DEPLOY FAIL: rolled back to $before" "$T/out"'
check "red: checkout back on the previous commit" '[ "$after" = "$before" ]'
check "red: rollback hook ran" 'grep -q "to $before" "$HOME/rollback.log"'

# 3. a dirty checkout is refused and left alone
echo junk > "$T/checkout/junk"
rc=$(run)
check "dirty: refused" '[ "$rc" != 0 ] && grep -q "checkout is dirty" "$T/out"'
check "dirty: file untouched" '[ -f "$T/checkout/junk" ]'
rm "$T/checkout/junk"

# 4. fix forward: green again, and a no-new-commits re-run re-verifies
push four
rc=$(run); check "fix forward: deploys" '[ "$rc" = 0 ] && [ "$(git -C "$T/checkout" log -1 --format=%s)" = four ]'
rc=$(run); check "no new commits: still verifies and passes" '[ "$rc" = 0 ] && grep -q "no new commits" "$T/out"'

# 5. a failing pre-pull hook does not block
printf 'exit 7\n' > "$T/work/deploy/hooks/pre-pull.d/20-broken.sh"
(cd "$T/work" && git add -A && git commit -qm five && git push -q origin main)
rc=$(run)   # the broken hook arrives with this pull; it runs on the NEXT deploy
push six
rc=$(run)
check "pre-pull failure: deploy continues" '[ "$rc" = 0 ] && grep -q "pre-pull: a hook failed (the deploy continues)" "$T/out"'

# 6. a diverged checkout fails without changes
(cd "$T/checkout" && echo local > g && git add g && git commit -qm local)
push seven
rc=$(run)
check "diverged: pull fails, nothing changed" '[ "$rc" != 0 ] && grep -q "pull --ff-only failed" "$T/out"'

echo "bash: $BASH_VERSION"
[ "$fails" -eq 0 ] && echo "MINI-DEPLOY TESTS PASS" || { echo "MINI-DEPLOY TESTS FAIL ($fails)"; sed 's/^/  | /' "$T/out"; exit 1; }
