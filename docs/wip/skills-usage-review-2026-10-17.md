# Skills usage review — why agents don't run the skills we have (2026-10-17)

The operator asked: "see why we don't run skills when we have them". This note is the evidence,
the causes, and what changed. Written by the homelab session; the skill-nudge hook is the orrery
session's work.

## The evidence

**Source:** every saved transcript under `~/.claude/projects/` (23 files, all projects). Counted
twice: how often each of our skills was invoked, and how often an agent ran by hand what a skill
covers.

| Skill | Invoked | Done by hand instead |
|---|---|---|
| `ship` / `secrets-scan` | 2 / 4 | **893** `git push` commands in 15 sessions |
| `o11y-review` / `obs-boot` | 5 / 0 | **626** hand-written VictoriaMetrics/Logs/Traces queries in 7 sessions |
| `compose-check` | 0 | **124** `docker compose config`/`up` commands in 6 sessions |
| `gpu-mode` | 3 | **114** direct `gpu-mode-swap.sh` calls in 5 sessions |
| `docs-preflight` | 1 | **88** `mkdocs build` runs in 6 sessions |
| `dgx-status` | 0 | **69** `ssh dgx-llm-1` + `nvidia-smi` / `docker ps` in 5 sessions |
| `close-arc` | 0 | **39** hand edits of `NEXT_STEPS.md` in 3 sessions |

The two counts aren't strictly comparable: a `git push` without `ship` is not always wrong, and a
`gpu-mode-swap.sh --mode-only` is what the skill runs. But the pattern is clear. 8 of 18 skills were
never invoked: `fleet-stats`, `compose-check`, `vllm-deploy`, `dgx-status`, `obs-boot`, `close-arc`,
`scoped-agents` and `ci-watch`. `ci-watch` was brand new.

## Why

1. **Skills load on the operator's words, not on the agent's own next step.** A description's
   "Use when …" is matched when a request arrives. Most of the work above wasn't a request.
   It was an agent deciding mid-task to push, query, or recreate. Nothing looks at the skill list
   again at that point, so `ship` never comes up while `git push` is being typed.
   *This is the main cause.*
2. **Some skills are checklists without a script.** `secrets-scan` had only a `SKILL.md`: "run
   gitleaks, else these patterns". Using it means re-typing the procedure, so agents skip it, or
   run gitleaks directly, which is fine, but then it never counts as the skill.
   *Correction:* the first version of this note implied the 893 pushes went unscanned. They
   didn't. The `secrets-guard.sh` PreToolUse hook, wired since 2026-07-30, scans every
   `git commit`/`git push` an agent runs, but with regexes only, no gitleaks.
3. **Some skills had the wrong shape for the job.** `o11y-review` is a window *review*, while
   post-deploy checking needs a *gate* (expected vs live, PASS/FAIL). So agents wrote a fresh
   verify script after each deploy, 2026-10-16/17 included.
4. **One-command wrappers lose to the command.** `dgx-status`, `gpu-mode`, `compose-check`: an
   agent that knows the command runs it. That's often fine. The loss is the skill's *context*
   (the gotchas, the approval rules), which the command doesn't carry.
5. **Recurring hand-work had no skill at all**, so it was redone, with mistakes each time:
   - probe-and-clean-up (about 6 times, with a wrong endpoint, a wrong frame, a 403);
   - minting credentials (a key whose value was never stored);
   - drift checks;
   - multi-line ssh.

## What changed (2026-10-17)

**New skills, each tested live before commit:**

| Skill | Commit | What it does |
|---|---|---|
| `host-run` | 512268e | runs a script file on the mini, DGX or VPS, killing the inline-ssh quoting traps |
| `telemetry-probe` | 512268e | sends a labelled probe, checks it landed, checks it's absent from the sibling environments, deletes it, confirms |
| `mint-credential` | ad2c40c | mints, stores (mode 600), proves (allowed 200 / denied 403), and records the handbook row |
| `infra-drift` | e5d048f | checks the checkout, containers vs compose, floating images, stray compose files |
| `deploy-verify` | b67d4bf | before/after deploy gate. On its first run it found `PLAYER-1I`, an Android crash the manual checks missed. |

**Extended skills:**
- `triage-fleet-review` gets `proposals.py` (a9c2ebd).
- `close-arc` checks live state before striking an item (a9c2ebd).

**Handbook rules** (512268e):
- VictoriaLogs retention, and the instant-query lookback trap;
- confirm a GlitchTip delete with a later 404;
- run multi-line commands from a script file;
- a relayed approval isn't approval;
- a key isn't minted until its row exists.

**Triggers:**
- **The orrery session's hook:** `skill-nudge.py` (its commits b38e20e, cae4486 and 8708c22,
  not pushed when this note was written) adds a context note when a prompt or a Bash command
  matches a skill's `triggers.json`. That is the fix for cause 1: it brings the skill up at the
  agent's own next step, not only on the operator's words.
- **This session's trigger files:** f77f0ee added `triggers.json` for the five new skills. They
  were replayed over this session's 2,295 Bash commands and 211 prompts. `host-run` fires on 250
  commands, the inline multi-line ssh calls it replaces; the others fire rarely.

## The operator's four decisions ("yes to all 4", 2026-10-17)

- [ ] **Wire `skill-nudge.py`** into `~/.claude/settings.json`: the `UserPromptSubmit` and
      `PreToolUse` Bash hooks, with the entries in `settings.json.example` in the orrery
      session's commits. Waiting for those commits to reach main. Without it,
      `triggers.json` does nothing.
- [x] ~~Give `secrets-scan` a script and maybe a push hook~~ — *a21d0d3*:
      `secrets-scan/scripts/scan.sh` (`--staged`, `--push`, `--range`, `--tree`; gitleaks,
      else patterns; PASS/FAIL), `ship` runs `scan.sh --push`, and the existing
      `secrets-guard.sh` hook gains a gitleaks pass (tests 18/18 with gitleaks, 16/16
      without). No new hook was needed: the push hook already existed (see cause 2).
- [ ] **Catch install drift:** `index.py --check` also reports repo skills not linked into
      `~/.claude/skills`. Waiting for the orrery session's `index.py` change
      (`--write-repo`) to reach main. Its case on 2026-10-17: the six prod-ops skills
      (66dedd3) were on main but not linked on the laptop.
- [x] ~~Shrink `homelab-endpoint` to a pointer~~ — *done 2026-10-17*: it now points at the
      handbook. Its own table was stale: it listed coder-next on `:9000` and a "research"
      mode for `:8003`, which handbook section 13 shows is the prod vLLM.

## Not covered

- **Approximate counts:** they're regex counts over transcripts, and don't separate "should
  have used the skill" from "the command was the right call".
- **Missing history:** sessions whose transcripts were cleaned up aren't counted.
- **Other repos:** skills only in other repos (podcast_scraper's own) weren't counted.
