#!/usr/bin/env bash
# secrets-scan: report secrets about to enter (or already in) git, file:line, values redacted.
#   scan.sh                 staged changes (default; what `git commit` would add)
#   scan.sh --push          commits not yet on the upstream (what `git push` would send)
#   scan.sh --range A..B    a commit range
#   scan.sh --tree [PATH]   the working tree as it is (no git history)
# Uses gitleaks when installed (~200 provider rules); otherwise the same high-signal regexes as
# the secrets-guard hook. Ends with "SECRETS SCAN: PASS|FAIL" (exit 1 on FAIL). Never prints a value.
set -uo pipefail
mode=staged; arg=""
case "${1:-}" in
  ""|--staged) mode=staged ;;
  --push) mode=push ;;
  --range) mode=range; arg="${2:?--range needs A..B}" ;;
  --tree) mode=tree; arg="${2:-.}" ;;
  *) echo "usage: scan.sh [--staged|--push|--range A..B|--tree [PATH]]" >&2; exit 2 ;;
esac
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || [ "$mode" = tree ] || { echo "not a git repo" >&2; exit 2; }

if [ "$mode" = push ]; then
  if   git rev-parse --abbrev-ref '@{u}' >/dev/null 2>&1; then arg='@{u}..HEAD'
  elif git rev-parse --verify -q origin/main >/dev/null 2>&1; then arg='origin/main..HEAD'
  else echo "no upstream to compare with" >&2; exit 2; fi
  mode=range
fi
[ "$mode" = range ] && [ -z "$(git rev-list "$arg" 2>/dev/null)" ] && { echo "nothing in $arg"; echo "SECRETS SCAN: PASS"; exit 0; }

# A real .env (not .env.example) entering git is a finding by itself.
envs=""
case "$mode" in
  staged) envs="$(git diff --cached --name-only | grep -E '(^|/)\.env(\.local|\.production|\.prod)?$' || true)" ;;
  range)  envs="$(git diff --name-only "$arg" | grep -E '(^|/)\.env(\.local|\.production|\.prod)?$' || true)" ;;
esac

fail=0
if command -v gitleaks >/dev/null 2>&1; then
  echo "scanner: gitleaks $(gitleaks version 2>/dev/null) ($mode${arg:+ $arg})"
  rep="$(mktemp)"
  case "$mode" in
    staged) gitleaks git --staged --redact --no-banner --log-level error --report-format json --report-path "$rep" . >/dev/null 2>&1 ;;
    range)  gitleaks git --log-opts="$arg" --redact --no-banner --log-level error --report-format json --report-path "$rep" . >/dev/null 2>&1 ;;
    tree)   gitleaks dir --redact --no-banner --log-level error --report-format json --report-path "$rep" "$arg" >/dev/null 2>&1 ;;
  esac
  rc=$?
  skip_patterns=1
  if [ "$rc" = 1 ]; then
    fail=1
    jq -r '.[] | "  \(.File):\(.StartLine) — \(.RuleID)" + (if .Commit != "" then " (commit \(.Commit[0:8]))" else "" end)' "$rep" 2>/dev/null \
      || echo "  (findings present; report unreadable)"
  elif [ "$rc" != 0 ]; then
    echo "  gitleaks failed (exit $rc): falling back to patterns"
    skip_patterns=0
  fi
  rm -f "$rep"
else
  echo "scanner: patterns (gitleaks not installed; brew install gitleaks for the full rule set)"
  skip_patterns=0
fi

if [ "${skip_patterns:-0}" = 0 ]; then
  case "$mode" in
    staged) diff="$(git diff --cached -U0)" ;;
    range)  diff="$(git diff -U0 "$arg")" ;;
    tree)   diff="$(grep -rIn --exclude-dir=.git --exclude-dir=node_modules -E '.' "$arg" 2>/dev/null | sed 's/^/+/')" ;;
  esac
  placeholder='buddy-is-the-king|hf_xxx|<your|\$\{|changeme|change_?me|placeholder|dummy|xxxx+|redacted|example|\.\.\.|test-api-key|test[_-]key|sk-test|test-token|fake-?key|not-?a-?real'
  added="$(printf '%s\n' "$diff" | grep -E '^\+' | grep -Ev '^\+\+\+' | grep -Eiv "$placeholder")"
  while IFS='|' read -r rule pat; do
    if grep -Eq -e "$pat" <<<"$added"; then fail=1; echo "  $rule (run with gitleaks for file:line)"; fi
  done <<'PATTERNS'
Anthropic API key|sk-ant-[A-Za-z0-9_-]{20,}
OpenAI-style key|\bsk-[A-Za-z0-9]{20,}
GitHub token|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}
GitLab PAT|glpat-[A-Za-z0-9_-]{20,}
AWS access key id|AKIA[0-9A-Z]{16}
Google API key|AIza[0-9A-Za-z_-]{20,}
Slack token|xox[baprs]-[A-Za-z0-9-]{10,}
private key block|-----BEGIN [A-Z ]*PRIVATE KEY-----
PATTERNS
fi

if [ -n "$envs" ]; then fail=1; printf '  real .env file in the change: %s\n' $envs; fi
if [ "$fail" = 1 ]; then
  echo "Remove each secret AND rotate it: a secret that reached git is compromised even if deleted later."
  echo "SECRETS SCAN: FAIL"; exit 1
fi
echo "SECRETS SCAN: PASS"
