#!/usr/bin/env bash
# command-ask-guard.sh — Claude Code PreToolUse hook. Makes the AGENTS.md "ask first" rules deterministic:
# a command that pushes, opens a GitHub issue, deletes or prunes destructively, or installs into a shared
# environment gets `permissionDecision: "ask"`, so Claude Code asks the operator (in a headless run, where
# nobody can answer, it is refused).
#
# Why a hook and not only permissions.ask: Bash(...) permission rules match the native Bash tool only, and the
# lean-ctx policy routes agents' shell commands through mcp__lean-ctx__ctx_shell, which those rules never see
# (2026-11-21: `claude -p "... git push origin main"` pushed through ctx_shell with Bash(git push:*) in ask).
# This hook reads the command from either: matcher `Bash|bash|mcp__lean-ctx__ctx_shell|mcp__lean-ctx__shell|
# mcp__lean-ctx__ctx_execute`.
#
# Asked about (anywhere the shell runs it, so `cd x && git push` is caught too):
#   git push (incl. `git -C dir push`, --force) · gh issue create · rm -rf / -fr / -r -f (except on the
#   command's own mktemp folder or the session temp areas) ·
#   docker system|volume|image|container|builder|network prune · docker volume rm · compose down -v/--volumes ·
#   terraform apply|destroy · pip/pip3/python -m pip/uv pip install · uv add · uv tool install ·
#   npm install -g / npm i -g · brew install
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
text="$code"
if reruns; then
    text="$(printf '%s' "$cmd" | tr "\"'" '  ')"
fi

# rm -rf is allowed when every target is:
# - the command's own `mktemp` folder (VAR=$(mktemp ...), then "$VAR" or "$VAR/sub");
# - a path in a Claude temp area: /tmp/claude-<anything>/<sub> (this machine's scratchpads under /tmp/claude-<uid>,
#   /private/tmp on macOS, and a work folder an agent made on another host, e.g. /tmp/claude-work over ssh) or
#   CLAUDE_CODE_TMPDIR;
# - a relative path whose first part is a generated-output folder (BUILD_DIRS), which the next build remakes.
# Anything else asks: a "..", a glob, "~", ".", an absolute project path, any other relative path
# (2026-11-23, operator: an eval-harness session's `rm -rf .build/f3-new` before each rebuild asked every time).
BUILD_DIRS=".build build dist out target .cache .pytest_cache .mypy_cache .ruff_cache __pycache__ node_modules htmlcov .coverage coverage .tox .nox .next .nuxt .turbo .parcel-cache .gradle"
rm_target_ok() {
    local t="$1" v
    case "$t" in *..*) return 1 ;; esac
    if [[ "$t" =~ ^\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?(/.*)?$ ]]; then
        v="${BASH_REMATCH[1]}"
        printf '%s' "$cmd" | grep -Eq -- "(^|[;&|(\`[:space:]])${v}=\"?(\\\$\\(|\`)mktemp([[:space:]]|\\)|\`)"
        return
    fi
    case "$t" in
        /tmp/claude-?*/?*|/private/tmp/claude-?*/?*) return 0 ;;
    esac
    case "$t" in
        /*|~*|*[*?[]*) ;;
        *) t="${t#./}"; case " $BUILD_DIRS " in *" ${t%%/*} "*) return 0 ;; esac ;;
    esac
    [ -n "${CLAUDE_CODE_TMPDIR:-}" ] && case "$t" in "${CLAUDE_CODE_TMPDIR%/}/"?*) return 0 ;; esac
    return 1
}
rm_ok() {   # every recursive forced rm in $text targets only allowed paths
    local seg flags t
    while IFS= read -r seg; do
        seg="${seg#"${seg%%rm*}"}"
        set -f; set -- $seg; set +f
        shift
        flags=""
        while [ $# -gt 0 ] && [ "${1#-}" != "$1" ]; do flags="$flags$1"; shift; done
        case "$flags" in *recursive*force*|*force*recursive*) ;; *r*f*|*f*r*) case "$flags" in *--*) continue ;; esac ;; *) continue ;; esac
        [ $# -gt 0 ] || return 1
        for t in "$@"; do rm_target_ok "$t" || return 1; done
    done < <(printf '%s\n' "$text" | grep -oE -- "${S}rm[[:space:]][^;&|)]*")
    return 0
}

check() {   # $1 = ERE, $2 = what, $3 = the AGENTS.md rule
    if printf '%s' "$text" | grep -Eq -- "$1"; then
        [ "$2" = "a recursive forced delete" ] && rm_ok && return 0
        ask "command-ask-guard: ${2}. The operator approves this per instance (~/.config/AGENTS.md, ${3}). Ask in the conversation before running it; in a headless run it is refused."
    fi
}
check "${S}git([[:space:]]+-[^;&|]*)?([[:space:]]+[^;&|[:space:]]+)*[[:space:]]+push([[:space:]]|\$)" "git push" "1: never push without the operator's go"
check "${S}gh[[:space:]]+issue[[:space:]]+create" "opening a GitHub issue" "1: never open a GitHub issue without the operator's explicit ask"
check "${S}rm[[:space:]]+(-[A-Za-z]*r[A-Za-z]*f|-[A-Za-z]*f[A-Za-z]*r|-r[[:space:]]+-f|-f[[:space:]]+-r|--recursive[[:space:]]+--force|--force[[:space:]]+--recursive)" "a recursive forced delete" "1: destructive changes need a per-instance go; deletes cover the exact paths named"
check "${S}docker[[:space:]]+(system|volume|image|container|builder|network)[[:space:]]+prune" "a docker prune" "1: destructive changes need a per-instance go"
check "${S}docker[[:space:]]+volume[[:space:]]+rm" "deleting a docker volume" "1: destructive changes need a per-instance go"
check "compose([[:space:]]+[^;&|]*)?[[:space:]]+down([[:space:]]+[^;&|]*)?[[:space:]]+(-v|--volumes)([[:space:]]|\$)" "compose down with volumes" "1: destructive changes need a per-instance go"
check "${S}terraform[[:space:]]+(apply|destroy)" "terraform apply/destroy" "1: destructive changes need a per-instance go"
check "${S}(pip3?|python3?[[:space:]]+-m[[:space:]]+pip|uv[[:space:]]+pip)[[:space:]]+install([[:space:]]|\$)" "a pip install" "1: no new dependencies and no installs into a shared environment without approval"
check "${S}uv[[:space:]]+(add|tool[[:space:]]+install)([[:space:]]|\$)" "a uv add / tool install" "1: no new dependencies without approval"
check "${S}npm[[:space:]]+(install|i)([[:space:]]+[^;&|]*)?[[:space:]]+(-g|--global)([[:space:]]|\$)" "a global npm install" "1: no installs into a shared environment without approval"
check "${S}brew[[:space:]]+install" "a brew install" "1: no installs into a shared environment without approval"
allow
