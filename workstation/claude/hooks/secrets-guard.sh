#!/usr/bin/env bash
# secrets-guard.sh — Claude Code PreToolUse hook (Bash matcher). Blocks a
# `git commit` / `git push` when the change about to enter (or leave) git trips a
# secret scan — automating the non-negotiable "never commit secrets" (AGENTS.md
# #29). Companion to the secrets-scan skill: this is the fast, automatic net;
# /secrets-scan (which prefers gitleaks) stays the thorough, on-demand report.
#
# PreToolUse contract: reads {tool_name, tool_input.command, cwd} as JSON on stdin.
# On a detected secret it prints a `deny` decision (exit 0) → the tool call is
# blocked with a redacted reason. EVERY other path allows (exit 0, no output):
# non-git commands, clean diffs, and any internal error. Fail-open by design — a
# broken guard must never brick the operator's git.
#
# Coverage: the high-signal regex set shared with the secrets-scan skill (no
# external deps). Catches common secret shapes, not everything — the ship ritual +
# /secrets-scan (gitleaks) remain the thorough gate before a push. Values are never
# echoed; findings report the rule name only.

set -uo pipefail   # deliberately NOT -e: internal errors must fail-open, not block

allow() { exit 0; }   # allow the tool call (no output = normal permission flow)

deny() {              # block with a redacted reason (exit 0 + PreToolUse deny)
    jq -n --arg r "$1" \
      '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}' \
      2>/dev/null \
      || printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"secrets-guard: potential secret in the change; run /secrets-scan"}}\n'
    exit 0
}

command -v jq >/dev/null 2>&1 || allow          # no jq → can't parse payload → fail-open
payload="$(cat 2>/dev/null)" || allow
cmd="$(printf '%s' "$payload" | jq -r '.tool_input.command // empty' 2>/dev/null)" || allow
cwd="$(printf '%s' "$payload" | jq -r '.cwd // empty' 2>/dev/null)"
[ -n "$cmd" ] || allow

# Is this a git commit / push? Loose but safe: a block only ever fires on a real
# secret, so matching extra git commands widens the net, it never mis-blocks.
printf '%s' "$cmd" | grep -Eiq '\bgit\b' || allow
is_push=0; is_commit=0
printf '%s' "$cmd" | grep -Eiq '\bpush\b'   && is_push=1
printf '%s' "$cmd" | grep -Eiq '\bcommit\b' && is_commit=1
[ "$is_push" = 1 ] || [ "$is_commit" = 1 ] || allow

# Operate in the repo the command targets.
[ -n "$cwd" ] && { cd "$cwd" 2>/dev/null || allow; }
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || allow

# --- select the diff about to enter/leave git ---
diff=""; names=""
if [ "$is_commit" = 1 ]; then
    # `-a`/`--all`/`-am` stage tracked mods at commit time → scan those too.
    if printf '%s' "$cmd" | grep -Eiq '( -[a-z]*a[a-z]*| --all)( |$|"|'"'"'|;|&|\|)'; then
        diff="$(git diff HEAD 2>/dev/null)"; names="$(git diff HEAD --name-only 2>/dev/null)"
    else
        diff="$(git diff --cached 2>/dev/null)"; names="$(git diff --cached --name-only 2>/dev/null)"
    fi
else
    # push: scan the outgoing commit range, best-effort; fail-open if unknown.
    rng=""
    if   git rev-parse --abbrev-ref '@{u}'      >/dev/null 2>&1; then rng='@{u}..HEAD'
    elif git rev-parse --verify -q origin/HEAD  >/dev/null 2>&1; then rng='origin/HEAD..HEAD'
    elif git rev-parse --verify -q origin/main  >/dev/null 2>&1; then rng='origin/main..HEAD'
    fi
    [ -n "$rng" ] || allow
    diff="$(git diff "$rng" 2>/dev/null)"; names="$(git diff "$rng" --name-only 2>/dev/null)"
fi
[ -n "$diff" ] || allow

# --- scan only ADDED lines; drop obvious placeholders ---
added="$(printf '%s\n' "$diff" | grep -E '^\+' | grep -Ev '^\+\+\+')"
placeholder='buddy-is-the-king|hf_xxx|<your|\$\{|changeme|change_?me|placeholder|dummy|xxxx+|redacted|example|\.\.\.'
scan="$(printf '%s\n' "$added" | grep -Eiv "$placeholder")"

hits=""
hit() { grep -Eq -e "$1" <<<"$scan" && hits="${hits}  - ${2}"$'\n'; }
hit 'sk-ant-[A-Za-z0-9_-]{20,}'                            'Anthropic API key (sk-ant-…)'
hit '\bsk-[A-Za-z0-9]{20,}'                                'OpenAI-style key (sk-…)'
hit 'ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}'    'GitHub token'
hit 'glpat-[A-Za-z0-9_-]{20,}'                             'GitLab PAT (glpat-…)'
hit 'AKIA[0-9A-Z]{16}'                                     'AWS access key id (AKIA…)'
hit 'AIza[0-9A-Za-z_-]{20,}'                               'Google API key (AIza…)'
hit 'xox[baprs]-[A-Za-z0-9-]{10,}'                         'Slack token (xox…)'
hit '-----BEGIN [A-Z ]*PRIVATE KEY-----'                  'private key block'
hit '(api[_-]?key|secret|token|password|passwd|bearer|auth)["'"'"' ]*[:=][ "'"'"']*[A-Za-z0-9/+._-]{16,}' 'generic secret assignment'

# a real .env (not .env.example / .env.sample) entering git
if printf '%s\n' "$names" | grep -Eq '(^|/)\.env(\.local|\.production|\.prod)?$'; then
    hits="${hits}  - real .env file in the change"$'\n'
fi

[ -n "$hits" ] || allow

verb="commit"; [ "$is_push" = 1 ] && verb="push"
deny "secrets-guard blocked this git ${verb} — the change matches secret patterns:
${hits}Remove the secret and rotate it (a secret in git is compromised even if later deleted). Run /secrets-scan for file:line detail, or run the git command in a terminal outside Claude to override."
