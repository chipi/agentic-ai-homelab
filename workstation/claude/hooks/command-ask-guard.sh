#!/usr/bin/env bash
# command-ask-guard.sh — Claude Code PreToolUse hook. A short backstop for the few actions that leave the
# machine or can't be undone: a push that forces or deletes (plain pushes, main included, are allowed since
# 2026-11-26), opening a GitHub issue,
# a docker prune or volume removal, compose down -v, terraform apply/destroy. Those get
# `permissionDecision: "ask"`, so the operator is asked (a headless run, where nobody can answer, refuses).
#
# Everything else is left to auto mode and the agent's judgment of ~/.config/AGENTS.md: deletes and installs
# are scoped there ("on shared infra", "into a shared environment"), and a text pattern can't see that scope.
# The 2026-11-21 refactor put rm -rf and installs here and in 20 permissions.ask rules; every delete of an
# agent's own folder and every .venv install then asked, auto mode stopped working, and each prompt led to
# another exception pattern. On 2026-11-23 the operator had them removed (README, "2026-11-23: back to a
# short list").
#
# Why a hook at all: Bash(...) permission rules match the native Bash tool only, and the lean-ctx policy routes
# agents' shell commands through mcp__lean-ctx__ctx_shell, which those rules never see (2026-11-21:
# `claude -p "... git push origin main"` pushed through ctx_shell). This hook reads the command from either:
# matcher `Bash|bash|mcp__lean-ctx__ctx_shell|mcp__lean-ctx__shell|mcp__lean-ctx__ctx_execute`.
#
# Asked about (anywhere the shell runs it, so `cd x && git push origin main` is caught too):
#   a git push that forces or deletes (see push_ok) ·
#   gh issue create · docker system|volume|image|container|builder|network prune · docker volume rm ·
#   compose down -v/--volumes · terraform apply|destroy
# Not asked about: the same words in text that is not run (a heredoc written to a file, a commit message, an
# echo, a comment). Inside bash -c / sh -c / ssh / eval / su / a heredoc into a shell, the text is checked.
# Not covered: a command assembled at runtime (a variable expanded, a script file that pushes, even one this
# same command just wrote with a heredoc), a heredoc into python3 or node whose code shells out, and
# `trap '...'` handlers (their text is quoted, so skipped).
#
# PreToolUse contract: reads {tool_name, tool_input} as JSON on stdin; "ask" is printed as JSON, exit 0. Every
# other path allows (no output, exit 0), including COMMAND_ASK_GUARD=off (the operator's escape hatch; agents
# never set it) and no jq / an unreadable payload: fail-open, a broken guard must never block every command.

set -uo pipefail

allow() { exit 0; }
ask() {
    jq -n --arg r "$1" \
      '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"ask",permissionDecisionReason:$r}}' \
      2>/dev/null || allow
    exit 0
}

[ "${COMMAND_ASK_GUARD:-on}" = "off" ] && allow
command -v jq >/dev/null 2>&1 || allow
payload="$(cat 2>/dev/null)" || allow
tool="$(jq -r '.tool_name // empty' <<<"$payload" 2>/dev/null)" || allow
case "$tool" in Bash|bash|mcp__lean-ctx__ctx_shell|mcp__lean-ctx__shell|mcp__lean-ctx__ctx_execute) ;; *) allow ;; esac
cmd="$(jq -r '.tool_input.command // .tool_input.code // empty' <<<"$payload" 2>/dev/null)" || allow
[ -n "$cmd" ] || allow

# lean-ctx's rewrite of a Bash command, `[{ ].../lean-ctx -c '<command>'[ newline } && pwd -P >| <file>]`, runs
# <command>: check that (its '\'' escapes read the same to the quote scanner below). One that does not have
# this shape is checked as written (reruns).
if [[ "$cmd" =~ ^[[:space:]]*(\{[[:space:]]*)?([^[:space:]]*/)?lean-ctx[[:space:]]+-c[[:space:]]+\' ]]; then
    rest="${cmd:${#BASH_REMATCH[0]}}"
    tail_re="'([[:space:]]*\\}[[:space:]]*(&&[[:space:]]*pwd -P >\\|[[:space:]]*[^;&|[:space:]]+)?)?[[:space:]]*\$"
    if [[ "$rest" =~ $tail_re ]]; then
        cmd="${rest:0:$(( ${#rest} - ${#BASH_REMATCH[0]} ))}"
    fi
fi

S='(^|[;&|(`[:space:]])'   # start of a command word: line start or a separator / whitespace before it

# What the shell will run, not text that only mentions a command (2026-11-22: a heredoc writing a message
# that quoted "git push", a commit message, an echo or a comment all asked, so the operator saw constant
# prompts). Dropped: heredoc bodies, comments, and quoted strings containing whitespace (every guarded
# pattern spans a space, so a quoted word without one can never match and is kept, e.g. rm -rf "$d").
code="$(printf '%s\n' "$cmd" | awk '
function flushq() { if (buf ~ /[ \t\n]/) out = out " "; else out = out " " buf " "; buf = "" }
{
    line = $0
    if (hd != "") { t = line; if (hdtab) sub(/^\t+/, "", t); if (t == hd) hd = ""; out = out "\n"; next }
    n = length(line); i = 1; pend = ""
    while (i <= n) {
        c = substr(line, i, 1)
        if (q == "s") { if (c == "\047") { q = ""; flushq() } else buf = buf c; i++; continue }
        if (q == "d") {
            if (c == "\\" && i < n) { buf = buf c substr(line, i + 1, 1); i += 2; continue }
            if (c == "\"") { q = ""; flushq() } else buf = buf c
            i++; continue
        }
        if (c == "\\" && i < n) { out = out c substr(line, i + 1, 1); i += 2; continue }
        if (c == "\047") { q = "s"; i++; continue }
        if (c == "\"") { q = "d"; i++; continue }
        if (c == "#" && (i == 1 || substr(line, i - 1, 1) ~ /[ \t;&|(]/)) break
        if (substr(line, i, 2) == "<<" && substr(line, i, 3) != "<<<") {
            rest = substr(line, i + 2); tab = 0
            if (substr(rest, 1, 1) == "-") { tab = 1; rest = substr(rest, 2) }
            sub(/^[ \t]*/, "", rest)
            if (match(rest, /^[\047"]?[A-Za-z0-9_]+/)) { pend = substr(rest, RSTART, RLENGTH); gsub(/[\047"]/, "", pend); ptab = tab }
            out = out "<<"; i += 2; continue
        }
        out = out c; i++
    }
    if (q != "") buf = buf "\n"; else out = out "\n"
    if (pend != "") { hd = pend; hdtab = ptab }
}
END { if (q != "") flushq(); printf "%s", out }')" || code="$cmd"

# Text that a shell runs again (bash -c "...", ssh host "...", eval, a heredoc into bash or ssh, | sh, a
# lean-ctx -c the unwrapping above did not match): there the quoted text and the heredoc bodies are
# commands, so the whole command is checked as written, with its quote characters as spaces.
# `bash file.sh` runs a file, which is not checked, even one this same command wrote with a heredoc
# (2026-11-23, operator: a test script pushing to a throwaway local repo asked).
SH='(bash|sh|zsh|dash|ksh)'
reruns() {
    printf '%s' "$code" | grep -Eq -- "${S}(ssh|eval|su)([[:space:]]|\$)" && return 0
    printf '%s' "$code" | grep -Eq -- "${S}([^[:space:]]*/)?lean-ctx[[:space:]]+-c([[:space:]]|\$)" && return 0
    printf '%s' "$code" | grep -Eq -- "${S}${SH}[[:space:]]+-[A-Za-z]*[cs]" && return 0
    printf '%s' "$code" | grep -Eq -- "${S}${SH}[[:space:]]*(<|\$|[;&|)])" && return 0
    return 1
}
text="$code"; raw=0
if reruns; then
    text="$(printf '%s' "$cmd" | tr "\"'" '  ')"; raw=1
fi

# Pushes need no go, main included (operator, 2026-11-26: "lets allow agents to push to main"; feature
# branches since 2026-11-23). What still asks is a push that can destroy history or branches: --force/-f
# (alone or in a bundle such as -uf), --force-if-includes, a +refspec, a :branch delete, --delete/-d,
# --mirror, --prune, and --force-with-lease to a default or release branch or with no branch named (with a
# feature branch it is the normal push after a rebase). Text another shell re-runs (bash -c, lean-ctx -c,
# ssh, eval, a pipe into sh) is read the same way, with its quotes as spaces.
PUSH_DEFAULT_BRANCHES="main master trunk develop development production prod stable release gh-pages HEAD"
push_ok() {
    local seg a dest n lease protected
    while IFS= read -r seg; do
        seg="${seg#* push}"
        set -f; set -- $seg; set +f
        n=0; lease=0; protected=0
        for a in "$@"; do
            case "$a" in
                *'>'*|*'<'*) continue ;;
                --force-with-lease|--force-with-lease=*) lease=1; continue ;;
                --force|--force-if-includes|--delete|--mirror|--prune) return 1 ;;
                --*) continue ;;
                -*) case "${a#-}" in *[fd]*) return 1 ;; esac; continue ;;
                +*|:*) return 1 ;;
            esac
            n=$((n + 1))
            [ $n -eq 1 ] && continue
            dest="${a#*:}"; dest="${dest#refs/heads/}"
            case " $PUSH_DEFAULT_BRANCHES " in *" $dest "*) protected=1 ;; esac
            case "$dest" in release/*|releases/*) protected=1 ;; esac
        done
        if [ "$lease" = 1 ] && { [ "$protected" = 1 ] || [ $n -lt 2 ]; }; then return 1; fi
    done < <(printf '%s\n' "$text" | grep -oE -- "${S}git([[:space:]]+-[^;&|]*)?([[:space:]]+[^;&|[:space:]]+)*[[:space:]]+push([[:space:]][^;&|)]*)?")
    return 0
}

check() {   # $1 = ERE, $2 = what, $3 = the AGENTS.md rule
    if printf '%s' "$text" | grep -Eq -- "$1"; then
        [ "$2" = "a force push or branch delete" ] && push_ok && return 0
        ask "command-ask-guard: ${2}. The operator approves this per instance (~/.config/AGENTS.md, ${3}). Ask in the conversation before running it; in a headless run it is refused."
    fi
}
check "${S}git([[:space:]]+-[^;&|]*)?([[:space:]]+[^;&|[:space:]]+)*[[:space:]]+push([[:space:]]|\$)" "a force push or branch delete" "1: force-pushes and branch deletes need a per-instance go"
check "${S}gh[[:space:]]+issue[[:space:]]+create" "opening a GitHub issue" "1: never open a GitHub issue without the operator's explicit ask"
check "${S}docker[[:space:]]+(system|volume|image|container|builder|network)[[:space:]]+prune" "a docker prune" "1: destructive changes need a per-instance go"
check "${S}docker[[:space:]]+volume[[:space:]]+rm" "deleting a docker volume" "1: destructive changes need a per-instance go"
check "compose([[:space:]]+[^;&|]*)?[[:space:]]+down([[:space:]]+[^;&|]*)?[[:space:]]+(-v|--volumes)([[:space:]]|\$)" "compose down with volumes" "1: destructive changes need a per-instance go"
check "${S}terraform[[:space:]]+(apply|destroy)" "terraform apply/destroy" "1: destructive changes need a per-instance go"
allow
