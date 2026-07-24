# Round 7 — review ask: §7.3 *implementation* + the first scored eval

Self-contained brief. You work in this tree; everything below is checked in
(or in the working tree where noted). Append your findings to
`REVIEW-2026-07-24-fleet1-architectural.md` as `# Round 7`.

## What shipped since your Round 6

Your Round 6 §6 "minimal version" was built almost verbatim. Refs:

- `5cd484f` — investigation-driven triager. `mvp/triage.py` `investigate()`:
  menu-driven probe loop, hard cap **N=3**, four terminal dispositions
  (dismiss / cleanup / file / escalate-with-question). `mvp/probes.py` — typed
  6-probe menu (event_detail, occurrence_history, service_logs, metric, trace,
  source_state); the model requests probes BY NAME, never writes queries.
  Deterministic gates: intent gate on File (unchanged), `_cleanup_gate`
  (machine-checkable test marker), `_dismiss_gate` (a corroborating probe must
  have run and returned usable).
- `6bb5603` — eval reworked to your Round 6 §5 recommendation: freeze the
  **probe→response table**, not the evidence bundle. `mvp/freeze.py` records
  each probe live and stores `probes:{probe_key→response}`; `mvp/score.py`
  replays `investigate(signal, probe_table=frozen)` k times.
- Working tree (uncommitted) `mvp/freeze.py`: eager full-menu freeze +
  `refreeze_existing()` + label-preservation across re-freeze. See "risk 1".

## The first scored result — deepseek-v4-flash, k=3, 10 operator-labeled fixtures

```
FALSE-DISMISS rate : 6/9 = 0.67   (of file-labeled runs, dismissed)
over-FILE rate     : 1/30 = 0.03
file-recall        : 1/9 = 0.11
escalate rate      : 4/30 = 0.13
inconsistent       : 3/10  [ORRERY-6, PODCAST-4, PODCAST-6]
confusion (GT -> got):
  dismiss->dismiss 9    file->dismiss 6   file->escalate 2   file->file 1
  cleanup->cleanup 5  cleanup->dismiss 4  cleanup->escalate 2  cleanup->file 1
```

Fixture set (mini-local, not committed — data hygiene): 3 dismiss (client-noise
ORRERY-8/A + grafana-orrery-stale), 4 cleanup (test hooks ORRERY-5/6, markers
PLAYER-3/PODCAST-6), 3 file (PLAYER-4/5 `bug`, PODCAST-4 `config-enhancement`).
Labels: operator-given for the 5 judgement calls; triager-citable for the 5
marker/repo-data cases.

## What I want challenged (disagree freely)

**1. The eager-full-menu freeze — sound, or does it hide the coverage gap?**
The model is not deterministic in *which* probe it picks (flash/MoE drifts at
temp 0). Freezing only the observed path meant a replay that requested an
unfrozen probe got a `<not in frozen table>` sentinel → degraded to escalate,
confounding model variance with coverage. My fix freezes the **whole 6-probe
menu eagerly** at default args + the model's actual args. Question: does eagerly
freezing probes the model would *never* run mask a real signal (e.g. a probe
that live-fails is now always "available"), or is pre-populating the lookup the
right call? Is there a case for freezing only the union of probes seen across a
larger freeze-k instead?

**2. THE crux — ground-truth semantics for intent-not-citable signals.**
PLAYER-4/5 are client-side `SyntaxError`s. The *only* source that knows they're
real bugs is the operator. Under §4.1 the triager can't cite that intent, so the
intent-gate-correct autonomous action is **escalate**, not file. I labeled them
`file` (operator's stated "it's a bug"). So: should GT be the signal's **true
nature** (file) or the **correct autonomous disposition given the triager can't
read the operator's mind** (escalate)? This decides what "false-dismiss" even
measures. Your Round 6 §3/§4 line — "investigation earns what/where/how-often,
never intent" — reads to me as arguing GT should be escalate here. Confirm or
break that. (Either way dismiss is wrong; the conclusion "flash under-files"
survives — but the *metric* moves.)

**3. Is 0.67 false-dismiss a MODEL verdict or a PROMPT artifact?** flash is
dismiss-biased (dismiss→dismiss 9/9 perfect; everything else leaks to dismiss).
Is the file-path under-specified in the system prompt (`triage.py` `_SYSTEM`),
or is this genuinely "flash is too weak, jump to v4-pro"? I have NOT run the
v4-pro sweep yet. Before I spend that, is there a prompt fix you'd make first so
the sweep isolates model from prompt?

**4. Did the investigation loop actually close R5-1, or move it?** You flagged
(R5-1) the dismiss gate is structurally vacuous on the error path. `_dismiss_gate`
now requires a corroborating probe that returned `_usable()`. But `_usable()`
treats any `"<…>"` string as non-evidence, and several probes return `<not
applicable>` for error signals. Does the gate now bite, or does it just escalate
everything on the error path (2 of 9 file-runs escalated — is that the gate
working, or the gate failing safe)?

**5. Small-N honesty.** file-recall is 1/9 across only 3 file fixtures. Is the
finding "flash is unfit" defensible at this N, or is the set too thin to
conclude anything but "run more file-labeled cases first"?

## Decisions riding on your answer
- (2) determines whether I relabel PLAYER-4/5 before any further scoring.
- (3) determines whether I prompt-fix before the v4-pro sweep or after.
- All fixtures + machinery are ready; the sweep is one command once the above settle.
