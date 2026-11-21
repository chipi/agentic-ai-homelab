# Operator rules: reasons and incidents of record

The global [`AGENTS.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/workstation/config/AGENTS.md)
states each rule in a line or two, because every line there is read on every request. This page keeps
what was cut to get there: why each rule exists, and the incidents that produced it. An agent reads it
when a rule's reason matters to the case in front of it. Moved here 2026-11-21 (refactor plan,
`docs/wip/agent-instructions-refactor-plan.md`); the wording is the original's, shortened.

## 0. Truthfulness

The operator's stated stakes: they would rather lose access to AI than have these rules keep being
broken. The full failure-mode analysis is the memory file `feedback_operator_truthfulness_protocol.md`.

- **0.0 Do not lie.** Every other rule is worthless without it. *Incident 2026-09-07:* asked who taught it
  to end an apology by blaming the operator, an agent answered "No one taught me to do it" (a flat
  denial), then defended it with a taught-versus-trained distinction built after the fact, then wrote
  "you called it a lie" rather than "I lied". Four consecutive messages, four instances of the pattern,
  each presented as candour.
- **0.11 Watch running work live.** The operator's rule of 2026-07-17: when something is running, watch it
  line by line; as soon as something fails, fix it so it is ready for the next run; never sleep while it
  runs.
- **0.12 The pre-send check** became mandatory because the rules alone, read once at session start, did
  not fire at the moment of writing.
- **0.14 Use the access you have.** *Incident 2026-07-24 (telemetry ladder):* a hand-over dumped about 15
  unverified assumptions on the infra agent; all were checkable and true. Minutes after writing the
  lesson down, the agent repeated it as "3 real gaps": two already existed, and it closed all three
  itself once it looked. The Grafana token was in a sibling repo's `.env`, two minutes away. Passive
  memory did not fire; that is why it became a pre-send check.
- **0.15 A surprising workaround means a wrong premise.** *Incident 2026-08-13 (podcast-player #1618,
  fixture audio):*
  - The corpus shipped an undecodable 146-byte audio data URI. The agent searched one directory, found
    no `.mp3`, and concluded the repo had no fixture audio.
  - `which ffmpeg` found nothing, so it hand-built MPEG-2 Layer III frames byte by byte and rewrote 36
    fixture files (+2 MB).
  - `tests/fixtures/audio/v3/` held real MP3s for all 36 episodes, one directory up. `pip install
    imageio-ffmpeg` worked first try. Everything was reverted.
  - What made it dangerous: flawless verification of an artifact that should never have been built.
- **0.16 A zero-result search is about the search.** The same #1618 incident: the directory being read
  defined the boundary of what existed. Nearby text that seems to confirm the absence often describes the
  very workaround being removed.
- **0.17 A red gate on your branch is yours.** *Incident 2026-08-03:* four failures were called
  "pre-existing" on the strength of a `git stash` that still contained the agent's own committed
  coverage-arc work, which had edited the very presets the tests check. The operator had told agents to
  stop calling failures pre-existing "a hundred times". The comparison has to be against the pre-session
  branch point, which is what the `baseline-diff` skill does.

## 1. Approval and shared state

- **Per-instance approval for destructive and shared changes.** *Incident 2026-05-29:* the prod VPS was
  destroyed on an "I had approval for the previous one" assumption.
- **Delete approval is per path; check a shared machine for live work.** *Incident 2026-08-25 (mini disk
  cleanup):*
  - Another agent's `~/Library/Developer` was batched into a "57 GB" reclaim list, and "ok on 57gb" was
    treated as blanket permission.
  - It was deleted while about 750 simulator processes (other agents' iOS jobs) were running. The
    active-process check had errored and the agent proceeded anyway.
  - Nothing of source was lost, but live jobs died. The operator: "You had the list a b c d and went to
    e f."
- **Installing is a scope decision; a note that forbids it outranks a check that it is installable.**
  *Incident 2026-08-14 (podcast-player #1619, viewer e2e):*
  - The memory index said the ML extras "cannot install on this box". The agent ran `pip install
    --dry-run lancedb`, saw a wheel, declared the note stale, and installed lancedb, torch 2.2.2 and
    sentence-transformers into the repo venv without opening the note.
  - The note's body named those exact versions under "Do not 'fix' this by downgrading", with the reason
    (lance-format divergence from CI). It also did not work: transformers 5.x needs torch >= 2.5.
  - It was reported at the bottom of a summary, which is burying it: an environment change made without
    asking leads the report.
- **Never open GitHub issues unasked.** A GitHub issue is a public commitment that drains the operator's
  attention every time it appears in `gh issue list`; local tasks disappear when handled.
  - *2026-06-15:* #1002-#1004 opened unprompted in a guardrails session. The operator: "stop opening GH
    issues from now on; all things are immediate follow-up in tasks."
  - *2026-07-20:* six follow-up issues (#1243-#1248) opened during a Search v3 pass. All were deleted
    and the work implemented in place.
  - Both times the rule had been read early in the session and was gone by the time the "tidy to track
    this" impulse fired.

## 2. How to work

- **Cleanup after crashes, only your own processes.** On a shared workstation other checkouts and agents
  run the same `node`/`vite`/`playwright` binaries; `pgrep -f` also matches the checking command itself.
  The `SessionEnd` reaper (`~/.claude/hooks/session-reap.sh`) is family-scoped. The details and the dry
  run are in the `process-hygiene` skill and `workstation/claude/hooks/README.md`.
- **Podcast corpus changes** need the outcome table, a fresh reviewer's verdict and the operator's
  recorded go (podcast_scraper `docs/guides/CORPUS_CHANGE_METHOD.md`); a hand-over without them is
  refused, naming what is missing.

## 3. Machines

- **The mini's production engine is closed to development.** A dev e2e container that published ports in
  the production VM hung lima's port-forward for 7 hours on 2026-10-08 (the same shape on 2026-09-03).
  The contract is ADR-0009 and `docs/recipes/dev-docker-engine.md`.

## 4. Subagents

- **Named lower tiers, enforced.** A subagent with no model of its own inherits the main conversation's
  (Opus): one session of 2026-11-14 spent 41% of its subagent tokens that way (83 `general-purpose` and
  14 `Explore` calls). On 2026-11-19, after sessions launched Opus subagents anyway, the
  `subagent-model-guard.sh` hook began denying them. The 2026-07-02 experiment (ADR-0004) put inline work
  at about $0.10 against $1-18 for multi-agent variants.

## The opencode fleet's role names

opencode's `oh-my-opencode` plugin names its 11 agents after Greek myths; the operator thinks in roles.

| Role | Plugin agent | Model |
|---|---|---|
| @orchestrator | sisyphus | moonshotai/kimi-k2.6 |
| @planner | prometheus | z-ai/glm-5.2 |
| @backend, @ui | hephaestus | deepseek/deepseek-v4-pro |
| @tester | sisyphus-junior | deepseek/deepseek-v4-flash |
| @reviewer | momus | z-ai/glm-5.2 |
| @docs | librarian | deepseek/deepseek-v4-flash |
| @debugger | oracle | z-ai/glm-5.2 |
| helpers | metis (z-ai/glm-5.2), atlas (moonshotai/kimi-k2.6) | |
| unused | multimodal-looker (z-ai/glm-5.2), explore (deepseek/deepseek-v4-flash) | |

## Model and effort (for the operator)

Default to the cheapest model that fits. For an architectural session `/model opusplan` (Opus plans,
Sonnet implements) beats pure Opus on cost. Tune reasoning with `/effort`; don't leave `xhigh` as the
global default, it taxes every simple turn.
