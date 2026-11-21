---
name: skill-authoring
description: Write or change a skill for Claude Code and opencode in this setup — where skills live (workstation/claude/skills, chipi/infra skills/), the frontmatter and its "Use when …" sentence, a scripts/ folder for the repeatable part, testing against the live system, install.sh linking, and regenerating the skills index. Use when asked to write, add, change or fix a skill, or when a procedure keeps recurring and should become one.
---

# skill-authoring

A skill is a packaged, tested procedure for a task that keeps coming back: a review, a deploy ritual, a
proof method. Most ship a script, so the same question gets answered the same way by every agent, every
week.

## How skills load

- Claude Code and opencode read every skill's `name` and `description` at session start, and load the
  full `SKILL.md` when a task matches.
- The description's "Use when …" sentence is the trigger. Write it in the words the operator uses ("how
  is the fleet doing", "what happened overnight").
- Only the description is always in context; the body loads on use. So procedures belong here, not in
  `AGENTS.md`.
- After a compaction, invoked skill bodies are re-injected but capped (5,000 tokens per skill), and
  truncation keeps the start: put the most important instructions near the top.

## Where they live

- `agentic-ai-homelab/workstation/claude/skills/<name>/`.
- Product skills (prod deploys, corpus migrations, prod batches) live in the private chipi/infra repo's
  `skills/<name>/`.
- `workstation/install.sh` links both into `~/.claude/skills/`; an infra skill wins over a same-named one
  here. opencode scans `~/.claude/skills/` too, so one location serves both harnesses.

## Steps

1. **Frontmatter:** `name`, and a `description` that says what it does and has a "Use when …" sentence
   naming the situations.
2. **The repeatable part goes in `scripts/`.** Read-only by default; mutating steps are gated on explicit
   approval.
3. **Test it against the live system** before calling it done. Record what you proved in the commit
   message, not as a dated "Verified" block in the skill: a log of past runs loads on every use and
   prescribes nothing.
4. **Make it generic when the task is,** with the project as a parameter, so Close Listening, Orrery and
   homelab can share it.
5. **Regenerate the index:** `python3 workstation/claude/skills/index.py --write` writes
   `workstation/claude/skills/INDEX.md`. `--check` exits 1 when it is stale; CI runs it.
6. **Link it:** re-run `workstation/install.sh` (or `--check-install` to see what is missing).

## Keep it lean

- Only what the agent can't work out itself.
- A script's output is evidence, not a verdict: the skill says how to judge it.
- No pressure language (MUST, NEVER in capitals). A rule that must hold every time is a hook.
