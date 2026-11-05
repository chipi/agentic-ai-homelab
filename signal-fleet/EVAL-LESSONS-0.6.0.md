# What the triage-fleet evaluation teaches the fleet itself

**Status:** living, 2026-10-30; section 7 (2026-11-04) answers section 6 and corrects F1, F3 and F7. Written to be handed to an agent
that will improve the homelab triage fleet (signal-fleet, Fleet 2) on its own, outside eval-harness.

**Provenance:** moved here from eval-harness on 2026-11-04 (the owner's instruction), unchanged; the original is
`research/internal/TRIAGE_FLEET_LESSONS_0.6.0.md` at chipi/eval-harness commit `d42e0437c`. Paths and commits below are
the ones it was written against (signal-fleet `c739792`, the dataset builder `21bc902`).

**Read first:** the fleet's own guide, `agentic-ai-homelab/docs/signal-fleet-guide.md` (how it works and why), and
`signal-fleet/EVAL.md` (its evaluation design). This document only adds what building a gold dataset from the
fleet's production decisions showed. Every number below was measured; the command or file is named beside it.

## 1. Where this comes from

- **The data:** the fleet's 233 Orrery decisions from 2026-07-25 to 2026-10-29 (test signals removed), published as
  `chipi-nbgd/orrery-triage` on Hugging Face, built by `signal-fleet/datasets/build_orrery_items.py` at `21bc902`.
- **The labels:** the operator's verdicts on the 44 closed issues the fleet filed (from his close comments, each
  confirmed), carried to 60 decisions; and labels on 33 `exact` decisions (the probe answers the model saw),
  proposed by a labeller model (Claude Fable 5.1) and decided by the operator. `verdicts.jsonl` beside the
  decisions says which label came from where.
- **The code read:** `signal-fleet/mvp/triage.py`, `actions.py`, `filing.py`, `probes.py` at `c739792`.
- **The replay:** eval-harness's `examples/triage-fleet/adapter.py` calls the fleet's own
  `triage.investigate(signal, probe_table=...)` with the frozen probe answers, so its prompt, probe budget and
  gates run exactly as in production. Only the model changes between arms.

## 2. Findings about the fleet

### F1. The dismiss gate makes most escalations, not the model (corrected in section 7)

- **Measured:** of production's 49 escalations, **39 begin "dismiss gate: no independent corroborating probe"**: the
  model decided `dismiss` and `triage._dismiss_gate` turned it into `escalate`. 4 more are the cleanup gate; **6**
  are the model's own escalations. (Counted over the 233 decisions' `fleet_decision.reason`.)
- **Why it happens:** a dismissal passes only when an *independent* probe (`service_logs`, `metric`, `trace`,
  `source_state`) returns usable content, or `occurrence_history` looks benign. A browser error has no server-side
  logs, metric or trace, so for client-side noise there is nothing to corroborate with, and every correct dismissal
  becomes an operator escalation.
- **Effect:** production escalates **21%** of signals (49 of 233); its own prompt asks for about 1 in 20 (5%).
- **Example:** `ORRERY-PROD-U`, 2026-10-16. The model wrote "a classic browser-extension hook patching
  addEventListener" (the stack's `addEL_hook` at `<anonymous>:9`), decided dismiss, and the gate escalated it. The
  operator later closed the issue for that error.

### F2. The brief makes every error-shaped signal a filing

- **The prompt** (`triage._SYSTEM`) says: "Anything error-shaped is file-able — an unhandled error … is ITSELF a
  code-invariant violation", and names one dismissable browser class: client network transients.
- **What it never names:** a stale client running an old build (version skew, chunk-load failures after a deploy),
  injected browser-extension code, a staging bundle mirrored somewhere and hit by bots.
- **What the operator closed as noise** (sheet part A, his own close comments): 4 issues "external browser noise, not
  orrery code" (#545 #548 #549 #551), 4 "a deployed staging bundle mirrored …, not real visitors" (#556–#559), 3
  duplicates of those (#560 #561 #563), a low-signal rollup (#523), a config-tuning issue (#429).
- **Example:** 5 decisions on "Cannot read properties of undefined (reading 'universal')" in SvelteKit's client were
  filed as genuine defects; the labeller reads them as stale-client version skew around the fix of 2026-10-21.

### F3. The fleet knows how old the release is, and does not tell the model

- The GlitchTip issue the fleet fetches carries `firstRelease.dateCreated` and `lastRelease.dateCreated`
  (`signal.raw`, on 131 of the 233 decisions). `triage._signal_intro` shows the model only `source`, `alertname`,
  `labels` and `summary` (`triage.py:237`), and `event_detail` names the release only by id (`gha-<sha>`).
- So "this event came from a build weeks older than the current one" is in the fleet's hands but not the model's,
  though it is the operator's most common reason for closing chunk-skew and stale-client errors (#553, #554), and
  the labeller's reason on 5 decisions (`ORRERY-PROD-1D/1O/1T/1U/1V`, release created 2026-09-16, events in late
  October).
- Not covered: whether a fix shipped after that release; no probe says so.

### F4. The model reads little of what is available

- `n_probes` over the 233 decisions: 0 probes 10, 1 probe 88, 2 probes 96, 3 probes 39. The budget is 3
  (`SF_MAX_PROBES`). The probe it most needs for a client error, `event_detail` (the stack, the culprit, the
  release), is one request among six.

### F5. Duplicates are handled after the model, as designed

- `filing.file_or_update` and `file_escalation` look an open issue up (fingerprint, normalized key, alert key) and
  comment instead of opening a new one. The model never sees open issues, and should not have to. An evaluation
  must therefore not mark a filing wrong because an issue already existed (the first labelling pass did; corrected).

### F6. What production gets right and wrong against the labels

- On the 93 decisions with an owner label (final, 2026-10-30), production was right on 59, raised **24 false
  alarms** (filed or escalated noise) and made **10 false dismissals** (dismissed a problem later fixed).
- Of the 12 exact decisions where the labeller disagreed with production, the owner labelled all 12 `dismiss`: 5
  stale-client errors on a weeks-old release (F3), 6 deploy chunk-skew errors from builds without the fix, and 1
  injected browser extension (F1).

### F7. An empty reply on the last turn crashes the decision (corrected in section 7; fixed in e2fbd6a)

- `triage.investigate()` retries a turn whose reply is empty (`continue`). On the last turn there is no turn
  left, the loop ends, and the function returns `None`; `triage()` returns it, and acting on it fails.
- Seen in the replay with gpt-oss:20b on X3 (2026-10-30): a reasoning model whose answer was cut off. Production's
  model rarely returns empty, which is why it has not shown up there. The replay records it as an escalation with
  "no terminal decision" and counts it (`no_decision`).
- Fix: after the loop, fall through to the existing "no terminal decision" escalation, as the non-JSON path does.

## 3. Suggestions for the fleet

Each is a change the replay can measure before it ships: freeze the change, replay the 93 labelled decisions with
the baseline model, compare to production's recorded decisions (section 5).

1. **Let client-side errors be dismissed on their own evidence.** For a GlitchTip browser signal, accept as
   corroboration a benign `occurrence_history` (low count, no user spread) together with a stack whose top frames are
   outside the app (injected or extension code) or a known transient class. Keep the gate for server-side signals.
   Expected effect: most of the 39 gate escalations. Risk: false dismissals of real client defects; measure both.
2. **Name the noise classes in the brief**, as the operator closes them: stale clients and version skew after a
   deploy, injected/extension code, mirrored staging bundles, bots. Pair each with the evidence that shows it.
3. **Show the model the release's age** (F3): add `firstRelease`/`lastRelease` `dateCreated`, and the current
   release, to the signal intro. The data is already fetched; this is a prompt-assembly change. Later, a probe for
   fixes deployed since that release.
4. **Make `event_detail` the default first look for GlitchTip signals**, or give it in the intro instead of as a
   probe, so the budget goes to corroboration.
5. **Recheck the 1-in-20 escalation target** against the gate: the prompt asks for 5% while the gate produces 17% (39
   of 233) by itself.

6. **Tell the model the trade-off it is scored on** (owner, 2026-10-30, for the tuning phase). The evaluation now
   decides on a combined cost: a missed real problem costs 5 false alarms, and false alarms may not exceed
   production's rate. The brief today says the opposite ("anything error-shaped is file-able", "escalate at most
   ~1 in 20"). Writing the same trade-off into the brief aligns what the model optimises with what the operator
   wants; it is the objective itself, not a trick on the test. Measure it like any other change: one arm.

## 4. What the evaluation process taught (reusable for any fleet)

- **The operator's close comments are the verdicts.** GitHub's close reason is COMPLETED on nearly every close; the
  comment says fixed, noise, duplicate. Reading them gave 44 verdicts in one sitting ("all yes").
- **Link an issue to a decision by fingerprint, not by title.** One generic title ("Importing a module script
  failed") matched 37 fingerprints.
- **A verdict reaches only the decision that filed the issue and earlier ones on its fingerprint.** Decisions while
  the issue was open belong to the dedup stage, not the model.
- **A labeller model sees more than the agent did.** Its brief must say what the agent could see, use hindsight only
  to establish what the signal was, and say whether the right call was knowable then. The first pass, without
  those rules, labelled 10 decisions on information the model never had. The second pass still showed the
  labeller the whole stored signal (`signal.raw`) as "seen at decision"; the agent's prompt shows four of its
  fields. "Seen at decision" must be built from the agent's own prompt assembly, not from the stored record.
- **A goal that counts only misses rewards an agent that flags everything.** v1 decided on false dismissals with no
  limit on false alarms; llama3.1:8b, the smallest model run, missed none of 34 real problems by flagging 27 of 31
  noise decisions. A goal for a triage step needs both sides: a ceiling on noise and a price for a miss.
- **Probe retention decides what can be replayed.** Of the 1,528 probe answers in v1, 745 are `unavailable`
  (stores hold logs from 2026-09-30, traces from 2026-10-07). The per-decision probe capture deployed on 2026-10-29
  makes future months exact.

## 5. How to measure a fleet change with eval-harness

The dataset, labels and replay exist; a change to the prompt or a gate is one more arm.

1. Commit the change in signal-fleet; point `TRIAGE_FLEET_SRC` at that checkout.
2. Add an arm config in `examples/triage-fleet/configs/` with the baseline model (`eval-fleet-triage-pro`).
3. `evh run --config <it> --repeat 3` (there is no `evh experiment-run`; corrected 2026-11-04) over the labelled set;
   `evh goals --goal triage_orrery` compares it with the
   baseline arm on `triage_cost` (deciding: a missed real problem costs 5 false alarms), with `false_alarm`
   under its ceiling, `false_dismiss`, `escalated` and cost beside it.
4. Read the per-evidence-level breakdown in the inspector: only `exact` items are what production's model saw.

## 6. To complete after the v1 run

- The ten models' results on the labelled decisions: does any model fix F1/F2 inside today's prompt and gates, or do
  all of them hit the same walls (then the prompt and gate are the lever, not the model)?
- F6 re-measured on the final labels.
- Which suggestions above the results support, with numbers.

## 7. What the fleet session measured and changed (2026-11-04)

Measured in eval-harness round r4 of the goal `triage_orrery`, on `orrery_triage_v1_labelled_v2` (below): the
same 65 owner-labelled decisions, production's model (`eval-fleet-triage-pro`) on every arm, only the fleet's code
changing. Each arm ran 3 passes; each comparison is a paired sign-flip test by item, each side the mean of its 3
passes. `triage_cost` counts a missed real problem as 5 false alarms. Runs: chipi/eval-harness branch 062 (data
under `harness/data/runs/triage_*_2026110*`).

### Answer to section 6: the model is not the lever

80+ model arms on v1 found none significantly better than production's model on `triage_cost`. The changes that
moved it were to the fleet's brief.

### Corrections to F1 and F7

- **F1 (the dismiss gate) is not mainly a cost.** On v1, production's model saw the gate fire on 20 decisions:
  12 where it had dismissed a real problem (the gate saved it) and 8 where it had dismissed noise rightly (the gate
  made a false alarm). At 5 false alarms per miss, loosening the gate as suggestion 1 has it would lose more than it
  gains. But 7 of the 12 saves were an artifact of v1 (next point).
- **v1 held hindsight.** 7 of the model's 18 false dismissals on v1 cited a probe answer production never saw:
  "GlitchTip issue X no longer exists". v1's rebuild also took `lastSeen` from the browser-set event timestamp
  (2023-11-14 on four items, midnight on ten) and, on 13 of 233 items, a `lastRelease` created after the decision.
  v2 (`signal-fleet/datasets/build_orrery_items_v2.py`, published as revision `v2` of `chipi-nbgd/orrery-triage`)
  removes them and records each change in `provenance.v2`. On the 15 affected labelled items the model's own false
  dismissals fell from 0.94 to 0.21 (p 0.002); the fleet's final decisions did not change (the gate had caught them).
  `provenance` still quotes what was removed: never give it to a model as evidence.
- **F7 did not crash production; it hid.** The orchestrator reads `None` as "deferred" but counted nothing, so the
  signal was re-triaged, and paid for, every cycle and never escalated. A reply that never parsed as JSON took the
  same path. Fixed in `e2fbd6a`: an empty last reply defers (counted, escalated after 6 cycles), an unparseable one
  is the "no terminal decision" escalation.
- **F3 (release age) does not separate the cases it was meant to.** ORRERY-PROD-1P (real) and -1V (noise) carry
  the same build age; what differs is whether a fix had shipped by then, which the filing stage knows and the model
  does not. A stale-client rule in filing would have changed 3 of the fleet's 63 real reopens and regressions
  (`freeze_stale_client.py`, in chipi/fleet-eval-data `projects/stale-client-rule/`): parked.

### Shipped: the app failing to load its own code is a real problem (prompt `219b34bf`)

The brief called a failed dynamic import or service-worker load a client network transient to dismiss. The
operator's rule: a problem is to be fixed, and once fixed it should not be seen again. All 13 labelled decisions of
that class are real. `a7dfcd2` files them; CSS-preload and plain fetch failures stay dismissable.

| against production (v2, 3 v 3) | before | after | p |
|---|---:|---:|---:|
| `triage_cost` | 0.872 | 0.446 | 0.0011 (better on 11 items, worse on 1) |
| missed real problems (`false_dismiss`, of 34) | 0.206 | 0.059 | 0.016 |
| escalations (of 65) | 0.292 | 0.118 | 0.0001 |
| filed (of 65) | 0.456 | 0.667 | |
| on the operator's desk: filed + escalated (of 65) | 0.749 | 0.785 | |
| of what is on the desk, noise | 0.445 | 0.373 | |

*Corrected 2026-11-05 (the fleet plan's review):* the fall in escalations is not a lighter desk. The change turns
escalations and dismissals into filings, so slightly more decisions reach the operator (0.749 → 0.785); what it
improves is that fewer of them are noise and far fewer real problems are missed. Read the escalation row with the
two below it. The 12 decisions it moved rest on 12 distinct owner verdicts (none shares one; across all 65 labelled
decisions only issue #554 carries two), so the paired test is not inflated by labels carried between decisions.
Measured on Orrery only: the brief is the same for every project, and PLAYER is a browser app too.
| false alarms (of 31) | 0.699 | 0.613 | 0.13 (not worse) |

Its hypothesis was recorded in the commit before the run, and held: ORRERY-5, -7, -PROD-3, -PROD-G filed in 3 of
3 passes; the CSS-preload noise was not filed. One noise item got worse (ORRERY-U). Without the 15 hindsight items
the effect holds (-0.453, p 0.0018). Deployed 2026-11-04 16:30 UTC (`8213775`, `DEPLOY PASS`).

### Measured, not shipped

- **Naming the client noise the operator closes** (`13856f9`: injected extension code, a browser too old for the
  bundle, a mirrored bundle) moved the model (its own false alarms 0.376 → 0.226, p 0.049) and not the fleet
  (`triage_cost` p 0.22; escalations 0.292 → 0.390, p 0.017, worse): the gate escalated the new dismissals.
- **The same, with the gate taking a deterministic marker of that noise as corroboration** (`01226ca`, on top of
  what ships): the targeted items became right dismissals in 3 of 3 passes, but against what ships `triage_cost`
  was +0.056 (p 0.48) and escalations +0.077 (p 0.019, worse). Its recorded prediction failed: four real problems
  turned cleanup or dismiss in 1 of 3 passes each, and the mirrored-bundle sentence made the model call four
  CSS-preload decisions cleanup, which the cleanup gate escalates. A smaller version (the gate and two classes,
  no mirror sentence) was designed after reading these 65 items, so it is to be confirmed on decisions made from
  now on, not on these.

### Not covered by this section

- One model, one project (Orrery), GlitchTip errors only; 65 decisions, of which 30 are `exact`.
- No held-out set: every change was designed and measured on the same 65 decisions. The shipped change was named
  from the gate analysis before its run; the rest were not tested on unseen data.
- The live effect is not observed yet: no new signal reached the fleet in the first hour after the deploy.
- ORRERY-S (real) was dismissed in 3 of 3 v2 baseline passes against 1 of 3 on v1; its evidence differs only in the
  wording of the store-unavailable answers. Whether that wording moves the model is not separated from its own
  pass-to-pass variation at k=3.

## Not covered

- Grafana alerts: this dataset is GlitchTip errors from Orrery only; the gate's behaviour on server-side alerts is
  not measured here.
- podcast_scraper and homelab signals: not in this dataset.
- The filing stage's own correctness (dedup, grouping): the dedup dataset `chipi-nbgd/signal-fleet-dedup` covers its
  normalisation functions, not this.
- None of the suggestions has been tried; each needs its replay before it ships.
- Hosted Llama 4 Scout (OpenRouter, 2026-10-30): not runnable as the fleet calls it. No endpoint supports
  `response_format: json_object` (OpenRouter's routing removed all four), so Scout runs self-hosted only. A fleet
  that needs JSON mode is tied to the providers that offer it: worth knowing before switching models.
