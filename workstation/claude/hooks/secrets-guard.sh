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
# Under pipefail, `printf "$big" | grep -q` fails when grep exits early and printf takes SIGPIPE,
# which made every command over the 64 KB pipe buffer skip the scan; tests on $cmd use <<<.
# The C locale makes the char-by-char command parser below linear instead of quadratic.
export LC_ALL=C

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
grep -Eiq '\bgit\b' <<<"$cmd" || allow
is_push=0; is_commit=0
grep -Eiq '\bpush\b'   <<<"$cmd" && is_push=1
grep -Eiq '\bcommit\b' <<<"$cmd" && is_commit=1
[ "$is_push" = 1 ] || [ "$is_commit" = 1 ] || allow

# Where each git commit / push in the command runs. The command is split into segments at
# ; & | ( ) and newlines (quote-aware), the dir is followed through `cd`/`pushd` (a subshell's
# cd ends at its `)`), and each `git … push|commit` is scanned in the repo it runs in, with its
# own `-C`. Only that repo: `cd other && git push` from a session sitting in a repo with its own
# unpushed work must not block on that work (2026-11-04), and `cd clean && cd dirty && git push`
# must scan dirty. When the dir cannot be known (`cd $var`, `cd -`, a dir that does not exist,
# --git-dir / GIT_DIR) or no git commit/push parses although the words are there
# (`bash -c "git push"`, eval), the cwd and every dir the command names are scanned instead.
SEP=$'\x1f'
W=()
split_words() {  # split_words <segment> → W: shell words, quotes removed
    local s="$1" i=0 n=${#1} c q="" w="" have=0
    W=()
    while [ "$i" -lt "$n" ]; do
        c="${s:i:1}"
        if [ -n "$q" ]; then
            if [ "$c" = "$q" ]; then q=""
            elif [ "$q" = '"' ] && [ "$c" = '\' ]; then i=$((i+1)); w+="${s:i:1}"
            else w+="$c"; fi
        else
            case "$c" in
                \"|\') q="$c"; have=1 ;;
                \\) i=$((i+1)); w+="${s:i:1}"; have=1 ;;
                ' '|$'\t') [ "$have" = 1 ] && W+=("$w"); w=""; have=0 ;;
                *) w+="$c"; have=1 ;;
            esac
        fi
        i=$((i+1))
    done
    [ "$have" = 1 ] && W+=("$w")
    return 0
}
resolve() {  # resolve <dir> <base> → an existing absolute dir, or "?" when it cannot be known
    local t="${1/#\~/$HOME}"
    case "$t" in ''|-|*'$'*|*'`'*) printf '?'; return ;; esac
    case "$t" in /*) ;; *) [ "$2" = "?" ] && { printf '?'; return; }; t="$2/$t" ;; esac
    if [ -d "$t" ]; then printf '%s' "$t"; else printf '?'; fi
}

# Bash string indexing makes this loop quadratic: 0.5 s at 20 KB, 9.5 s at 100 KB, 143 s at 400 KB
# (measured 2026-11-05), and a hook that times out lets the command through. A longer command
# (a heredoc commit message) is not parsed: n=0 leaves no jobs, so the fallback below scans.
segs=(); ops=(); cur=""; q=""; i=0; n=${#cmd}; [ "$n" -gt 16384 ] && n=0
while [ "$i" -lt "$n" ]; do
    c="${cmd:i:1}"
    if [ -n "$q" ]; then
        cur+="$c"
        if [ "$c" = "$q" ]; then q=""
        elif [ "$q" = '"' ] && [ "$c" = '\' ]; then i=$((i+1)); cur+="${cmd:i:1}"; fi
    else
        case "$c" in
            \"|\') q="$c"; cur+="$c" ;;
            \\) cur+="${cmd:i:2}"; i=$((i+1)) ;;
            ';'|'&'|'|'|'('|')'|$'\n') segs+=("$cur"); ops+=("$c"); cur="" ;;
            *) cur+="$c" ;;
        esac
    fi
    i=$((i+1))
done
segs+=("$cur"); ops+=("")

here="${cwd:-$PWD}"; stack=(); named=(); unknown=0
job_kind=(); job_dir=(); job_args=()
for k in "${!segs[@]}"; do
    split_words "${segs[k]}"
    j=0; gd=0
    while [ "$j" -lt "${#W[@]}" ]; do  # leading keywords, wrappers and VAR=value assignments
        case "${W[j]}" in
            do|then|else|elif|if|while|until|'{'|'!'|time|command|exec|nice|nohup|sudo|env) j=$((j+1)) ;;
            GIT_DIR=*|GIT_WORK_TREE=*) gd=1; j=$((j+1)) ;;
            [A-Za-z_]*=*) j=$((j+1)) ;;
            *) break ;;
        esac
    done
    word="${W[j]:-}"
    case "$word" in
        cd|pushd)
            if [ -z "${W[j+1]:-}" ]; then here="$HOME"; else here="$(resolve "${W[j+1]}" "$here")"; fi
            [ "$here" != "?" ] && named+=("$here") ;;
        popd) here="?" ;;
        git|*/git)
            gdir="$here"; sub=""; m=$((j+1))
            while [ "$m" -lt "${#W[@]}" ]; do
                case "${W[m]}" in
                    -C) gdir="$(resolve "${W[m+1]:-}" "$gdir")"; [ "$gdir" != "?" ] && named+=("$gdir"); m=$((m+2)) ;;
                    -c|--namespace|--config-env) m=$((m+2)) ;;
                    --git-dir*|--work-tree*) gd=1; m=$((m+1)) ;;
                    -*) m=$((m+1)) ;;
                    *) sub="${W[m]}"; break ;;
                esac
            done
            [ "$gd" = 1 ] && gdir="?"
            case "$sub" in push|commit)
                [ "$gdir" = "?" ] && unknown=1
                a=""; for x in "${W[@]:m+1}"; do a+="$x$SEP"; done
                job_kind+=("$sub"); job_dir+=("$gdir"); job_args+=("$a") ;;
            esac ;;
    esac
    case "${ops[k]}" in
        '(') stack+=("$here") ;;
        ')') if [ "${#stack[@]}" -gt 0 ]; then
                 here="${stack[${#stack[@]}-1]}"; unset 'stack[${#stack[@]}-1]'; stack=(${stack[@]+"${stack[@]}"})
             fi ;;
    esac
done
if [ "${#job_kind[@]}" = 0 ] || [ "$unknown" = 1 ]; then
    # also any dir after cd/pushd/-C anywhere in the text, quotes included (`bash -c "cd x && git push"`).
    # A relative one is tried against the cwd and every absolute dir found, since its base is not
    # known (`cd $X && git -C sub push`): a `sub` under any of them is scanned. Under a dir only
    # named by a variable it stays unscanned.
    rel=()
    while IFS= read -r t; do
        t="${t#*[[:space:]]}"; t="${t#[\"\']}"; t="${t%[\"\']}"; t="${t/#\~/$HOME}"
        case "$t" in
            /*) [ -d "$t" ] && named+=("$t") ;;
            ''|-|*'$'*|*'`'*) ;;
            *) rel+=("$t") ;;
        esac
    done < <(printf '%s\n' "$cmd" | grep -oE '(cd|pushd|-C)[[:space:]]+[^[:space:];&|()"'"'"']+')
    for t in ${rel[@]+"${rel[@]}"}; do
        for b in "${cwd:-$PWD}" ${named[@]+"${named[@]}"}; do [ -d "$b/$t" ] && named+=("$b/$t"); done
    done
    for d in "${cwd:-$PWD}" ${named[@]+"${named[@]}"}; do
        [ "$is_push" = 1 ]   && { job_kind+=(push);   job_dir+=("$d"); job_args+=(""); }
        [ "$is_commit" = 1 ] && { job_kind+=(commit); job_dir+=("$d"); job_args+=(""); }
    done
fi

# owner/repo of a URL or a remote's URL, so a push to a URL is matched to the remote it names
slug() { local u="${1%/}"; u="${u%.git}"; u="${u//://}"; printf '%s' "${u#"${u%/*/*}/"}" | tr 'A-Z' 'a-z'; }

# push: the patches of the commits the pushed remote does not have yet — what the push adds.
# Only that remote's refs count as published, so a commit already on a fork or backup remote is
# still scanned. A tree diff against the upstream (the old way) also took in every commit a
# rebase brought from main, which is already published, and blocked on it. `--cc` keeps a
# secret added in a merge commit itself.
scan_push() {  # scan_push <-p|--name-only> <args, SEP-separated>
    local ex=() revs=() r t s rs repo="" all=0 nonopt=0 skip=0 args=()
    IFS="$SEP" read -ra args <<<"$2"
    for t in ${args[@]+"${args[@]}"}; do
        if [ "$skip" = 1 ]; then skip=0; continue; fi
        case "$t" in
            --all|--mirror|--branches) all=1; continue ;;
            --repo) skip=2; continue ;;
            --repo=*) repo="${t#--repo=}"; continue ;;
            -o|--push-option|--receive-pack|--exec) skip=1; continue ;;
            -*) continue ;;
        esac
        if [ "$skip" = 2 ]; then repo="$t"; skip=0; continue; fi
        nonopt=$((nonopt+1))
        if [ "$nonopt" = 1 ] && [ -z "$repo" ]; then repo="$t"; continue; fi
        t="${t#+}"; [ -n "${t%%:*}" ] && git rev-parse --verify -q "${t%%:*}^{commit}" >/dev/null && revs+=("${t%%:*}")
    done
    rs="$(git remote 2>/dev/null)"
    if [ -z "$rs" ]; then
        git rev-parse --abbrev-ref '@{u}' >/dev/null 2>&1 || return 0
        git diff "$1" '@{u}..HEAD' 2>/dev/null; return 0
    fi
    [ -n "$repo" ] || repo="$(git config "branch.$(git branch --show-current 2>/dev/null).remote" 2>/dev/null)"
    if [ -n "$repo" ]; then
        if grep -qxF -- "$repo" <<<"$rs"; then ex+=("--remotes=$repo")
        else
            s="$(slug "$repo")"
            for r in $rs; do [ "$(slug "$(git remote get-url "$r" 2>/dev/null)")" = "$s" ] && ex+=("--remotes=$r"); done
        fi
    fi
    if [ "${#ex[@]}" = 0 ]; then
        if grep -qx origin <<<"$rs"; then ex=(--remotes=origin); else ex=(--remotes); fi
    fi
    [ "$all" = 1 ] && revs+=(--branches)
    [ "${#revs[@]}" -gt 0 ] || revs=(HEAD)
    git log "$1" --cc --format= "${revs[@]}" --not "${ex[@]}" 2>/dev/null
}

# --- select the diff about to enter/leave git, in the repo each git command runs in ---
diff=""; names=""; seen="$SEP"
for k in "${!job_kind[@]}"; do
    top="$(git -C "${job_dir[k]}" rev-parse --show-toplevel 2>/dev/null)" || continue
    key="${job_kind[k]} $top ${job_args[k]}"
    case "$seen" in *"$SEP$key$SEP"*) continue ;; esac
    seen+="$key$SEP"
    cd "$top" 2>/dev/null || continue
    if [ "${job_kind[k]}" = commit ]; then
        # `-a`/`--all`/`-am` stage tracked mods at commit time → scan those too. Without parsed
        # args (the fallback), the command text decides, as before.
        a="${job_args[k]:-$cmd}"
        if grep -Eiq '(^| )(-[a-z]*a[a-z]*|--all)( |$|"|'"'"'|;|&|\|)' <<<"${a//$SEP/ }"; then
            diff+="$(git diff HEAD 2>/dev/null)"$'\n'; names+="$(git diff HEAD --name-only 2>/dev/null)"$'\n'
        else
            diff+="$(git diff --cached 2>/dev/null)"$'\n'; names+="$(git diff --cached --name-only 2>/dev/null)"$'\n'
        fi
    else
        diff+="$(scan_push -p "${job_args[k]}")"$'\n'; names+="$(scan_push --name-only "${job_args[k]}")"$'\n'
    fi
done
[ -n "${diff//[[:space:]]/}" ] || allow

# --- scan only ADDED lines; drop obvious placeholders ---
# One narrow exception (operator, 2026-11-05): eval-harness (evh) manifests map item ids to the
# sha256 of each item, and gitleaks' generic-api-key fires on an id like `…compose-api-1` beside a
# 64-hex value. A line is skipped only when all three hold: the file is an evh manifest
# (data/references/<set>/<ref>/manifest.json, data/datasets/<name>.json), the line is exactly
# `"<id>": "<64 lowercase hex>"`, and the id names no secret (key, secret, token, passw, auth,
# bearer, credential). `"api_key": "<64 hex>"` in a manifest is still scanned. Written without
# regex intervals so macOS awk runs it too.
# A second one (operator, 2026-11-08): Go's go.sum lists each module with its public checksum, and
# gitleaks fires on a module named like a secret (`modernc.org/token v1.1.0 h1:<hash>=`). A line is
# skipped only in a file named go.sum and only when it is exactly `<module> <version>[/go.mod]
# h1:<43 base64 characters>=`. Anything else in a go.sum is still scanned.
added="$(printf '%s\n' "$diff" | awk '
  /^\+\+\+ / { f = $2; sub(/^b\//, "", f); next }
  /^\+/ {
    if (f ~ /(^|\/)go\.sum$/) {
      line = $0; sub(/^\+/, "", line)
      if (line ~ /^[A-Za-z0-9._~\/-]+ v[A-Za-z0-9.+_-]+(\/go\.mod)? h1:[A-Za-z0-9+\/]+=$/) {
        h = line; sub(/^.* h1:/, "", h)
        if (length(h) == 44) next
      }
    }
    if (f ~ /(^|\/)data\/references\/[^\/]+\/[^\/]+\/manifest\.json$/ || f ~ /(^|\/)data\/datasets\/[^\/]+\.json$/) {
      line = $0; sub(/^\+[ \t]*/, "", line)
      if (line ~ /^"[^"]*"[ \t]*:[ \t]*"[0-9a-f]+",?[ \t]*$/) {
        id = line; sub(/^"/, "", id); sub(/".*$/, "", id)
        v = line; sub(/^"[^"]*"[ \t]*:[ \t]*"/, "", v); sub(/".*$/, "", v)
        if (length(v) == 64 && tolower(id) !~ /(key|secret|token|passw|auth|bearer|credential)/) next
      }
    }
    print
  }')"
placeholder='buddy-is-the-king|hf_xxx|<your|\$\{|changeme|change_?me|placeholder|dummy|xxxx+|redacted|example|\.\.\.|test-api-key|test[_-]key|sk-test|test-token|test_token|fake-?key|not-?a-?real'
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
# The VALUE must look like a secret, not code: a quoted literal (>=16 chars, dots allowed inside
# quotes) OR a long unquoted run (>=24 chars, NO dot — so a dotted/underscored code expression like
# `token = _episode_fuse.set(fuse)` or `auth = terminal_message(...)` can't reach the length and is
# not mistaken for a secret). Real keys are quoted in code or long+unquoted in .env-style lines.
hit '(api[_-]?key|secret|token|password|passwd|bearer|auth)["'"'"' ]*[:=][ ]*(["'"'"'][A-Za-z0-9/+._=-]{16,}|[A-Za-z0-9/+_=-]{24,})' 'generic secret assignment'

# a real .env (not .env.example / .env.sample) entering git
if grep -Eq '(^|/)\.env(\.local|\.production|\.prod)?$' <<<"$names"; then
    hits="${hits}  - real .env file in the change"$'\n'
fi

# --- gitleaks, when installed: its ~200 provider rules catch shapes the regexes above don't
# (Stripe, Twilio, SendGrid, …). Same placeholder-filtered added lines; rule ids only, never
# values (--redact). Fail-open: a gitleaks error (exit other than 0/1) never blocks.
if [ -z "$hits" ] && command -v gitleaks >/dev/null 2>&1 && [ -n "$scan" ]; then
    rep="$(mktemp 2>/dev/null)" || allow
    printf '%s\n' "$scan" | gitleaks stdin --redact --no-banner --log-level error \
        --report-format json --report-path "$rep" >/dev/null 2>&1
    rc=$?
    if [ "$rc" = 1 ]; then
        rules="$(jq -r '[.[].RuleID] | unique | join(", ")' "$rep" 2>/dev/null)"
        hits="  - gitleaks: ${rules:-a provider secret rule}"$'\n'
    fi
    rm -f "$rep"
fi

[ -n "$hits" ] || allow

verb="commit"; [ "$is_push" = 1 ] && verb="push"
deny "secrets-guard blocked this git ${verb} — the change matches secret patterns:
${hits}Remove the secret and rotate it (a secret in git is compromised even if later deleted). Run /secrets-scan for file:line detail, or run the git command in a terminal outside Claude to override."
