# Refactor plan: the global AGENTS.md and CLAUDE.md

Applies [Writing agent instructions](../recipes/agent-instructions-guide.md) to the operator's two
always-loaded files. Started 2026-11-21 on the operator's ask. **Nothing is changed yet**; each step
below waits for the operator's go.

## Where we start (measured 2026-11-21)

| File | Lines | Characters | ~Tokens | Loaded by |
|---|---|---|---|---|
| `workstation/config/AGENTS.md` (`~/.config/AGENTS.md`) | 859 | 73,070 | ~18,300 | Claude Code (imported), opencode |
| `workstation/claude/CLAUDE.md` (`~/.claude/CLAUDE.md`) | 239 | 14,713 | ~3,700 | Claude Code |
| this repo's `AGENTS.md` | 62 | 3,378 | ~850 | sessions in this repo |

`AGENTS.md` by section (characters): Skills 29,906 (the skill table alone 25,236, 63 rows) ·
NON-NEGOTIABLE 20,364 · Operating discipline 5,543 · Safety, secrets, dependencies 3,518 ·
Big-bets 3,069 · Subagent delegation 2,752 · Fleet nickname map 2,116 · STRONG defaults 1,738 ·
Documentation hygiene 903 · Communication 816 · Model & effort 496 · What overrides 490 · lean-ctx 455.

`CLAUDE.md`: a second copy of the truthfulness protocol (T0-T16, about 11,800 characters, the same
rules as `AGENTS.md` 0.0-0.16), then a lean-ctx block (1,447).

Sessions on the X3, 2026-11-07..21: the first request of a session carried a median 88,600 tokens;
these files were about 22,000 of it.

## Target

- `AGENTS.md` **under 200 lines and about 15,000 characters**, every rule kept, each as one to three
  lines: the rule and its "tell" where it has one.
- `CLAUDE.md` **under 15 lines**: the import of `AGENTS.md` and the Claude-only notes.
- Nothing the harness or a hook already does is said twice.
- Incident stories, rationale and long procedures move to docs and skills, linked by one line.

## Item by item

Destinations: **keep** (kept in `AGENTS.md`, shortened) · **skill** · **hook/permission** (enforced,
the file keeps one line) · **doc** (moved to `docs/reference/operator-rules.md`, new, linked) ·
**delete** (duplicated elsewhere).

### AGENTS.md

| # | Item (current chars) | Destination | What stays in AGENTS.md |
|---|---|---|---|
| A1 | Title and intro | keep | 3 lines: what the file is, that repo files layer on top |
| A2 | Fleet nickname map (2,116) | doc: opencode only | none in the global file; it moves to `workstation/config/opencode/` (the plugin roster is opencode's) |
| A3 | 0.0 Do not lie, 0.0.a-e and the 2026-09-07 incident (2,801) | keep + doc | the rule and the five forms, one line each, plus the tell; the incident goes to the doc |
| A4 | 0.1-0.11 (direct answers, evidence, ambiguity, hedging, reason-first, coverage, suppression, banned phrases, no pivot, speed, watch live) (~4,900) | keep | one line each, 11 lines |
| A5 | 0.12 pre-send checklist (1,883) | keep, shorter | a 12-item list, one short line each, pointing at the rules above; candidate for a Stop-hook check later (B6) |
| A6 | 0.13 no invented scope (1,333) | keep | 2 lines |
| A7 | 0.14 verify with access you have + the telemetry incident (2,005) | keep + doc | 2 lines; incident to the doc |
| A8 | 0.15 weird workaround = bad premise + the #1618 incident (2,735) | keep + doc | 2 lines; incident to the doc |
| A9 | 0.16 zero-result search (1,331) | keep | 2 lines |
| A10 | 1 Never push without approval | keep + permission (B1) | 1 line |
| A11 | 2 Rebase before every push | keep, point at the `ship` skill | 1 line |
| A12 | 3 Red CI is a requirement | keep | 1 line |
| A13 | 4 Per-instance approval for destructive/shared changes, per-path deletes, shared machines, failed guards + the 2026-05-29 and 2026-08-25 incidents (1,880) | keep + permission (B3) + doc | 4 lines; incidents to the doc |
| A14 | 5 Never invent root causes | keep, point at `repro-first` | 1 line |
| A15 | 6 Validate cost first + 32 cost awareness | keep, merged | 1 line |
| A16 | 7 Do exactly what was asked | keep | 1 line |
| A17 | 8, 9, 18 right validation, no redundant runs, re-run only the failed subtarget | keep, merged | 1 line |
| A18 | 10 Don't defer surfaced issues + T15 "pre-existing is banned" (1,107) | keep, merged | 2 lines; the 2026-08-03 incident to the doc |
| A19 | 11 Reproduce locally before pushing | keep, merged with A14 | (in A14) |
| A20 | 12 No new dependencies + 30 installing is a scope decision + the #1619 incident (2,396) | keep, merged + permission (B4) + doc | 2 lines; incident to the doc |
| A21 | 13 PRs ready, not draft | keep | 1 line |
| A22 | 14 Read the design intent first | keep | 1 line |
| A23 | 15-17 full output, foreground make, assessable exit codes | keep, merged | 2 lines |
| A24 | 19 Cleanup after crashes + reaper and stale-loop details (2,206) | keep + skill (C2) | 2 lines (only your own processes; never pkill/prune); the procedure goes to the skill |
| A25 | 20 Investigate before asking | keep | 1 line |
| A26 | Mini Docker: dev engine only (ADR-0009) | keep | 2 lines + link to `dev-docker-engine.md`; hook candidate (B5) |
| A27 | Operating the operator's services: read the handbook | keep | 1 line + link |
| A28 | Observability dev vs prod | keep | 3 lines (o11y-dev before a PR; never file issues from dev errors; never resolve from dev) |
| A29 | 21-24 communication (terse, steady when the operator is frustrated, honest limits, no emojis) | keep | 4 lines |
| A30 | 25-28 documentation hygiene | keep, merged | 3 lines; `docs-preflight` named |
| A31 | 29 Never commit secrets | keep (the `secrets-guard` hook and `secrets-scan` skill exist) | 1 line |
| A32 | 31 Rollback first + podcast corpus-change rule | keep | 2 lines; the corpus rule points at `corpus-migration` |
| A33 | 33 ADRs/RFCs for big decisions | keep, point at `new-doc` | 1 line |
| A34 | 34 Real bug: repro before fix | keep (in A14) | (in A14) |
| A35 | 35 Never open GitHub issues + two incidents (2,555) | keep + permission (B2) + doc | 2 lines; incidents to the doc |
| A36 | Subagent delegation, inline by default, tiers, the guard, the escape hatch (2,752) | keep (the `subagent-model-guard` hook enforces it) | 4 lines |
| A37 | Skills section: how loading works, how to write one (~4,700) | skill (C1) | 2 lines: check for a matching skill first; writing one → the skill |
| A38 | Skills index table (25,236) | delete from the file | none: Claude Code and opencode already list every skill with its description. `skills/index.py --write` keeps the table in `workstation/claude/skills/INDEX.md` instead (C3) |
| A39 | Model & effort | doc | none (operator tips, not agent rules) |
| A40 | What overrides this file | keep | 2 lines |
| A41 | lean-ctx tool routing | keep, one place only | 1 line (the hooks enforce it) |

### CLAUDE.md (global)

| # | Item | Destination | What stays |
|---|---|---|---|
| B-a | Header explaining the layering | keep | 2 lines |
| B-b | Truthfulness protocol T0-T16 (~11,800) | delete | none: it is the same text as AGENTS.md 0.0-0.16, and CLAUDE.md imports AGENTS.md, so Claude Code sees it twice. (It was copied "so it is visible regardless of loader path"; the import makes that true already.) |
| B-c | `@~/.config/AGENTS.md` | keep | 1 line |
| B-d | lean-ctx Replace Mode block (1,447) | keep, shorter | 3 lines: use the ctx_* tools; native Read only before Edit; the hook denies Grep/Glob |

### This repo's AGENTS.md

| # | Item | Destination |
|---|---|---|
| R-a | lean-ctx section (the third copy) | delete; the global file has it |

## New skills and hooks

**Skills (C)**

- **C1 `skill-authoring`**: how loading works, the frontmatter and "Use when ..." sentence, scripts,
  regenerating the index, testing against the live system (from A37).
- **C2 `process-hygiene`**: after a crash, find and stop only your own processes; the reaper's dry run;
  `cleanup-worktree.sh --stale-loops`; docker scoped to your compose project (from A24, with the
  hooks README).
- **C3** not a skill: `skills/index.py --write` writes `workstation/claude/skills/INDEX.md` instead of
  `AGENTS.md`, and CI's staleness check follows it.

**Hooks and permission rules (B)**, each its own go, since a prompt or a block has a cost:

- **B1** `permissions.ask` for `Bash(git push:*)`: the harness asks the operator at every push (rule 1,
  made deterministic). Trade-off: a prompt on every push, also in sessions where the operator granted an
  arc.
- **B2** `permissions.ask` for `Bash(gh issue create:*)`: rule 35 has been broken in at least two
  sessions while it was in the file.
- **B3** `permissions.ask` for the destructive set: `rm -rf`, `docker compose down -v`, `docker
  system/volume/image prune`, `terraform apply`, `git push --force` (rule 4).
- **B4** `permissions.ask` for installs: `pip install`, `uv pip install`, `npm i -g`, `brew install`
  (rule 12/30).
- **B5** on the mini only: a PreToolUse check that refuses `docker` commands that would reach
  `/var/run/docker.sock` from an agent session that is not the operator's (rule A26). Needs a design
  look first.
- **B6** later and optional: a Stop hook that scans the final message for the banned words (should,
  probably, likely, seems, I think) and a missing first-word answer. It is deterministic but may be
  noisy; try it in one session first.

Existing enforcement the file only points at: `subagent-model-guard.sh` (A36), `secrets-guard.sh` (A31),
the lean-ctx deny hooks (A41).

## The new home for stories and reasons

`docs/reference/operator-rules.md` (new): for each rule kept short in `AGENTS.md`, the reasoning and the
incidents of record (2026-05-29 prod VPS, 2026-06-15 and 07-20 issues, 07-24 telemetry, 08-03
pre-existing, 08-13 #1618, 08-14 #1619, 08-25 mini cleanup, 09-07 denial). `AGENTS.md` links to it once
at the top. The truthfulness memory file (`feedback_operator_truthfulness_protocol.md`) stays as it is.

## Step 1 result: `/doctor prompt-audit` (2026-11-21)

Run headless (`claude -p "/doctor prompt-audit"`, 17 turns, Opus 5.5). The full report is on the X3
at `~/.local/share/agent-instructions/prompt-audit-2026-11-21.md` (mode 600). It is not in this public
repo because it quotes the private chipi/infra skills. Its findings for the files in this repo:

- **The two always-loaded files contradict each other.**
  - `CLAUDE.md` says it "never duplicates" `AGENTS.md`, then carries the truthfulness protocol a
    second time, and that copy has drifted:
    - two rules labelled `T15`;
    - the pre-send checklist out of order;
    - one rule that exists only in the copy ("pre-existing" is banned).
  - That last rule conflicts with `AGENTS.md` 10, "if unsure whether it's in scope, ask".
  - The opencode sentence in `CLAUDE.md` is stale: opencode does not load this file yet.
- **Conflicts inside `AGENTS.md`.**
  - Rule 23's "I'm 80% confident" example against rule 0.3, which bans confidence numbers.
  - The lean-ctx edit route: native Read+Edit in `AGENTS.md`, `ctx_read anchored` + `ctx_patch` in
    `CLAUDE.md`.
- **Incident narratives** (rules 35, 30, 0.15 and others) and **pressure language** (NON-NEGOTIABLE,
  NEVER, profanity in 0.11). On Opus 5.5 an alarmed register over-applies; the rules themselves stay.
- **The skills table** duplicates the harness's own list. It names skills not installed here (cmux,
  higgsfield, lavish) and omits installed ones.
- **"Model & effort"** is guidance for the operator, not the agent.
- **Homelab skills with stale facts:**
  - `gpu-mode` and `dgx-status` name mode `idle`, which the script now rejects: the mode is `free`,
    plus `research-vllm`, `research-ollama`, `judging-*` and `robotics`;
  - `vllm-deploy` uses the ambiguous `research`;
  - `obs-boot` does not explain the Postgres-exporter and backup FAILs its script raises;
  - `o11y-dev` pins SHAs;
  - `fleet-stats` narrates a fixed bug.
- **Dated "Verified / Tested" blocks** in about 12 homelab skills record past runs and prescribe
  nothing.
- **Elsewhere:**
  - stale facts in five chipi/infra skills, for the infra session;
  - three vendor or plugin skills, left as they are because updates overwrite them.

The audit's own limits: no behaviour probes (whether a removed incident story changes behaviour on
Opus 5.5 is untested, which step 2's eval is for), and most skill findings came from its Sonnet
subagents' reads.

These findings join the item table: A3-A8, A13, A20 and A35 drop their stories; A29 drops the "80%"
example; A41 takes the `ctx_patch` route; B-b's one Claude-only rule moves into `AGENTS.md` and is
reconciled with rule 10; the skill fixes are a separate pass (step 3b).

## Steps

1. **Baseline** (done 2026-11-21, above). Run `/doctor prompt-audit` in a session (the operator, or `claude -p` if the command
   runs headless) and record what it finds. Record sizes and the first-request token count.
2. **A rules-adherence eval** in the private eval-harness repo pattern (like `chipi/harness-bakeoff`):
   about 15 short scenarios that each test one rule (asked to push; told "file an issue for this";
   a yes/no question; a failing check to report; a command that wants `pip install`; a "clean up"
   with an extra path; a zero-result search). Claude Code headless on Sonnet runs each with the
   current files and scores it by checks on the reply and the tool calls. Run 3 times.
3. **Draft** the new `AGENTS.md`, `CLAUDE.md`, `docs/reference/operator-rules.md`, skills C1 and C2,
   and the `index.py` change, on a branch. The operator reviews the diff.
   - **3b.** Fix the stale homelab skills the audit found (`gpu-mode`, `dgx-status`, `vllm-deploy`,
     `obs-boot`, `o11y-dev`, `fleet-stats`) and drop their dated test logs. This is independent of the
     rest, so it can go first.
4. **Re-run the eval** with the draft (the same 15 scenarios, 3 times). Adoption needs: no scenario
   worse than baseline; sizes on target.
5. **Hooks and permissions** B1-B4, one by one with the operator's go, each tested (the rule fires on
   the command, does not fire on a near-miss).
6. **Roll out** on the X3 first (install.sh links it), use it for a day, then the mini and the laptop
   with a pull.
7. **The auto-compact window**: `CLAUDE_CODE_AUTO_COMPACT_WINDOW` in `~/.claude/settings.json`
   (`settings.json.example` in this repo too), a value chosen from the token data, for example 300000;
   watched for a few days with the same token analytics.

## Not covered yet

- What else makes up the 88,600-token start (system prompt, tool schemas, MCP servers, skill
  descriptions); a minimal session against the normal one will show it.
- Whether shorter files change rule-following: only step 4 can show it, and 15 scenarios are a small
  sample.
- opencode: it reads the same `AGENTS.md`, but not `CLAUDE.md`, the hooks or the skills index the same
  way; the eval runs on Claude Code only.
- The repo-scoped `AGENTS.md` files in other projects (podcast, orrery, flotilla) are not part of this
  pass.
