# Writing agent instructions (CLAUDE.md, AGENTS.md)

**Why this exists.** Every agent session here loads the operator's global `AGENTS.md` (through
`~/.claude/CLAUDE.md` for Claude Code, and `~/.config/opencode/AGENTS.md` for opencode), and on
2026-11-21 that file was 859 lines, 73,070 characters: Claude Code warned that it was over its
recommended size, and agents were seen skipping rules that were in it. This guide collects what
Anthropic recommends for these files, so changes to them follow it. The refactor that applies it is
planned in [the refactor plan](../wip/agent-instructions-refactor-plan.md).

## Quick reference

| A piece of guidance that is... | Goes in | Loaded |
|---|---|---|
| A fact or rule every session needs, that the agent can't work out itself | the always-loaded file (`AGENTS.md` / `CLAUDE.md`), one or two lines | every request |
| A multi-step procedure, or something only some tasks need | a **skill** (`SKILL.md` with a "Use when ..." description) | name and description always; the body only when used |
| A rule that must hold every time, with no exceptions | a **hook** or a permission deny rule, plus one line saying it exists | enforced by the harness, not the model |
| Guidance for one part of a repo or one file type | a **path-scoped rule** (`.claude/rules/*.md` with `paths:`) or a scoped `AGENTS.md` | when a matching file is read or edited |
| Background, reasoning, incident history | a doc linked from the file (`docs/...`, memory) | when the agent opens it |
| Something learnt from a correction | auto memory (`MEMORY.md` + one file per fact) | first 200 lines / 25 KB of `MEMORY.md` |

## What Anthropic recommends

Sources: [memory and CLAUDE.md](https://code.claude.com/docs/en/memory),
[best practices](https://code.claude.com/docs/en/best-practices),
[the context window](https://code.claude.com/docs/en/context-window),
[effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents),
read 2026-11-21.

1. **Under 200 lines per file.** "Files over 200 lines consume more context and may reduce
   adherence." Claude Code warns at startup when a file is over the recommended length, and when files
   that are each within it add up past a combined limit.
2. **Only what the agent can't work out itself.** Every line "takes a little of Claude's attention on
   every task, whether it's relevant or not". Keep: the commands that check work, places where the code
   misleads, decisions that are not in the repo, "anything you've had to correct twice already". Cut:
   what the code, the docs or the harness already say.
3. **Procedures become skills.** "If an entry is a multi-step procedure or only matters for one part of
   the codebase, move it to a skill." A skill costs its name and description in every session, and its
   body only when it is used. Claude Code already lists every installed skill with its description, so a
   skills table in an always-loaded file is a second copy.
4. **Rules without exceptions become hooks.** "CLAUDE.md is for guidelines, and Claude is allowed to
   decide a guideline doesn't apply." And: "If Claude keeps ignoring a line that is in CLAUDE.md, adding
   IMPORTANT probably won't fix it. Either the file has grown long enough that the line gets lost, or
   the line is a rule that can't have exceptions, in which case it belongs in a hook." Emphasis
   (capitals, NON-NEGOTIABLE, BANNED) is not a substitute. Keep the enforced set small: "If you ever
   find yourself at forty of them, most are probably preferences."
5. **No contradictions, no stale lines.** "If two instructions contradict each other, Claude may pick
   one arbitrarily." `/doctor prompt-audit` checks the instruction files for contradictions, references
   to files that no longer exist, and instructions written for older models.
6. **Structure: headers and bullets,** not dense paragraphs. "Organized sections are easier for Claude
   to follow."
7. **Imports organize; they don't shrink.** "Splitting into @path imports helps organization but
   doesn't reduce context, since imported files load with the CLAUDE.md importing them." Path-scoped
   rules and skills are what keep text out of context until it is needed.
8. **The minimal set, loaded just in time.** "The minimal set of information that fully outlines your
   expected behavior." Recall falls as context grows ("context rot"), so keep references (paths, links)
   in the always-loaded file and let the agent open the detail when it needs it.
9. **Rules that must survive compaction live in the root file.** After compaction the project-root
   CLAUDE.md, unscoped rules and auto memory are re-injected from disk; path-scoped rules and nested
   files are summarized away until a matching file is touched again.

## Managing a session's context

- `/clear` when switching to unrelated work: "old conversation crowds out the files you need next and
  costs tokens on every message".
- `/compact <focus>` before a long new task, so the summary keeps what you choose.
- Send large reads and searches to a subagent; only its summary comes back.
- The auto-compact point: `CLAUDE_CODE_AUTO_COMPACT_WINDOW` (a token count, `100000` or more) in the
  `env` of `~/.claude/settings.json` sets it for every session; `/autocompact 300k` for one session.
  Here, sessions ran to about 967,000 tokens before compacting (2026-11-07..21), so a typical request
  re-sent 520,000-580,000 tokens.
- `/context` shows the live breakdown by category, including which instruction files loaded.

## How it is wired here

| File | Source in this repo | Loaded by |
|---|---|---|
| `~/.config/AGENTS.md` | `workstation/config/AGENTS.md` | Claude Code (imported by `~/.claude/CLAUDE.md`), opencode |
| `~/.claude/CLAUDE.md` | `workstation/claude/CLAUDE.md` | Claude Code, every session |
| `~/.claude/skills/*` | `workstation/claude/skills/`, chipi/infra `skills/` | Claude Code and opencode list them |
| `~/.claude/hooks/*` | `workstation/claude/hooks/`, wired in `~/.claude/settings.json` | Claude Code |
| a repo's `AGENTS.md` / `CLAUDE.md` | each repo | sessions started in it |

`workstation/install.sh` links them on each machine (X3, mini, laptop), so a change here reaches every
session on every machine at the next start.

## Checklist for a change to an instruction file

1. Does the line pass the test in 2: would the agent get it wrong without it?
2. Is it a procedure (skill), a rule without exceptions (hook), or part-time (path rule)? Then it goes
   there, and the file keeps at most a one-line pointer.
3. Does it duplicate or contradict another line, here or in a repo's file?
4. Size after the change: `wc -l -m` on the file; under 200 lines is the target.
5. Run `/doctor prompt-audit` in a session.
6. A behaviour change (a rule that used to be followed) is checked on real tasks before and after; the
   refactor plan has the method.

## Measuring

- **Fixed context per session:** the first request's input tokens in a transcript
  (`~/.claude/projects/<project>/<session>.jsonl`, `message.usage`: `input_tokens` +
  `cache_creation_input_tokens` + `cache_read_input_tokens`). On 2026-11-21: median 88,600 tokens over
  21 sessions; `AGENTS.md` + `CLAUDE.md` were about 22,000 of it.
- **Growth:** the median and maximum context per request in the same files, and the count of
  compactions.
- **Instruction files:** `wc -l -m` and `/context`.
