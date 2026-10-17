#!/usr/bin/env python3
"""skill-nudge — tell the agent when a skill matches what is happening.

Skills load on description matching, which an agent deep in a task skips (orrery
2026-10-17: o11y-review, replay-proven-fix and secrets-scan all fitted steps that
were done by hand). This hook adds a short context note — never a permission
decision — when:

  UserPromptSubmit  the prompt matches a skill's `prompt` patterns, or
  PreToolUse(Bash)  the command (or its run_in_background flag) matches a skill's
                    `bash` patterns.

Patterns live next to each skill: <skill>/triggers.json
  {"prompt": ["regex", …], "bash": ["regex", …], "background": true}
(`background: true` = match any Bash call with run_in_background that doesn't
already use the skill's own script). Skills are read from ~/.claude/skills/* and
$CLAUDE_PROJECT_DIR/.claude/skills/*. Each skill is nudged at most once per
session per event type (state in $XDG_STATE_HOME/skill-nudge/<session>.json).
Any error → no output, exit 0: a broken nudge must never block work.
"""
import json
import os
import re
import sys


def skill_dirs(project):
    roots = [os.path.expanduser("~/.claude/skills")]
    if project:
        roots.append(os.path.join(project, ".claude", "skills"))
    for root in roots:
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            d = os.path.join(root, name)
            if os.path.isfile(os.path.join(d, "triggers.json")):
                yield name, d


def when_text(d):
    try:
        text = open(os.path.join(d, "SKILL.md")).read()
        m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        fm = {}
        for line in (m.group(1).splitlines() if m else []):
            if ":" in line and not line.startswith(" "):
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip().strip('"')
        return fm.get("when_to_use") or fm.get("description", "")
    except OSError:
        return ""


def main():
    data = json.load(sys.stdin)
    event = data.get("hook_event_name", "")
    session = re.sub(r"[^A-Za-z0-9_-]", "", str(data.get("session_id", "nosession")))[:80]
    project = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or ""
    state_dir = os.path.join(os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state")), "skill-nudge")
    state_path = os.path.join(state_dir, f"{session}.json")
    try:
        seen = set(json.load(open(state_path)))
    except (OSError, ValueError):
        seen = set()

    hits = []
    if event == "UserPromptSubmit":
        prompt = data.get("prompt", "")
        for name, d in skill_dirs(project):
            t = json.load(open(os.path.join(d, "triggers.json")))
            if any(re.search(p, prompt, re.I) for p in t.get("prompt", [])):
                hits.append((name, d))
    elif event == "PreToolUse" and data.get("tool_name") in ("Bash", "bash"):
        ti = data.get("tool_input") or {}
        cmd = ti.get("command", "")
        for name, d in skill_dirs(project):
            t = json.load(open(os.path.join(d, "triggers.json")))
            own = os.path.join(d, "scripts")
            if any(re.search(p, cmd) for p in t.get("bash", [])) or (
                t.get("background") and ti.get("run_in_background") and own not in cmd and f"skills/{name}/" not in cmd
            ):
                hits.append((name, d))
    else:
        return 0

    new = [(n, d) for n, d in hits if f"{event}:{n}" not in seen]
    if not new:
        return 0
    lines = [f"Skill match: `{n}` — {when_text(d)[:300]} Load it with the Skill tool before doing this by hand." for n, d in new]
    os.makedirs(state_dir, exist_ok=True)
    json.dump(sorted(seen | {f"{event}:{n}" for n, _ in new}), open(state_path, "w"))
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": "\n".join(lines)}}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # never block the agent
        sys.exit(0)
