# What the triage-fleet evaluation teaches the fleet itself

**Status:** living, 2026-10-30. Final once the v1 run has its results (section 6). Written to be handed to an agent
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

### F1. The dismiss gate makes most escalations, not the model

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

### F7. An empty reply on the last turn crashes the decision

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
