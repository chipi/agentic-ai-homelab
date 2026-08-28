# Signal-fleet triage enhancements — holistic design

**Status:** design (pre-build), 2026-08-28. Driver: the v2.7 cleanup-pass
handover (2026-08-27) — auto-triage filed ~50+ issues for ~27 real signals and
mixed real bugs with working-as-designed noise. Eight improvements; this note is
the architecture that unifies them and the validation plan that proves each
stage. Execution is staged (#1→#8), every stage gated green before the next.

Source feedback: the handover pasted into the 2026-08-28 session (kept verbatim
in that transcript). Companion prod artifacts referenced by it
(`V2.7-BUG-TRIAGE`, `ISSUE-CLEANUP`) live in the **podcast_scraper** repo, not
here.

---

## 1. The pipeline today (where each item lands)

```
 sources.py           triage.py                     filing.py / actions.py
 ─────────            ─────────                     ──────────────────────
 poll GlitchTip  →  operational_class() [det]  →   file_or_update():
 /Grafana           ├─ hit  → dismiss (no LLM)       ledger dedup on `fingerprint`
 _is_test_signal    └─ miss → investigate() [LLM]      + curated group_key (storm)
 [det, ingest]         probe loop, N=3                reopen/regression/mute
 to_error_signal       gates: intent/cleanup/dismiss  labels: triage-fleet/*
 fingerprint =                                        correlate._event_summary
 glitchtip:{shortId}                                  (frames, release, trace)
```

Three deterministic layers already exist and are the seams the 8 items extend:

- **Ingest classifiers** (`sources._is_test_signal`, `triage.operational_class`)
  — no-LLM, run before/around the LLM, hold even when the triager is down.
- **Filing/dedup** (`filing.py`) — no-LLM, post-triage, **eval-neutral**
  (`score.py` never calls it).
- **Evidence extraction** (`correlate._event_summary`, `probes.py`) — feeds the
  triager's investigation.

## 2. The one unifying idea — extend the deterministic taxonomy, don't sprinkle

Today there is exactly one deterministic class function: `operational_class()`
(cost-cap / provider-budget / provider-fallback → **dismiss**). The handover asks
for more classes (external-transient, external, environment, low-signal,
recoverable). Rather than scatter regex checks, we add **one** classifier that
returns a single taxonomy tag, and the tag drives four downstream behaviors:

```
signal_class(signal) -> one of:
   operational        (existing: cost-cap/budget/fallback)  → DISMISS  [gate, safe]
   test/synthetic     (existing: _is_test_signal)            → CLEANUP  [gate, safe]
   external-transient (Deepgram timeout, provider 5xx/timeout)→ FILE config-enh [hint]
   external           (OpenAI 400 data_inspection, upstream 4xx)→ FILE config-enh [hint]
   environment        (permission denied, CARGO_HOME, disk)  → FILE config-enh [hint]
   low-signal         (1 occ, 0 users, unsymbolicated)       → FILE→rollup [filing]
   recoverable        (RecoverableSummarizationError, degraded)→ FILE low-prio [hint]
   code-bug (default) (everything else)                       → LLM decides [unchanged]
```

**The safety invariant (SIGNALS §7, non-negotiable):** a dismissed real defect is
a false-dismiss = eval FAIL. Therefore **only `operational` and `test` gate the
disposition** (they are provably-not-a-code-bug: a billing state, a guardrail
firing, a synthetic run). The genuinely-ambiguous new classes
(external / environment / recoverable / low-signal) **never force dismiss** — they
bias `work_type` (bug → config-enhancement), template the acceptance criteria, and
route filing. The LLM still owns file-vs-escalate for them. This is what keeps
false-dismiss at 0 while still fixing "ERROR-logged ≠ code bug."

**But the safety hole this opens (Fable 5 review R1, load-bearing):** biasing
`work_type` to `config-enhancement` is itself a lost-defect channel *below the
current metric*. Per §7.2, `config-enhancement` is invisible to Fleet 1 by an
existing guard — so a real bug misrouted to `config-enhancement` scores
disposition=`file`, false-dismiss=0, **BAR: PASS**, yet the defect never reaches
the fix pipeline. `score.py` scores disposition strings only (`score.py:107-113`).
**Fix, mandatory before #2/#3 ship:** dual ground-truth gains a `work_type`, and
`score.py` gains a **MISROUTE metric** (true_nature=bug that got filed as
`config-enhancement`) with its own hard bar = 0, treated exactly like
false-dismiss. Without this the eval is blind to the harm #2/#3 can do.

Mapping of that idea to the 8 items:

| # | Item | Layer | Mechanism | Eval impact |
|---|---|---|---|---|
| 1 | Normalize dedup key | filing | `normalized_key()` strips volatile tokens; fallback dedup dimension in `ledger_lookup` + new ledger col | **neutral** (filing) |
| 2 | Recoverability severity | ingest+triage | class `recoverable` → work_type/priority hint, never dismiss | **touches** (prompt) |
| 3 | External/env/transient | ingest+triage | `signal_class()` det tags → work_type=config-enhancement + acceptance template | **touches** (prompt) |
| 4 | Occurrence/user gating | ingest+filing | `low_signal()` det; sub-threshold FILE collapses to one per-area rollup issue | **neutral** (filing) |
| 5 | Innermost `__cause__` | evidence | `_event_summary` walks chained values, surfaces cause_* fields | **neutral** (enrich) |
| 6 | Stamp code_version | evidence+filing | surface `release`/sha into issue body + field | **neutral** (enrich) |
| 7 | Cross-link area+frame | filing | search open triage-fleet issues by area+normalized top-frame; "related to #N" | **neutral** (filing) |
| 8 | Area label + milestone | filing | area→`area:*` label on create; default `triage` milestone | **neutral** (filing) |

Only **#2 and #3** change the LLM triager's behavior; the other six are
deterministic and eval-neutral.

## 3. `normalized_key()` — the ~40% lever (item #1), specified

GlitchTip mints a new `shortId` per unique event fingerprint, and its fingerprint
embeds volatile tokens → one logical bug fragments into N `glitchtip:*` fps → N
issues. Fix: a stable key computed by us.

Normalization (order matters, most-specific first) — strip/placeholder:
- hex work/episode IDs: `\b[0-9a-f]{8,}\b`, UUIDs → `<id>`
- byte counts / integers ≥4 digits: `\b\d{4,}\b` → `<n>`
- dollar amounts: `\$\d+(\.\d+)?` → `<$>`
- paths: `(/[\w.\-]+){2,}` → `<path>`
- run/trace ids: `run-\d{8}T\d{6}\.\w+`, `[0-9a-f-]{20,}` → `<run>`
- ISO timestamps, bracket counters `\[\d+\]` → `<t>`, `[n]`

Key = `"v1:" + sha1( source | exc_type | normalized_skeleton | frame )[:12]`
(**revised per review R2/R4**):
- **versioned** (`v1:`) — any change to the extractor (#5) or the regex list
  re-fragments *loudly* instead of half-matching stale ledger keys.
- **`source` included** — a Grafana alert and a GlitchTip error must not
  cross-collapse in the degraded (no-exc_type) case.
- **`area` DROPPED from the hash** — `file.area` is LLM free-text
  (`actions.py:129`), so "summarization" vs "summarizer" across runs would
  re-key the same bug. Non-deterministic input has no place in a "deterministic"
  key.
- **skeleton from `alertname`/title only**, never `summary` —
  `sources.py:137-138` embeds `count=42, level=…, culprit=…` and `count` advances
  every poll; `\d{4,}` wouldn't strip 42→43.
- **`frame` = filename + function, NO lineNo** — `correlate.py:68` formats
  `file:lineNo function`; any deploy shifts the line. exc_type/frame come from
  `_event_summary` when available, else "".
- **empty norm_key NEVER matches** — a keyless row must not match all other
  keyless rows (the classic fuzzy-key bug).

`ledger_lookup` tries **fp → group_key → norm_key** in order, and the norm_key
dimension uses **newest-row** semantics (R3: first-match returns the oldest row →
after one regression cycle it resolves to a stale closed issue) and **never
inherits MUTED** (R3: mute is an operator judgment about ONE bug; inheriting it
across a fuzzy hash silently buries a different bug forever — only exact fp /
group_key hits honor MUTED). All norm_key reads are `.get("norm_key","")` (R3/#c4:
`filed.tsv` is a SEPARATE ledger from `config.LEDGER`; `_ensure_ledger_schema`
migrates the latter, not the former — old 6-col rows zip short and lack the key).

**Must-not (negative controls, tested):** (a) two different bugs (different
exc_type or top frame) must NOT share a norm_key; (b) the harder shape — two
different bugs with the **same exc_type whose top frame is a shared helper**
(`get_json`-shaped wrapper) must NOT collapse — refine "top app frame" to skip
known helpers or document the accepted risk; (c) a message with no volatile
tokens passes through unchanged; (d) same signal at count=42 and 43 → same key;
(e) golden frozen hash values, so a regex change breaks loudly.

## 4. Validation & reproducibility — the heart of this plan

Two gates already exist; we extend both and lean on the deterministic one.

### 4a. Deterministic gate — `eval_hardening.py` + `hardening-cases.json` (no LLM, no cost, no flakes)
This is the reproducibility engine: a versioned dataset of **real scrubbed
production signals** → asserted behavior, same input → same verdict. We extend the
`kind` taxonomy and add cases carrying the handover's real fingerprints:

- `kind:"dedup"` — a cluster of the handover's real fps (audio-eviction #1840-49,
  ADR-148 #1556…#1866) must collapse to **one** norm_key; a negative-control pair
  (two different bugs) must NOT.
- `kind:"signal-class"` — Deepgram-timeout #1529 → external-transient; OpenAI-400
  #1480 → external; Cargo-perm #1546 → environment; **negative controls**: a
  null-deref / real bug → `code-bug` (never external/environment).
- `kind:"low-signal"` — single-occ unsymbolicated #1345 → low-signal; count=42
  span-export → NOT low-signal.
- `kind:"cause"` — a chained-exception fixture (#1854 shape) → cause_frame is the
  inner per-feed frame, not the outer wrapper.

Every handover example becomes a frozen case. `python3 eval_hardening.py` exits
non-zero on any regression. **This is the per-stage gate.**

Additional cases the review flagged as easy-to-miss:
- **anchor-override**: a fixture where the deterministic tag is *wrong*
  (`signal_class=external-transient` but true_nature=bug — our retry logic
  mishandles a Deepgram timeout) → the LLM must file `bug`, not
  `config-enhancement`. Proves the class is a bias, not a gate, at the LLM level.
- **shared-helper frame** negative control (R4b above).
- **filed.tsv old-schema**: load a 6-col `filed.tsv` under 7-col `FILED_COLS`,
  lookup+upsert, no `KeyError` (all reads `.get`).
- **cause chain against a REAL captured GlitchTip payload**, not a hand-built one:
  the Sentry `values[]` ordering (which end is innermost) is the trap — a
  synthetic fixture built to my own assumption can't catch an inversion. Plus a
  depth-cap case. (Ties to §6 open item: capture one real chained-exception
  sample before trusting #5's ordering.)
- **low-signal + recoverable composed** (the maximally-buried path) and the
  **promotion** case (R6).

### 4b. Probabilistic gate — `score.py` (LLM, k≥3, costs money)
Only #2 and #3 touch the prompt. After those, run
`SF_OBSERV_DISABLED=1 SF_TRIAGE_MODEL=deepseek/deepseek-v4-pro python3 score.py 3`
and require the operator's bar held: **false-dismiss = 0 AND escalate ≤ 0.05**.
New labeled fixtures (dual ground-truth) added for the new classes. Cost is
surfaced to the operator BEFORE running (k=3 × N fixtures × v4-pro on the litellm
gateway).

### 4c. Filing unit checks (no network)
`filing.py` functions (`normalized_key`, rollup grouping, cross-link matching,
label/milestone mapping) get direct assertions with `_gh` monkeypatched to a
recording fake — no GitHub writes.

## 5. Staging & exit criteria (REVISED per review R2 — each stage green first)

**Stage 0 (gate, not a footnote):** run `score.py` baseline on this box and
confirm the bar still holds *before any change*; confirm current stage
(propose vs shadow). No delta claim is valid without this baseline.

1. **#5 cause** + **#6 version** — evidence enrichment. Must land BEFORE #1:
   #1's key consumes `_event_summary`'s frame/exc_type, which #5 rewrites —
   minting keys first would orphan them when #5 lands (R2).
2. **#1 norm-key** — deterministic dedup cases (golden hashes) + filing unit
   checks. Now safe: the extractor it depends on is frozen.
3. **#4 low-signal rollup** — low-signal cases + rollup unit check, **including
   the promotion rule** (R6): a real bug's first hit IS low-signal, so a
   norm_key/user-count crossing the threshold must break OUT of the rollup into
   its own issue — else first-occurrence bugs stay buried on recurrence.
4. **#7 cross-link** + **#8 labels/milestone** — filing unit checks (mocked
   `_gh`). #8 milestone + `area:*` labels are resolve-or-skip, never fail a file.
5. **#3 signal-class** — det class cases + negative controls; **declare
   precedence vs the existing `OPERATIONAL_MARKERS`** (R5: `fallback failed`
   already deterministically dismisses part of what #2/#3 want to file — pin the
   precedence with a case). Then `score.py` with the new MISROUTE metric holds.
6. **#2 recoverability** — class cases + `score.py` (false-dismiss=0, MISROUTE=0,
   escalate≤5%). #2 keys on the exception *type name* in the signal; if a real
   sample doesn't carry `RecoverableSummarizationError` verbatim, #2 degrades to
   heuristics (open question §6).

Order rationale: evidence extractors first (they're inputs to the key), then the
key, then filing behaviors, then the two LLM-touching items last so the expensive
eval runs once. Each stage: code + frozen cases + `eval_hardening.py` green
(+ filing unit checks); stages 5–6 also gate on `score.py`.

### 5b. Filing-tree hazards the norm_key dimension must respect (review R3/R5)
- **Mute inheritance** (`filing.py:237-238`): norm_key hits never honor MUTED.
- **Comment-cap black hole** (`filing.py:240-241`): a norm_key hit that returns
  `DEDUP` with no comment must still land its `actions.ledger_append` row — pin
  in a test so the occurrence is never invisible.
- **Newest-row lookup** (`filing.py:144-154`): norm_key resolves to the newest
  matching row, not the first (oldest/closed).
- **Shadow path** (`actions.queue_proposal:177`, `filing.py --flush-queue`):
  both dedup on fingerprint only, so in `shadow` the fragmentation persists.
  **Decision (operator, 2026-08-28): extend norm_key into the shadow path too** —
  `queue_proposal` + `--flush-queue` dedup on norm_key, so fragmentation dies in
  shadow as well as propose.

## 5c. Progress (2026-08-28)

- **Stage 0** ✓ deterministic baseline `eval_hardening.py` 9/9; `score.py` LLM
  baseline DEFERRED to just-before-Stage-5 (Stages 1–4 are score.py-neutral).
- **Stage 1 (#5+#6)** ✓ `correlate._summarize_event` (innermost cause, code_version),
  `actions.build_issue` stamp. 12 unit tests green.
- **Stage 2 (#1)** ✓ `filing.normalized_key` + ledger norm_key dimension
  (newest-row, never-inherit-MUTED) + shadow-path extension
  (`queue_proposal`/`--flush-queue`). 17 unit tests green incl. golden hashes;
  real handover clusters collapse (audio-eviction 10→1, ADR-148 →1). Golden
  testing caught a decimal-vs-hex byte-count normalization bug, now fixed +
  regression-guarded.
- **Stage 3 (#4)** ✓ `filing.low_signal` + per-bucket rollup (`_file_rollup`) +
  promotion (R6). 8 unit tests. Rollup is a FILE, never a dismiss.
- **Stage 4 (#7+#8)** ✓ `_related_issues` cross-link (best-effort GH search),
  `actions.build_issue` area label, `_ensure_labels` + `_milestone_number`
  (resolve-or-skip). 7 unit tests.
- **LLM-eval access SOLVED (2026-08-28):** litellm gateway `http://homelab:4001`
  reachable from the Mac over tailnet; auth via `LITELLM_MASTER_KEY` (fetched
  inline from the container env, never stored); models `fleet-triage-pro/flash`
  (in `config.RATES`). Run: `SF_TRIAGE_MODEL=fleet-triage-pro
  SF_OPENROUTER_URL=http://homelab:4001/v1/chat/completions OPENROUTER_API_KEY=$K
  SF_REFERENCE=../reference python3 score.py 3`. Baseline confirms prompt sha =
  `c2ece738` (the recorded-PASS prompt).
- **Baseline (k=3, fleet-triage-pro, prompt c2ece738):** BAR PASS —
  false-dismiss 0/9, escalate 2/42=0.05, file-recall 0.78.
- **Stage 5 (#3) + Stage 6 (#2)** ✓ `triage.signal_class` (external-transient /
  external / environment / recoverable) injected as a per-signal HINT into the
  USER message — `PROMPT_SHA` stays `c2ece738`, and **no existing fixture triggers
  it** (baseline behavior preserved). Only `operational`/`test` gate a dismiss;
  these classes bias `work_type`, never dismiss. `score.py` gains the **MISROUTE**
  metric (hard-zero). 7 new deterministic hardening cases (incl. 3 negative
  controls: real bug, bare-timeout span-export, client dynamic-import → all None).
  4 new LLM fixtures with `work_type` ground truth, incl. the **anchor-override**
  control.
- **FINAL EVAL (k=5, 18 fixtures, 89 scored):** **BAR PASS** —
  `false-dismiss 0/34`, **`MISROUTE 0/12`**, escalate `4/89 = 0.04` (under the
  bar, more headroom than baseline), file-recall **0.91** (up from 0.78). Anchor
  fixture filed as bug 5/5 (hint overridden — proves bias-not-gate). All 4 new
  fixtures filed 5/5 (no false-dismiss).
- **FINAL EVAL after gap-closure (k=5, 19 fixtures, 95 scored, 0 table-miss):**
  **BAR PASS** — `false-dismiss 0/40`, **`MISROUTE 0/13`**, **`routing 25/25 =
  1.00`** (every config-enh-truth fixture filed AS config-enhancement),
  file-recall `0.95`, escalate `2/95 = 0.02`. Per-fixture: ANCHOR→file/bug 5/5
  (hint overridden), DEEPGRAM/INSPECT/CARGO/RECOVER→file/config-enhancement 5/5.
- **Full suite:** `test_units.py` 44/44, `eval_hardening.py` 16/16, `score.py`
  k=5 BAR PASS (0 table-miss). All exit 0.

## 5d. Gap closures (2026-08-28, "no gaps" pass)

- **Routing direction now MEASURED, not inferred:** `score.py` logs `got_work_type`
  and reports `routing (cfg-enh)` — of config-enh-truth fixtures that filed, how
  many came out `config-enhancement`. (Was: only the bug-direction MISROUTE was
  measured.)
- **`external` class now has an LLM fixture** (`glitchtip-PODCAST-INSPECT-1`,
  OpenAI 400 data_inspection → config-enhancement). All 5 secondary classes are
  now exercised through the LLM, not just deterministically.
- **Table-miss eliminated:** the 1 table-miss (CARGO run4 requesting
  `source_state`) is fixed — every new fixture freezes the full probe menu incl.
  `source_state`.
- **#5 ordering VERIFIED against the real Sentry SDK** (`sentry_sdk 2.63.0`,
  `event_from_exception` on `raise Outer from Inner`): `values[0]`=inner cause,
  `values[-1]`=outer wrapper — exactly what `_summarize_event` assumes. No longer
  spec-only.
- **#7 cross-link PROVEN end-to-end against live GitHub:** `_related_issues` on
  culprit `_generate_and_validate_summary` returned the real open issue
  `chipi/podcast_scraper#1556` (the ADR-148 issue from the handover); empty/garbage
  frames return `[]` safely.

## 5e. Proving "better than before" — real-corpus dedup eval (2026-08-28)

"Passes the bar" ≠ "better than before." The #1 dedup benefit (the headline) is
NOT measured by score.py (triage dispositions) or eval_hardening (classifier
gates). So it was, until now, only unit-tested on 2 hand-picked clusters. Closed by:

- **`mvp/eval_dedup.py` + `reference-dedup/corpus.json`** — a frozen, scrubbed
  sample of **100 real GlitchTip signals** replayed through the deterministic
  filing stage (operational gate + norm_key + low-signal). Asserts collapse floors
  so the win can't silently regress. No LLM, no network.
- **Measured on real production data:** 100 issues → 56 operational (dismissed) →
  **44 fileable → 20 distinct norm_keys = 55% fewer issues** (floor 40%), + 23 of
  the 44 folded to low-signal rollups. Biggest merges are the handover's own
  clusters: **×12 audio-eviction**, ×7 RecoverableSummarizationError, ×4
  dynamic-import, ×3 run-budget. `eval_dedup.py` → PASS.
- The handover asked for "~40%"; reality is **55%** from norm_key alone. This is
  the strongest before/after evidence — real data, deterministic, committed.

Caveat: this is the FILING-stage collapse (assumes the triager files those 44; it
runs first). The collapse *ratio* is exact for whatever subset is filed. Corpus is
one 100-issue API page from a cost-cap-storm-heavy window.

**Three offline gates now guard the work** (all no-LLM, deterministic, exit-coded):
`test_units.py` (53, mechanisms) · `eval_hardening.py` (16, classifier + negative
controls) · `eval_dedup.py` (collapse floors). Plus `score.py` (LLM, BAR).

## 6. Non-goals / open questions (equal weight)

- **NOT auto-dismissing** external/environment/recoverable — deliberately. If the
  operator wants some of these dismissed-not-filed (lower volume, higher
  false-dismiss risk), that's a separate decision with its own negative controls.
- **#5 chained-exception ordering — RESOLVED by inspecting the live corpus
  (2026-08-28):** queried the GlitchTip DB directly (`issue_events_issueevent`,
  authorized mini access) — **all 62 exception events have `values` length = 1**;
  there are currently NO chained exceptions stored (even the #1854 "one or more
  feed failures" logs as a single exception, not a `__cause__` chain). So the
  multi-value ordering is spec-based only (Sentry "oldest first" = innermost
  first), isolated in `_summarize_event`, and doesn't affect any real event today
  (all resolve to depth=1, inner==outer, which is correct). Re-confirm when a real
  chain first appears.
- **Reading the podcast_scraper source** for recoverability markers
  (`RecoverableSummarizationError`, `record_stage_outcome`) — #2 keys on the
  exception *type name* in the signal, not on cross-repo source. Confirm the type
  name actually appears in the GlitchTip signal (needs a real sample) before
  trusting it; else #2 degrades to "recoverable" heuristics only.
- **Milestone existence** (#8) — assigning a `triage` milestone needs the
  milestone to exist in each target repo; resolve-or-skip, never fail the file.
- **norm_key retro-migration** — existing `filed.tsv` rows lack `norm_key`;
  backfill is best-effort (new column defaults empty), old dupes are not
  retroactively merged.
- **Not verified yet:** whether the fleet is currently in `propose` (issues live)
  or `shadow`; the current live escalate/file volume; that `score.py`'s baseline
  still passes on this box today (must run it once before claiming a delta — now
  Stage 0).
- **Two distinct ledgers, do not conflate** (review #c4): `config.LEDGER`
  (dispositions.tsv, migrated by `actions._ensure_ledger_schema`) vs the filing
  `filed.tsv` (`filing.FILED_COLS`, NOT auto-migrated). norm_key adds a column to
  `filed.tsv` only; old rows lack it → every read is `.get("norm_key","")`.
- **`area:*` label auto-create** (#8): not verified whether GitHub's create-issue
  REST call auto-creates a missing label or silently drops it — verify before
  relying on it; resolve-or-skip either way.

---

## 7. Review outcome — Fable 5 advisor, 2026-08-28

Verdict: core stance (gate only provably-non-bug classes, bias the rest) is sound
and the right generalization of `operational_class()`, **but** three findings were
folded in above before any code:
- **R1** (load-bearing): work_type misroute is invisible to `score.py` → added the
  MISROUTE metric + `work_type` ground truth as a hard gate for #2/#3 (§2).
- **R2**: stage order — #5/#6 now precede #1; the key is versioned (`v1:`) (§3, §5).
- **R3/R4/R5/R6**: norm_key spec hardened (drop area, title-only skeleton, no
  lineNo, include source, empty-never-matches, newest-row, never-inherit-MUTED);
  filing-tree hazards enumerated (§5b); #4 gains a promotion rule; #3 declares
  precedence vs the operational gate.

The full review (with file:line cites) is in the 2026-08-28 session transcript
(advisor agent `a6c1f4cb329c94839`).

## 8. Pre-deploy code review — Fable 5, 2026-08-28 (agent `a0b950537f21c344c`)

Adversarial review of the IMPLEMENTATION (not the design) before commit+deploy.
Verdict: **not safe as-is** — 3 confirmed must-fix bugs, all one root: `low_signal`
/`normalized_key` assumed GlitchTip field shapes but run on ALL sources, and every
one of the 44 tests used GlitchTip-shaped signals (the structural blind spot). All
fixed + Grafana-shaped tests added (53 total). Fixes are filing-side → eval-neutral,
k=5 BAR PASS still stands.

- **F1 (fixed):** a Grafana alert has no count/userCount/culprit → `low_signal`
  read absence as "low" → EVERY Grafana FILE (incl. orrery-staleness and the
  fail-closed substrate issue) buried in the rollup, promotion unreachable (count
  always 0). Fix: `low_signal` returns False unless `source=="glitchtip"` AND a
  count field is present.
- **F2 (fixed):** `file_or_update` routed ALL kinds through the rollup; an
  escalation/substrate that's low-signal-shaped lost its operator-question to a
  one-line rollup comment. Fix: skip the rollup for `kind in {escalation,substrate}`.
- **F3 (fixed):** same Grafana alertname on two instances → identical norm_key
  (basis lacked labels) → box B's incident deduped onto box A's issue in a possibly
  DIFFERENT repo (`INSTANCE_REPO_MAP`). Fix: append `instance` to the basis for
  grafana only (GlitchTip keys unchanged — golden hash test proves it).
- **Promotion-before-mute (fixed):** muting the low-signal aggregate silently muted
  every bug that later crossed threshold. Fix: promotion now checked before the
  mute gate.

Verified SOUND by the review (no change): filed.tsv 6→7-col migration (zip-short +
`.get`), dispositions.tsv schema untouched (no mass re-triage), GH-call boundaries
degrade-not-abort + within rate limits, signal_class never changes the disposition,
fixtures secret-clean.

Conscious-accept (documented, not blocking): aggressive path normalization can
collapse two different-endpoint failures (the SAME property that collapses the
audio-eviction cluster we WANT merged — keeping path segments would break that);
norm_key-never-inherits-mute means muting a *fragmenting* bug needs a future
`muted-class` label; GlitchTip rollup promotion waits one `RETRIAGE_HOURS` window.
