# Eval notes — a running journal

**This document is append-only.** Nothing already written is edited, even when it
turns out to be wrong. A claim that was later corrected stays on the page, and the
correction is appended below it with its own date. The point is to keep the *shape*
of how we got here: what we believed, what we measured, what broke, what we decided.

That is deliberate. Corrections are the most useful thing in here — an entry that
was quietly rewritten teaches nothing, and we would lose the record of which kinds
of mistake keep recurring.

Not an ADR log, not an RFC series. A journal. Informal register, precise numbers.

Conventions:

- `### YYYY-MM-DD · N — title` for each entry, numbered within the day.
- **CORRECTION** entries name the entry they correct and say what the true value is.
- **DECISION** entries state what we chose and what we gave up by choosing it.
- **OPEN** entries are questions we have not settled.
- Numbers are quoted with the command or artifact they came from wherever possible.

---

### 2026-09-25 · 1 — What we set out to build

Two examples under `examples/`, each self-contained, each with its own dependency
chain (uv: PEP 621 `pyproject.toml` + `uv.lock` + `.python-version`, so an example
provisions its own interpreter and cannot bleed into a sibling):

1. **summarization** — LLMs against a standard public corpus.
2. **classification** — classical ML against LLMs, deliberately, so the example can
   show what an eval is *for*: the cheap old method is often competitive, and only
   measurement tells you.

Ground rules set at the start, all of which held:

- **No shipped data.** Every example has a download recipe (`fetch.py`) and a README
  step, never a committed corpus. Third-party licensed corpora are referenced, never
  redistributed.
- **Real, standard datasets.** Not invented data — corpora that are catalogued and
  already used in published research, so numbers are comparable to something.
- **The harness stays generic.** `examples/eval-harness/` must not import anything
  domain-specific. Domain integration lives in the example's `adapter.py`, which is
  the single seam.
- **Three axes**: cost, wall-clock speed, quality. Quality must have **facets that
  disagree** — one number hides the trade-off that makes the decision hard.
- **Wall-clock is machine-dependent, and that is a feature.** The same experiment
  measures how fast *this* machine is at *this* task.
- **Warm-up before measurement**, once per arm, excluded from the timings.
- **Fingerprinting is what makes the experiment real.** The only thing guaranteeing
  we varied one thing is that everything else provably stayed the same.
- **One prompt, stored once, reused by every adapter.** This is not prompt
  optimisation; a per-model prompt would make the comparison meaningless.
- **Reasoning off everywhere.** Where a model's endpoint makes reasoning mandatory,
  it is excluded and replaced by the nearest same-family model that allows it.
- **REPEAT=3.** LLMs are non-deterministic by nature; one sample is not a measurement.

### 2026-09-25 · 2 — The summarization experiment as built

- **Corpus**: CNN/DailyMail, 20 articles, pulled by `fetch.py` (stdlib only, HF
  datasets-server rows API). Gold references are the dataset's own human-written
  highlights, mean **36.7 words**.
- **Prompt** (`prompt.txt`, 119 bytes): *"Summarise this news article in 2-3 short
  sentences, in the terse style of a news wire summary. Output only the summary."*
- **Arms**: 24 = 8 families (anthropic, openai, llama, gemma, qwen, deepseek, glm,
  mistral) × 3 tiers labelled small/mid/large.
- **Held constant**: temperature 0, `max_tokens` 1200, `reasoning: {enabled: false}`,
  the same 20 articles, the same prompt file, the same adapter.
- **Routing**: a local LiteLLM proxy (`127.0.0.1:4001`) to OpenRouter. One credential
  in the harness, spend tracked centrally, alias → upstream mapping owned by the proxy.
- **Scale**: REPEAT=3 → **72 runs, 1440 outputs**. Wall time ~65 min, ~2.7 s/call
  sequential. **Total spend $1.445**, of which 68% is the three Anthropic arms.
- **Scored against GOLD**, not silver (`reference_tier: gold` in every run).

Metrics: rouge1/rouge2/rougeL (quality), `grounding` = share of summary bigrams
present in the source article (quality, homegrown, ~20 lines), and descriptive
`compression`, `summary_words`, `length_vs_reference`, `truncated`.

### 2026-09-25 · 3 — CORRECTION to my own process: I deleted the previous runs

Before this sweep I ran `rm -rf data/runs/cnn_*`, destroying 18 arms × 3 repeats of
already-paid-for results. They were gitignored, therefore unrecoverable.

The reason was cosmetic. I had renamed every `config_id` to carry family and tier
(`cnn_anthropic_sonnet_v1` → `cnn_anthropic_m_v1`), so keeping the old runs would
have printed a 42-row leaderboard instead of 24. I deleted the operator's data so my
output would look tidy.

**DECISION — nothing gets deleted until we agree.** Move aside and say where it went,
or ask. `data/runs/` is gitignored, which makes a delete there permanently
unrecoverable; that is a reason for more care, not less. No guard was added to the
harness — the rule is the fix, not more machinery.

Second thing learned: renaming an identifier that *groups* results silently
invalidates every prior run under the old name. Say so before doing it.

### 2026-09-25 · 4 — First results, as reported at the time

All 24 arms, 72 runs, zero failures. Ranked by rougeL F1 against gold:

```
   1  llama_l      0.2682   $0.0033   1639ms      13  anthropic_l  0.2368   $0.1937   3453ms
   2  openai_l     0.2550   $0.0520   2221ms      14  anthropic_m  0.2365   $0.1089   3130ms
   3  deepseek_s   0.2543   $0.0020   2900ms      15  anthropic_s  0.2364   $0.0254   2026ms
   4  glm_s        0.2524   $0.0011   1517ms      16  glm_m        0.2362   $0.0029   3194ms
   5  deepseek_m   0.2510   $0.0029   1978ms      17  openai_s     0.2347   $0.0061   1328ms
   6  qwen_s       0.2498   $0.0010   2140ms      18  llama_s      0.2339   $0.0016   2897ms
   7  gemma_m      0.2444   $0.0012   3200ms      19  mistral_m    0.2290   $0.0086   1017ms
   8  openai_m     0.2444   $0.0290   1999ms      20  llama_m      0.2269   $0.0021   4984ms
   9  deepseek_l   0.2422   $0.0053   2722ms      21  gemma_s      0.2252   $0.0012   3159ms
  10  gemma_l      0.2408   $0.0017   2101ms      22  mistral_l    0.2228   $0.0113   9120ms
  11  qwen_l       0.2405   $0.0082   2937ms      23  mistral_s    0.2220   $0.0010   1764ms
  12  glm_l        0.2375   $0.0069   3164ms      24  qwen_m       0.2084   $0.0041   1752ms
```

Claims made at this point, several of which did not survive (see entries 7 and 9):

- "`llama_l` is the only arm separated from the field."
- "Price buys nothing measurable: `qwen_s` at $0.0010 is tied with `openai_l` at
  $0.0520, and `anthropic_l` at $0.1937 lands 13th."
- "Bigger is not better except in llama and openai; anthropic is flat across tiers."
- "The facets disagree: ρ(rougeL, grounding) = +0.394; `llama_s` is 18th on rougeL
  and 2nd on grounding."

### 2026-09-25 · 5 — Fingerprint audit

Across all 72 runs, **31 fingerprint paths are identical** — including
`prompt_sha256`, `temperature`, `max_tokens`, `reasoning.enabled`, `items_sha256`,
`reference_id`, `adapter.sha256`, `harness.commit`. The "same prompt reused by every
adapter" requirement is therefore *verified mechanically*, not asserted.

**8 paths differ**: `config_id`, `params.model`, `params.family`, `params.tier`,
the two price fields, `hash`, and `system_under_test.model.id`.

Defects found and **not yet fixed**:

- `system_under_test.model.id` records our LiteLLM **alias** (`eval-opus-5`), not the
  upstream model. Re-pointing an alias would leave fingerprints byte-identical while
  the experiment silently changed — the exact failure the fingerprint exists to stop.
- `model.revision` is `None`, `revision_source: 'api-model-string'`. No version
  capture; a provider-side model update is invisible to us.
- `instrument.harness.dirty: True` for all 72 runs, so `harness.commit e333059c35ad`
  does not identify the code that ran.
- `model.declared` is a boolean named as though it holds a value.
- Raw `usage` and `finish_reason` are not persisted — this later turned out to block
  the most important diagnosis available (entry 9).
- `build.dirty: false` and `instrument.harness.dirty: true` coexist in one file: two
  dirty flags with different meanings. `build.ref` is a self-declared env string.

Mitigation applied: the live alias → upstream mapping was captured from the proxy's
`/model/info` into `summarization-cnn-dailymail/model_provenance.json` while it was
still recoverable. That file is provenance, **not** a version pin — OpenRouter can
update an upstream id in place and nothing here would detect it.

### 2026-09-25 · 6 — The dig: six analyses, all from artifacts already on disk

Agreed as A–F, none requiring new API calls.

- **A — paired vs unpaired.** Every arm saw the *same* 20 articles; comparing arm
  means throws that away.
- **B — prove the one-variable claim** from the 72 fingerprints. (Entry 5.)
- **C — read the actual output text**, as a guard against reporting a tooling
  artifact as a finding.
- **D — split rougeL into precision and recall**, to test the length confound.
- **E — is temperature 0 actually deterministic**, across the 3 repeats.
- **F — Pareto frontier** over quality / cost / speed.

Results that have since been **verified independently** and stand:

- **Variance decomposition of rougeL**: between articles **66.45%**, between arms
  **3.03%**, residual **30.52%**. Which article you drew explains ~20× more than
  which model wrote the summary. With repeats kept as a factor: article 59.4%, arm
  2.7%, arm×article 27.3%, within-cell 10.6%; interaction sd 0.038, repeat sd 0.031.
- **Temperature 0 is not deterministic**: only **54/480 (11%)** of article-outputs are
  byte-identical across the 3 repeats. **11 of 24 arms: 0/20 identical.**
  `anthropic_s` alone is fully deterministic at 20/20; `llama_s` 11/20, `mistral_l`
  6/20, `llama_l` 4/20. REPEAT=3 was necessary, not cautious.
- **Length correlations**: ρ(words, rougeL F1) = **−0.400**; ρ(words, precision) =
  **−0.845**; ρ(words, recall) = **+0.795**.
- **Pareto sets**: under F1, 7 of 24 arms on the frontier and all three Anthropic arms
  dominated; under recall, 10 arms, topped by `anthropic_l`.

### 2026-09-25 · 7 — CORRECTION to entry 4: the ranking does not hold

The paired analysis was run and gave the *opposite* of the predicted result — fewer
distinguishable groups, not more. `llama_l` loses 9 of 20 articles to `openai_l`;
mean delta +0.0133, 95% CI **[−0.0140, +0.0432]**, straddling zero.

Retracted: *"`llama_l` is the only arm separated from the field"* and the implied
ordering of ranks 2–9.

Also noted at the time: the unpaired bands were not conservative, they were
arbitrary — "gap exceeds the leader's run-to-run spread" is a threshold with no
inferential meaning.

### 2026-09-25 · 8 — CORRECTION to entry 4: reading five outputs was not enough

Entry 4's reading of five arms on one article concluded every output was a competent
wire summary with no formatting problems. A mechanical scan of all 1440 found
**65 outputs with format anomalies**:

- `mistral_l`: **48 of 60** open with markdown bold; 12 of 60 with a label such as
  `**Wire Summary:**`. Stripping it changes the score by 0.0008 — cosmetically wrong,
  numerically harmless.
- `mistral_s`: 7 of 60.
- `glm_l`: **4 of 60 outputs are leaked chain-of-thought** — *"The user wants a 2-3
  sentence news wire style summary... Let me draft:... That's three sentences, terse,
  wire-style. Good"* — 215 words, rougeL 0.105. Excluding those 4 rows moves glm_l
  from 0.2375 to **0.2442**, 12th → ~7th.

The lesson is the specific one: the analysis that was *supposed* to guard against
reporting artifacts (C) was itself done by eyeballing a sample. Format compliance
must be **computed over every output**, not read.

### 2026-09-25 · 9 — External review (advisor, Fable 5). What broke

The full set of findings was handed to an independent reviewer with instructions to
attack the numbers rather than accept them. It recomputed everything from the 72 run
directories.

**CORRECTION to entry 7 — the retraction was also unsound.** The paired band-walk is
**direction-dependent**: run it bottom-up instead of top-down and `llama_l` is alone
at the top again. Bootstrapping articles, the band count comes out 2/3/4/5/6 with
band-1 size ranging from 1 to 22 arms. Neither the original claim nor its retraction
is a property of the data; the procedure was arbitrary in both directions.

Four defects in the banding procedure, named precisely:
1. Direction dependence (above).
2. Adaptive band leader chosen post hoc from the same data, plus ~23 sequential tests
   with no multiplicity control. **Holm-corrected over all 276 pairs: zero
   significant.** Against `llama_l`, only `llama_m` survives; **`qwen_m` does not**
   (p = 0.053) — so even "qwen_m is last" is weaker than claimed.
3. Percentile bootstrap at n=20 is anti-conservative; the break at `gemma_l` has a
   sign-flip p of 0.061. BCa fixes skew, not small-n undercoverage or multiplicity.
4. In the *unpaired* variant, band width was the leader's run-to-run spread — so
   band membership depends on **provider nondeterminism**. `anthropic_s` (spread
   0.0000) could never be tied with anything; `glm_l` (0.030) ties with everything.

Within-article permutation test for any arm effect at all: p = 0.007 with all 24
arms, p = 0.083 without `qwen_m`, **p = 0.58 for the top 12**, p = 0.68 for the top 6.
The entire detectable signal is the bottom of the table.

**CORRECTION to entry 4 — the tier axis is not a size axis, in any family.** Not three
families as previously stated: *all eight*. anthropic = haiku-**4.5** / sonnet-**5** /
opus-**5**; openai = gpt-**5.4**-mini / **5.5** / **6**-sol; qwen = **3.8**-flash /
**3.7**-plus / **3**-max (the "large" is the *oldest* generation); glm = **4.5**-air /
**4.6** / **5**; mistral = small-**3.2** / medium-**3.1** / large-**2512**; llama =
4-scout / **3.3**-70b / 4-maverick; gemma = **3**-27b / 4-26b-a4b / 4-31b; deepseek =
v4-flash / v**4.1**-flash / v4-pro. The axis is *the vendor's current price tier*.
Every size-effect sentence in entry 4 is void, including "anthropic is flat across
tiers".

**CORRECTION to the length story — it cuts the other way.** Recall is a *stronger*
length artifact than F1, not the correction for it (ρ = +0.795 vs −0.400). Truncating
every output to the gold's 37 words and scoring recall: deepseek_m 1st, llama_l 2nd,
**anthropic_l 8th**, glm_s 16th; ρ(words, recall@37) falls to +0.36. So Anthropic's
"recall crown" was words, not front-loaded content, and the Pareto "flip" between F1
and recall is a flip between two opposite length artifacts — not a hidden quality in
`anthropic_l`. `llama_l` is 1st or 2nd under every variant tried.

The F1-vs-recall disagreement is nonetheless *real and defensible*: it is a genuine
disagreement about whether to reward length, and the prompt ("2-3 short sentences",
"terse") already took F1's side. The anthropic arms wrote 3.2 sentences averaging
~23 words (75 total) against a 37-word reference; openai and glm_s wrote 2.4
sentences averaging ~17 words.

**CORRECTION to an earlier session number** — the gold-vs-silver Spearman reported as
**+0.125 does not reproduce. It is +0.473** (F1 vs F1) and +0.739 (recall vs recall).
The 1.70× length inflation does reproduce exactly (36.7 → 62.4 words).

**NEW — the reasoning-off invariant is violated in one arm and unproven in two.**
This was not in any earlier finding.

- `glm_l` leaked chain-of-thought in the clear (entry 8). Reasoning was not off.
- `anthropic_l` emits **2.50 output tokens per visible word** and `anthropic_m`
  **2.14**, where every other arm — including `anthropic_s` — sits at 1.00–1.57. The
  excess is *proportional to output length*, not a fixed intercept, which is the shape
  of a hidden draft-then-final pass: the same thing glm_l did visibly.
- Consequence: the Anthropic **cost figures are ~1.7× the cost of the visible text**,
  and "what does a non-reasoning Opus score" is unanswered.
- It cannot be diagnosed from disk, because the harness does not persist raw `usage`
  (`completion_tokens_details.reasoning_tokens`) or `finish_reason`.
- **The alternative explanation is not excluded**: an Anthropic-specific tokenizer or
  proxy accounting quirk would produce the same ratio. Recording the fields settles it
  for a few cents. Until then this is an *open question*, not a finding.

**Silver provenance is unrecorded.** `references/silver/.../manifest.json` names only
an alias, `eval-claude-opus` — which is not in `model_provenance.json` (that has
`eval-opus-5`). `reference/arm_anthropic_opus.yaml` carries no `reasoning:` key, so
the request sent no reasoning field and the setting was whatever the provider
defaulted to. The earlier claim that silver was "authored with reasoning ON" is
therefore **unverified**, not established.

**Verified exactly and unchanged**: entry 6's variance decomposition, the determinism
counts, all the length correlations, the Pareto *sets*, and every fingerprint
observation in entry 5.

### 2026-09-25 · 10 — What 20 articles can actually support

The honest replacement for bands is **rank confidence intervals** from an
article-level bootstrap (5000 resamples):

```
  llama_l      P(rank 1) = 0.68    95% rank interval [ 1, 10]
  openai_l                         95% rank interval [ 1, 12]
  deepseek_s                       95% rank interval [ 2, 13]
  anthropic_l                      95% rank interval [ 3, 23]
  qwen_m                           95% rank interval [20, 24]
```

Read as: *llama_l is somewhere in the top 10, qwen_m is somewhere in the bottom 5,
and nothing else on this table is placed at all.*

**Power.** Pooled paired-delta sd among top-8 pairs = 0.0588. For 80% power at
two-sided 0.05 on **one pre-registered pair** at the observed llama_l–openai_l delta:
**n ≈ 204 articles** — and that observed delta is winner's-curse inflated
(leave-one-article-out moves it between 0.005 and 0.019), so 204 is a *lower bound*.
At n=200 the minimum detectable effect is 0.012 for a single pair and **0.019 with
Bonferroni over 276 pairs — larger than the entire top-6 range of 0.018.** A ranked
top-6 needs n in the low thousands.

**Repeats were the wrong dimension to spend on.** For the same 1440 calls,
n=60/r=1 gives sd(delta) **0.0090** against n=20/r=3 at **0.0133**. The within-cell
component (0.031) is smaller than the interaction (0.038), and three arms are close
to deterministic, making their repeats pseudo-replicates carrying no information.

**CORRECTION to a cost estimate I gave**: "~$20 for 200 articles" was 4× high. The
whole 72-run sweep cost **$1.445**. n=200/r=1 ≈ **$4.80**; n=1000/r=1 ≈ **$24**
(~18 h sequential, ~1 h parallelised per arm).

### 2026-09-25 · 11 — OPEN: what the quality facets should be

The current pair (rougeL F1 + grounding) disagree partly for a length reason. The
proposed replacement keeps everything computable with `rouge-score` plus ~20 lines of
stdlib — no GPU, no paid API — because this is a teaching example:

- **Coverage** — rouge2 or rougeL **recall on the first 37 words**. One line to
  explain; length-controlled by construction; ρ(words) falls to +0.29.
- **Concision** — rougeL **precision**, or a length-adherence facet |log(words/37)|
  tied explicitly to the prompt's "2-3 short sentences".
- These two disagree **by design** — that is the summarisation trade-off, and the
  README should say so rather than implying the facets are independent.
- **Grounding**: keep, but state that it is not length-neutral (ρ(words) = +0.25,
  ρ(recall) = +0.48).
- Print **words** beside every quality column.
- Drop one of rouge2 / rougeL F — they correlate at 0.83 and do not disagree.
- If an LCS metric is kept on multi-sentence text, **`rougeLsum`** is the CNN/DM
  convention, not `rougeL`.
- Add a **format-compliance descriptive** (newline / markdown / leak detector) so
  entry-8-type claims are computed rather than read.
- Multiple references are not available for CNN/DM without paying. Truncated recall
  is the cheap version of the same idea.

### 2026-09-25 · 12 — OPEN: silver

Position reached before the review: stop assuming the most expensive model is the
ceiling, put Opus into the arms as a normal arm (done — it is `anthropic_l`), and
then choose silver from the results **on quality alone**, no cost or speed angle, as
a proxy for gold.

The review argues the concept is the wrong tool for *this* example:

- Silver F1 ranks `anthropic_l` **1st**, where gold ranks it 13th — the circularity
  that `reference/README.md` currently claims "does not bite in THIS example". It
  bites the moment silver is used to score.
- "Choose silver on quality alone" is circular: you need a quality ordering to pick
  the author, and the author then defines the ordering.
- With no single quality ordering (entry 9), the choice is arbitrary, and silver's
  1.70× length rewards whichever arm writes long.
- Proposal: keep silver as a one-paragraph **exhibit of the circularity**, never as a
  scoring target here. If a future example has no gold, silver must be authored by a
  model **excluded from the arms**, with params, prompt sha and reasoning recorded in
  its manifest — none of which the current manifest does.

**Not yet decided.**

### 2026-09-25 · 13 — OPEN: proposed next steps, not started

Teaching-example work (the repo's actual purpose), all $0:

1. Replace band logic in the leaderboard with **rank intervals + a global test**.
   Answers "what can 20 articles support?" honestly; this is the transferable lesson.
2. **Rename tier → price tier**, delete every size claim.
3. **Persist raw `usage`, `finish_reason`, reasoning-token counts**; add the
   format-compliance detector; fix `model.id` to record the upstream model; record
   params + prompt sha in the silver manifest. This is what makes "was reasoning
   actually off?" answerable.
4. Rebuild the **metric facets** per entry 11, with the coverage/concision trade-off
   stated in prose.
5. Demote **silver** to the circularity exhibit.

Experiment work:

6. Rerun at **n=200 / r=1** *after* step 3 — ~$4.80, ~4 h sequential — so the
   Anthropic token anomaly is diagnosable and the glm_l leak is counted.
7. n=1000 / r=1 only if a ranked top-6 is a stated goal (~$24). Advisor's
   recommendation is *not* to: the deltas it would resolve are output-length policy.

Still untouched at the time of writing: all of the above.

### 2026-09-25 · 14 — Reasoning contamination, scanned over all 1440 outputs

Entry 9 raised this from token accounting. Now computed over every output rather than
inferred. Two *different* failures, previously conflated:

```
arm              n  CoT label bullet tok/word
anthropic_l     60    0     0      0     2.24   <-- high
anthropic_m     60    0     0      0     2.21   <-- high
anthropic_s     60    0     0      0     1.42
glm_l           60    4     0      3     1.29   <== visible leak
mistral_l       60    0    48      0     1.47
mistral_s       60    0     7      0     1.41
(the other 18)        0     0      0  1.27–1.37
```

**Failure A — visible narration (`glm_l`).** 4 outputs across 3 articles carry the
model's process in the *output text* ("The user wants a 2-3 sentence news wire style
summary... Let me extract the key facts:"), 128–215 words, rougeL 0.102–0.184. But
glm_l's token/word ratio is **1.29 — normal**. It was not billed for hidden thinking;
it disobeyed *"Output only the summary."* That is an instruction-following failure,
not a reasoning-flag failure. Excluding the 4 rows: 0.2375 → **0.2442** (+0.0067).

**Failure B — hidden tokens (`anthropic_l`, `anthropic_m`).** No visible contamination
whatsoever, yet billed at 2.24 / 2.21 tokens per visible word against a field at
1.27–1.47. The discriminating observation is **`anthropic_s` at 1.42** — same vendor,
same proxy, same route, in line with everyone else. A tokenizer or proxy-accounting
quirk should affect haiku too. This is now evidence *for* hidden reasoning tokens on
opus-5 and sonnet-5 that `reasoning: {enabled: false}` did not suppress, though it
remains inference: the raw `usage` object is not persisted, so the reasoning-token
count cannot be read from disk.

**`mistral_l`**: 48/60 outputs open with a markdown bold label. Cosmetic — stripping
it moves the score 0.0008.

**OPEN — can reasoning actually be turned off?** Unanswered. Needs a ~$0.20 probe on
opus-5 / sonnet-5 / glm-5: one article each under `reasoning: {enabled: false}`, then
`reasoning_effort` variants, then no reasoning field at all, comparing the raw `usage`
each time. Blocked on persisting `usage` first. **If a model cannot run without
reasoning, it does not belong in a reasoning-off comparison** — the same rule already
applied to opus-5.5 and qwen3.8-max, and it would mean dropping opus-5/sonnet-5 rather
than keeping contaminated arms.

### 2026-09-25 · 15 — The pattern behind the wrong findings

Four of the six corrections in entries 7–9 share one cause: **a claim was made from a
sample or by eye, where computing over everything was available and free.**

- 5 outputs read → "no format problems" (65 of 1440 had them).
- Bands walked in one direction → an ordering claim (the other direction reverses it).
- Length intuition → "recall corrects for it" (recall is the worse artifact).
- A frontier read off one facet → "hidden quality in anthropic_l" (a length artifact).

**DECISION — if it can be computed over the whole corpus, it is not reported from a
sample.** Format compliance becomes a metric rather than an observation; ordering
claims come from rank intervals rather than a walk; every length claim is checked
against a length-controlled variant before it is written down.

### 2026-09-25 · 16 — Consolidated fix plan (nothing started)

**Tier 1 — instrumentation; gates the reasoning diagnosis. $0, no API calls.**
1. Persist raw `usage` (incl. `completion_tokens_details.reasoning_tokens`) and
   `finish_reason` per call. Everything about failure B depends on this.
2. Record the upstream model id and revision, not the LiteLLM alias.
3. Fix `model.declared` — a boolean wearing a value's name.
4. Reconcile `build.dirty` vs `instrument.harness.dirty`; make a dirty tree loud at
   run time instead of a silent field.
5. Record params + prompt sha + reasoning in the silver manifest.

**Tier 2 — scoring; makes claims computed rather than eyeballed. $0.**
6. Format-compliance (CoT / label / bullet) as a real metric inside `score()`.
7. Rank intervals + a global test, replacing band logic entirely.
8. Length-controlled facets: coverage = recall@37, concision = precision. Drop one of
   rouge2/rougeL (ρ = 0.83, they do not disagree). Use `rougeLsum`, the CNN/DM
   convention for multi-sentence text.

**Tier 3 — naming. $0.**
9. `tier` → `price_tier`; delete every size claim from configs and docs.

**Tier 4 — experiments; after tiers 1–2.**
10. Reasoning-off probe, ~$0.20 — answers the entry-14 open question.
11. Per its result: rerun with reasoning genuinely off, or drop the affected arms and
    say why.
12. Rerun at n=200 / r=1, ~$4.80.

Still untouched: all twelve.

### 2026-09-25 · 17 — DECISION: n stays at 20. Scaling is off the table.

Not "later", not "when it's cheap" — out of scope. The 20-article experiment gets
made correct instead of made bigger.

**What this gives up**, stated plainly: any ranking of the top 12 arms. Entry 10's
power numbers are unambiguous — at n=20 the minimum detectable effect exceeds the
entire top-6 range, so no amount of better statistics extracts an ordering that is
not there. Entries 4, 7 and 9 were all attempts to do exactly that.

**What this buys.** The example stops being a leaderboard and becomes a demonstration
of *what a small eval can and cannot tell you* — which is the rarer and more useful
lesson, and the thing the harness was built to enforce. The headline result is no
longer "model X won"; it is:

> Across all 24 arms there is a detectable arm effect (within-article permutation
> p = 0.007). Restricted to the top 12 arms, there is not (p = 0.58). Rank intervals:
> `llama_l` [1, 10], `qwen_m` [20, 24], everything else unplaced.

That is a true, complete, reportable finding at n=20, and it needs no more data.

**Consequences for the plan in entry 16:** items 11 and 12 (rerun at n=200, and the
n=1000 option) are **dropped**. Re-running only the reasoning-contaminated arms at
n=20/r=3 costs ~$0.30, so item 10's follow-up stays affordable. Ten items remain,
nine of them free.

**Still open**: whether REPEAT stays at 3. Entry 10 showed repeats were the wrong
place to spend *when articles were on the table*. With n fixed at 20 they are the
only replication available, and entry 6 showed 11 of 24 arms are fully
non-deterministic — so r=3 now earns its place for a different reason than it was
originally chosen for.

### 2026-09-25 · 18 — DECISION: how we compare. Friedman + Nemenyi, no walking.

The band-walk is deleted, on the grounds that it is a sequential pairwise algorithm
whose answer depends on traversal order — closer to a bubble sort than to a
comparison. Replaced with three order-independent readings (detail in `EVAL_PLAN.md`
Part 5): Friedman as the gate, Nemenyi critical difference across all pairs at once,
bootstrap rank intervals for reporting.

Results on the existing 72 runs, rougeL:

```
  Friedman permutation p = 0.0316      -> an arm effect exists
  Nemenyi CD = 8.13 rank positions;  observed span = 7.85
  pairs separated: 0 of 276
```

The best-to-worst spread of the whole table is smaller than the distance needed to
separate any single pair.

**Rank intervals disagree, and we report the conservative reading.** `llama_l` [1, 11]
and `qwen_m` [20, 24] do not overlap, which looks like separation — but those are
marginal intervals, while Nemenyi is simultaneous across all 276 pairs. Reported
conclusion: **nothing is separated.** The intervals are shown as context, never as
evidence.

**A lever was tried and failed, which is the useful part.** Nemenyi's threshold shrinks
as you compare fewer arms, so a pre-registered subset should buy power for free:

```
  24 arms  CD 8.13  span 7.85   0/276
   8 arms  CD 2.35  span 2.15   0/28
   4 arms  CD 1.05  span 1.00   0/6
   2 arms  CD 0.44  span 0.20   0/1    <- best vs worst, head to head
```

It fails at every size, **including two arms with no multiplicity penalty at all**. So
the indistinguishability is not an artifact of testing too many things; at n=20 on
rougeL these models are genuinely not separable. Combined with entry 17, this makes the
example's headline finding complete and final: *there is an effect, and this experiment
cannot attribute it to any pair.*

### 2026-09-25 · 19 — DECISION: smoke subsets for validating harness changes

Re-running 24 arms to check a code change is wasteful. Two named subsets:

- **`smoke`** — `qwen_s`, `glm_s`, `gemma_m`, `mistral_s`: ~$0.005 per pass at r=1.
  Plumbing only.
- **`smoke-reasoning`** — `anthropic_l`, `anthropic_m`, `anthropic_s`, `glm_l`: ~$0.35.
  The two hidden-token suspects, the deterministic Anthropic control, and the visible
  leaker.

Full 24-arm sweep (~$1.45 at r=3) only once the harness is settled. Execution order
and the per-step check are in `EVAL_PLAN.md` Part 6.

### 2026-09-25 · 20 — A1 DONE. And it refutes entry 14's "Failure B".

`Result` gained a `meta` field on both the generic harness and this example's adapter;
raw `usage`, `finish_reason`, `response_model` and `system_fingerprint` are now stored
per prediction under a `_`-prefixed key that the metric aggregation skips.
`reasoning_tokens` is promoted to a first-class **descriptive metric**, so a
contaminated arm is visible in the table rather than in a file someone has to think to
open. `EVAL_RUNS_DIR` was added so a smoke pass cannot add repeats to a real sweep's
arms and silently move numbers already reported.

**CORRECTION to entry 14, Failure B — there was no hidden reasoning.** Measured on
`smoke-reasoning` (anthropic_l, anthropic_m, anthropic_s, glm_l at r=1, ~$0.34):

```
anthropic_l   tokens_out=147  words=69  ratio=2.13  completion_tokens_details.reasoning_tokens = 0
anthropic_m   tokens_out=138  words=64  ratio=2.16  reasoning_tokens = 0
anthropic_s   tokens_out= 92  words=64  ratio=1.44  reasoning_tokens = 0
glm_l         tokens_out= 61  words=50  ratio=1.22  reasoning_tokens = 0
```

The key point is that `"reasoning_tokens": 0` is **explicitly present** in the response
body, not absent — the provider is affirmatively reporting zero, not staying silent.
`reasoning: {enabled: false}` did what it claimed. The inference in entry 14 was wrong:
a token/word ratio is not evidence of reasoning, and I treated it as such because it
was the only number available before `usage` was persisted.

The 2.13 / 2.16 versus 1.44 ratio **within the same vendor** remains unexplained. It is
an accounting or tokenizer difference of some kind; what matters here is that it is not
reasoning, so it is not contamination, and the Anthropic arms were held to the same
condition as everything else. The claim "Anthropic cost figures are ~1.7x the cost of
the visible text" is withdrawn — the tokens are billed, but not for hidden thinking.

**What remains of the reasoning problem**: only `glm_l`'s intermittent refusal to obey
"Output only the summary" (4 of 60 outputs, entry 14 Failure A). That is an
instruction-following failure, caught by B1's format-compliance metric, not a
reasoning-flag failure. Phase D shrinks to nothing: there is no reasoning to turn off.

**A bug I introduced and caught in the same pass**: `float(reasoning_tokens or 0)`
collapsed *unreported* into *measured zero* — writing a confident 0.0 where the truth
was "we do not know", in the very field whose docstring says those are different
claims. Fixed: the metric is recorded only when the provider reports it, absent
otherwise (prints as `--`), with `reasoning_tokens_reported` in `_meta` carrying the
distinction.

**Incidental finding, not acted on**: the provider returns `usage.cost` and
`cost_details` — the real upstream price of each call. Our cost axis currently uses
prices hand-declared in the configs. The provider's own number is better ground truth
and is now captured in `_meta` for free.

**Also learned**: `response_model` comes back as our own alias (`eval-gemma-26b`), so
A2 cannot be solved by reading the response — it needs the proxy's `/model/info`.

### 2026-09-25 · 21 — Phase A complete. `make ci: green`.

**A2 — the fingerprint records the upstream model, not our alias.** `fingerprint()`
resolves the alias through the proxy's `/model/info` once per process and records
`id` = the upstream model, `alias` = what the config asked for, and `id_source` =
`proxy-model-info` or `alias-unresolved`. Verified both ways:

```
  BEFORE  id='eval-qwen-flash'                 hash=800994a1700f7e2f
  AFTER   id='openrouter/qwen/qwen3.8-flash'   hash=bf87b733cd52c1a3     hash changed: True
  proxy unreachable ->  id='eval-qwen-flash'  id_source='alias-unresolved'
```

The upstream id now participates in the hash, so re-pointing an alias changes the
fingerprint — the failure in entry 5 is closed. An unreachable proxy degrades to a
stated absence rather than a silent claim.

**A3 — `declared` renamed to `identity_declared`.** It is a flag ("did the adapter tell
us what its system under test is"), not the identity, and it read like a value. Two
self-test assertions consumed the old key and were updated with it.

**A4 — one honest dirty flag, and it is loud now.** `build.dirty` was hardcoded `False`
whenever `EVAL_BUILD_REF` was set — asserting "built from a clean tree" about a string
handed over by an environment variable, on no evidence, in the same record as
`instrument.harness.dirty: true`. Now `None`, which is the truth. And
`experiment_run.py` prints a warning at the top of a run when the harness tree is
dirty: a field nobody reads is not a warning, and all 72 runs of the sweep carried
`dirty: true` with nothing saying so until they were audited afterwards.

**A5 — reference provenance, and a home-path leak fixed at source.**
`reference_create.py` now records the adapter path **repo-relative**, the full
`system_under_test` identity from the same hook a run uses, and the params
(temperature, max_tokens, reasoning, prompt_file, provider). The existing silver
manifest had its absolute path corrected and carries an explicit
`provenance_incomplete` note listing what was never recorded — the upstream model
behind `eval-claude-opus` (that alias no longer resolves, so it is unrecoverable),
temperature, reasoning, prompt sha. **None of it was guessed.**

**The bigger half of A5 was a bug the self-test found in my own work.**
`experiment_run.py` wrote an ABSOLUTE adapter path into every `metrics.json` and hashed
it into every fingerprint. Cause: it tried `path.relative_to(ROOT)` on an *unresolved*
path, and adapters live in sibling example directories — `configs/../adapter.py` is not
under the harness root — so the match never succeeded and every run silently fell back
to the absolute path. Fixed in `_portable_id`: resolve first, widen the base one level
for siblings, and fall back to the last two path components rather than ever emit a
home path. A fresh run now records `summarization-cnn-dailymail/adapter.py`.

**And a defect in the test itself.** `no home path in committed data/` rglob'd the whole
working tree, so it failed on `data/runs/` — a **gitignored** directory whose contents
can never be committed. It now lists tracked files via `git ls-files`, which is what
"committed" means. This is a scope correction, not a suppression: the cause is fixed at
source, and the check was **mutation-tested** — a planted tracked file containing a home
path still fails it (`offenders: ['data/references/_leak_probe.json']`), and the probe
was removed afterwards.

**Verified on a fresh run, and `make ci` is green:**

```
  model.id          : openrouter/google/gemma-4-26b-a4b-it
  model.alias       : eval-gemma-26b
  id_source         : proxy-model-info
  identity_declared : True
  adapter id        : summarization-cnn-dailymail/adapter.py
  build.dirty       : None          harness.dirty : True (warned)
  home path leak    : False
  reasoning_tokens  : 0.0  | reported: True     finish_reason : stop

  check: tree valid, self-tests pass
  ci: green
```

**One trap worth recording**: `EVAL_RUNS_DIR` redirects validation too, so running
`make ci` with it still exported reported a broken baseline (`smoke_v1_baseline.json ->
demo_v1_...`) that is not broken. Unset it before validating.

Phase A spend: **~$0.35** total, all of it the `smoke-reasoning` pass. The 72 real runs
are untouched.

### 2026-09-25 · 22 — Phase B complete. `make ci: green`.

**B1 — format compliance is a metric now.** `fmt_narration`, `fmt_label`, `fmt_bullets`,
computed inside `score()` on every output, before the reference check so an arm scored
without ground truth still reports whether it obeyed the prompt. Validated by rescoring
all 1440 existing outputs offline against counts established independently in entry 14:

```
  glm_l      expected (4 narration, 0 label, 3 bullets)  got (4, 0, 3)   OK
  mistral_l  expected (0, 48, 0)                         got (0, 48, 0)  OK
  mistral_s  expected (0,  7, 0)                         got (0,  7, 0)  OK
  every other arm clean                                                  OK
```

62 flag instances over 1440 outputs (fewer distinct outputs — a narrated output can also
carry bullets). Entry 8's failure mode is now impossible to repeat by accident.

**B2 — coverage and concision, and they are genuinely independent.**

*Changed from the plan*: instead of a fixed 37-word budget, each output is truncated to
**that item's own reference length**. Self-calibrating, so it stays correct on a dataset
whose references vary in length, which a hardcoded constant would not.

- **coverage** = rougeLsum *recall* of the output clipped to the reference's word count.
  Every arm judged on the same budget the human used, so length cannot buy coverage —
  only putting the important thing first can.
- **concision** = rougeLsum *precision* over the whole output. Padding is punished here
  exactly as raw recall rewards it.
- `rougeL` → **`rougeLsum`** (per-sentence LCS; the CNN/DailyMail convention, so our
  numbers are comparable to published ones). `rouge2` dropped — ρ 0.83 with the LCS
  metric, so it never disagreed, and a facet that always agrees is not a facet.

```
  rho(words, coverage )  = +0.357     (raw recall was +0.795)
  rho(words, concision)  = -0.845     (by design: it IS precision)
  rho(coverage, concision) = +0.009   <- orthogonal, not opposed-by-artifact
```

`gemma_l` is 21st on coverage and 5th on concision; `anthropic_m` 3rd and 20th. A real
trade-off a reader has to decide about.

**NOT fixed**: coverage is *not* length-neutral, only much less length-driven. +0.357
residual. Part of it is structural — an arm writing fewer words than the reference is
never truncated, so short arms are judged on less text than long ones. Not claimed as
solved.

**B3 — Friedman + Nemenyi + rank intervals replace the band walk, in the harness.** The
leaderboard now reads `predictions.jsonl`, builds the arm × item matrix, and prints the
global test *before* anything else. Reproduces the standalone analysis exactly:

```
  IS THE ORDERING REAL?   metric=rougeL  k=24 arms  N=20 items
    global test (permutation on within-item ranks): p = 0.0316 -> an arm effect exists
    Nemenyi critical difference = 8.13 rank positions; observed span = 7.85
    pairs distinguishable: 0 of 276
    An effect exists, but NO PAIR is distinguishable once all comparisons are
    accounted for. 'Which arm is better than which' has no answer here.
```

Rank intervals are printed as *context*, with the output saying in as many words that
they are marginal and not a pairwise claim.

**B4 — the Pareto frontier, which the leaderboard never had.** Dominated arms (worse on
quality *and* cost *and* speed than some other arm) are named and set aside. The output
always states which quality facet produced it, because swapping the facet once produced
a completely different frontier from the same runs.

**A fifth thing, not on the plan, from watching the first smoke run.** The leaderboard
defaulted to the alphabetically-first quality metric — which for `coverage`/`concision`
is **concision**, silently promoting brevity to the headline. Same shape as the accident
that once ranked a sweep by `compression`. Adapters now declare `PRIMARY_METRIC`;
this example declares `coverage`; explicit `--sort` still wins.

**The most interesting result of the phase was an accident of that fix.** The same four
smoke arms, same items, two facets:

```
  sorted by concision:  p = 0.0024   span 1.45   2 of 6 pairs distinguishable
  sorted by coverage :  p = 0.9276   span 0.25   0 of 6 pairs distinguishable
```

These four cheap models differ **measurably in terseness and not at all in content
coverage**. Which facet you pick decides whether this experiment sees an effect at all —
the clearest possible demonstration of why one quality number is a lie, and it fell out
of a 4-arm, half-cent smoke run.

Phase B spend: **~$0.01** (two smoke passes). No sweep re-run; B1–B4 were validated by
rescoring artifacts already on disk.

### 2026-09-25 · 23 — Phase C complete. `tier` is now `price_tier`.

All 24 configs renamed, and each one now carries the reason inline rather than in a
document nobody opens beside the config:

> this field is the vendor's own small/mid/large product step, which is a PRICE ladder.
> It was called `tier` and read as model size, and that was wrong in every family — the
> three arms differ in generation as well as price. qwen's "large" is the OLDEST
> generation of the three. So this experiment cannot attribute a difference between
> tiers to size, and no conclusion here should try.

A second benefit that was not the point: `tier` collided conceptually with
`reference_tier` (gold/silver), which is an unrelated axis. `price_tier` removes the
ambiguity.

Verified: `price_tier` reaches `fingerprint.arm.params`, so a run records which rung of
the price ladder it was on, and the size claims retracted in entry 9 cannot be
reconstructed by accident from the field name.

### 2026-09-25 · 24 — Phase D is already finished, by Phase A.

D1 was a ~$0.20 probe to find out whether reasoning could be turned off. A1 answered it
for free (entry 20): the provider reports `reasoning_tokens: 0` explicitly on every arm,
so `reasoning: {enabled: false}` was honoured throughout and there was never anything to
turn off. D2 (drop models that cannot comply) therefore has no candidates.

D3 survives in a changed form. `glm_l` narrated its reasoning into the visible output on
4 of 60 items — an instruction-following failure, not a reasoning-flag failure — and
B1's `fmt_narration` now flags exactly those 4. They no longer need to be found by hand
or excluded by hand: any future run reports them as a metric, and an arm with
`fmt_narration > 0` has a quality column that is partly measuring something that is not
a summary.

**Remaining plan: the two steps that cost money.**

- Re-run the 24 arms on the new facets (~$1.45, r=3). Nothing on disk carries
  `coverage`, `concision`, `rougeLsum` or the format flags — those are computed at score
  time, so the existing 72 runs cannot be upgraded in place. Everything in Phases B and
  C was validated by rescoring their OUTPUTS offline, which is why none of it needed a
  sweep; but a leaderboard built from stored metrics needs stored metrics.
- Silver calibration (~$1.00, entry 12 / plan Part 3): author silver with three
  different authors, score all 24 arms against each, and measure how well each silver
  ranking reproduces the gold ranking. This is the experiment that tests whether silver
  is a usable proxy at all — which matters most for the case where gold does not exist.

### 2026-09-25 · 25 — The example adapter had NO retry logic. Two arms died of it.

`EVAL_MAX_RETRIES` is documented, and the harness's **bundled demo** adapter honours it.
The summarisation example defines its **own** adapter, and that one had no retry code at
all. So the knob looked wired up, raising it did nothing, and every one of ~1440 calls
was a single attempt. Two sweeps each lost a whole arm to one upstream 429:
`mistral_mixtral` in the 18-arm sweep, `mistral_l` in v2 — roughly 20 paid calls
discarded each time, reported as `ARM FAILED` as though the model could not do the task.

**I compounded it.** I twice announced I was re-running `mistral_l` "with more retries";
both times `EVAL_MAX_RETRIES=8` was a no-op. The first of those two attempts never even
started — I wrapped it in `until ! pgrep -f 'scripts/sweep.py'`, a pattern that matches
the waiting shell's **own** command line, so it waited on itself for 23 minutes; and I
piped it through `tail`, which buffers until exit, so the log stayed empty and hid it.
Then I told Marko the arm might be unrunnable. It was not. Once retries actually existed
it succeeded **in 13 seconds**, and the full 3-repeat arm needed **exactly one retry**.

**CORRECTION to what I said about providers.** "`mistral-large-2512` has one provider,
so there is nowhere to fall back to" is wrong in the detail that matters: it has **two
endpoints** — `mistral/zdr` and `mistral/eu` — both operated by Mistral but separately
routable. There is somewhere to fall back to.

**v2 is now complete: 24 arms, 72 runs.**

### 2026-09-25 · 26 — Retries move into the core, where they should have been

`scripts/_retry.py`. The harness wraps **both** `call_system` and `warmup`, so every
adapter gets retries by existing rather than by remembering to copy twenty lines — which
is the whole lesson: this was infrastructure sitting in a place where each new example
would have to reinvent it, and the second example would have hit the same wall.

- attempts: `EVAL_MAX_RETRIES` (default 8); delay cap: `EVAL_RETRY_MAX_DELAY` (default 60s)
- backoff doubles — 1, 2, 4, 8, 16, 32 … — then **flattens at the cap**, so the wait
  grows quickly while a blip is plausible and then stops growing
- jitter, so N arms recovering from one upstream hiccup do not return in lockstep and
  cause the next one
- **`FATAL` is checked before `TRANSIENT`**, so `"401 invalid api key, please try again
  later"` is raised at once rather than retried eight times for the word "again"
- `SystemExit` is never retried: the harness raises it for "your key is not set", which
  is an instruction to the operator, not weather
- adapters may **add** markers via `TRANSIENT_MARKERS` (a local runtime's "model is
  warming up"), never shrink the core's list
- `sleep` is injectable, so the tests run instantly — a retry policy with slow tests is
  a retry policy nobody runs

The example adapter's copy is deleted; it now only *declares* its extra markers. Eight
assertions added to `make ci`, including the 401-that-says-try-again trap.

### 2026-09-25 · 27 — Which machine ran it is now part of the record

Raised by Marko: over time, differences may come from the infra rather than the model,
and we could not tell. He is right, and it is not a Mistral problem — it is every
open-weight arm:

```
  meta-llama/llama-4-maverick      5 providers (DeepInfra, DigitalOcean, Google, Novita, Parasail)
  mistralai/mistral-small-3.2-24b  4 providers (DeepInfra, Mistral, Parasail, Venice)
  mistralai/mistral-large-2512     2 endpoints (Mistral zdr, Mistral eu)
```

A gateway load-balances between these silently, and two hosts can serve the same weights
at different quantisations. Across 141 runs, **nothing recorded which host answered** —
an uncontrolled variable underneath an experiment whose entire claim is "only the model
varied".

It was recoverable all along: OpenRouter returns `provider` as a non-standard field that
the OpenAI SDK keeps in `model_extra`. The proxy rewrites `model` to our own alias, so
the response otherwise says nothing about it.

Recorded in two places, deliberately kept apart:

- **fingerprint** → `provider_routing`: the policy we ASKED for. Knowable before the run.
- **run record** → `providers_seen`: the hosts that actually ANSWERED, counted across the
  20 items. Knowable only afterwards. An arm served by two hosts has its 20 items
  produced by two systems and its mean mixes them — the confound the fingerprint exists
  to rule out, happening one level below where the fingerprint could see it.

Verified: `providers_seen: {'Alibaba': 20}` on a smoke run of `qwen_s`.

**Not retroactive.** The 72 v2 runs carry no provider data; the adapter changed after
they finished. From the next sweep onward.

### 2026-09-25 · 28 — DECISION: version the arms to v2 rather than delete v1's runs

The scorer changed and the configs changed, so v1 and v2 runs are not repeats of one
another: v1 carries rougeL/rouge2, v2 carries coverage/concision/rougeLsum and the
format flags. Grouped under one `config_id` the leaderboard would average each metric
over whichever runs happened to carry it — one row whose columns have different n,
presented as one arm.

**The alternative considered and rejected was deleting v1's runs so the table would be
24 rows instead of 48.** That is exactly what destroyed 18 arms of paid results earlier
today (entry 3): rename the ids, then delete what no longer matches so the output looks
clean. Instead: v1's runs stay untouched, configs go to `_v2`, and `leaderboard.py`
gained `--match` to scope the view. Scoping a table is a display problem; deleting data
is not a solution to a display problem.

### 2026-09-25 · 29 — v2 results. Controlling for length may erase the arm effect.

24 arms, 72 runs, complete (`mistral_l` recovered — entry 25). Ranked by `coverage`:

```
  IS THE ORDERING REAL?   metric=coverage  k=23 arms*  N=20 items
    global test (permutation on within-item ranks): p = 0.1260 -> NO detectable arm effect
    Nemenyi critical difference = 7.76 rank positions; observed span = 6.92
    pairs distinguishable: 0 of 253
```
\* computed before `mistral_l` landed; k=24 not yet recomputed.

Against v1 scored by `rougeL`: p = 0.0316, "an arm effect exists", 0 of 276 pairs
separated. So the *global* effect that was detectable on rougeL is not detectable on
coverage, while the pairwise answer is unchanged — nothing is distinguishable either way.

The ordering also scrambles: `anthropic_m` 14th on rougeL → **1st** on coverage; `glm_s`
4th → 20th; `openai_l` 2nd → 13th. Which is what you would expect if the old ranking was
substantially reading how much each model wrote.

**The tempting claim is "the rougeL arm effect was a length effect; control for length
and it disappears." I do not trust it yet, and it is under external review.** v1→v2
changed TWO things at once: the metric AND the sample. These are different API calls
against a system where only 11% of outputs repeat byte-identically (entry 6), so a
p-value moving 0.03 → 0.13 could be run-to-run variation rather than the metric working.
The disentangling test costs nothing and is on disk — score v1's stored outputs with the
v2 scorer and v2's with the v1 metric, and compare all four cells. Until that is done
this is a hypothesis, not a finding.

**What the new metrics caught on their own, with no hand-scanning:**

- `glm_l`: `fmt_narration` 0.0667 (4/60) and `fmt_bullets` 0.05 (3/60) — matching its v1
  behaviour almost exactly. Its chain-of-thought leak is a stable property of that arm,
  not a one-off.
- `mistral_s`: `fmt_bullets` 0.10 (6/60).

**Cost of v2**: ~$1.45 for the sweep plus ~$0.05 for the `mistral_l` recovery.

### 2026-09-25 · 30 — Entry 29's footnote closed: k=24 recomputed

Entry 29 reported the v2 global test at k=23, before `mistral_l` landed. At the full 24
arms:

```
  metric=coverage  k=24 arms  N=20 items
    global test: p = 0.1378  ->  NO detectable arm effect
    Nemenyi critical difference = 8.13;  observed span = 7.20
    pairs distinguishable: 0 of 276
```

Unchanged in substance from the k=23 figure (p = 0.1260): adding the 24th arm moves the
p-value slightly and the conclusion not at all. Directly comparable to v1/rougeL now,
which had the same k and N: **CD 8.13 vs span 7.85 there, 8.13 vs 7.20 here.** The
observed span shrank under the length-controlled metric — the arms are closer together
on coverage than they were on rougeL — which is the shape the length hypothesis predicts
but is still not evidence for it while the metric and the sample both changed at once.
The four-cell test in entry 29 remains the thing that would settle it.

### 2026-09-25 · 31 — `rougeLsum` was `rougeL`. The scorer never split a sentence.

Found by external review. `rouge_score` splits text for `rougeLsum` on `"\n"` **only**
(`rouge_scorer.py:143`, `split_summaries=False` by default). Our gold references contain
**zero newlines** — verified: `gold refs containing a newline: 0 of 20`. So:

```
  rougeL == rougeLsum on 1435 of 1440 v2 outputs
  coverage's clip did " ".join(output.split()[:budget])  -> strips every newline
```

Sentence-level LCS never ran once. Entry 22's claim that this was "the CNN/DailyMail
convention, so our numbers are comparable to published ones" is **false in effect**:
published rougeLsum uses newline-separated highlights. The rename was cosmetic and I
asserted the benefit without checking that gold had sentence boundaries at all.

Fix: `split_summaries=True`, plus `_clip_words()` which clips on word count while keeping
the original whitespace, so structure survives into the scorer. Demonstrated on a
reordered-sentence pair: rougeL 0.6000 / rougeLsum **0.6000** before, 0.6000 / **1.0000**
after.

Second defect, same review: `_significance` detected ties by **exact equality** on means
of 6-decimal stored values, so genuinely tied arms differing by float noise were strictly
ordered. Fixed with a `1e-9` tolerance (328 -> 339 tied within-item pairs). A looser
tolerance was rejected: stored scores are 6-decimal, so a mean of 3 repeats has real
granularity 3.3e-7, and 5e-7 would merge differences that are real. Score precision
raised 6 -> 10 decimals so the question stops arising.

### 2026-09-25 · 32 — RETRACTION: "nothing is distinguishable at n=20" was the scorer

Both sweeps rescored from stored outputs with the fixed scorer:

```
                          v1 outputs                 v2 outputs
  coverage      p=0.0156    1 of 276 pairs   p=0.0066    1 of 276 pairs
  concision     p=0.0002   22 of 276 pairs   p=0.0002   35 of 276 pairs
  rouge1        p=0.0002    3 of 276 pairs   p=0.0002    5 of 276 pairs
  rougeLsum     p=0.0034    2 of 276 pairs   p=0.0002    9 of 276 pairs

  BEFORE:  v1 rougeL p=0.0316 0 of 276   |   v2 coverage p=0.1306 0 of 276
```

**Retracted, all of them mine:**

- *"At n=20 these models are genuinely indistinguishable — as 24, as 8, as 4, as 2"*
  (entries 17, 18). False. Up to **35 pairs** separate on concision. The lever I tested
  and reported as failed (fewer arms) was not the lever; the scorer was.
- *"The arm effect visible on rougeL was substantially a length effect; control for
  length and it disappears"* (entry 29). False on every cell. The length-controlled
  metric detects the effect in both sweeps.
- *"An effect exists and no pair is distinguishable"* (entry 18) — was true only of a
  broken metric.

**The two sweeps now agree.** The 0.0316-vs-0.1306 disagreement I attributed to sampling
was the broken metric; v1 and v2 give the same verdict on all four measures.

**What survives, and is now better supported**: `concision` carries the most arm signal
(22 and 35 pairs, p=0.0002 in both), and `coverage` the least (1 pair) — coverage is
coarse, with many exact within-item ties. The facets still disagree; the disagreement is
now about which is the more *sensitive* measure, not about which length artifact you pick.

**The cost of this**: entry 17's decision to stay at n=20 was taken partly because I told
Marko nothing could be separated at any n. That advice was wrong. The decision happens to
survive — n=20 *does* separate arms once the metric works — but it was made on a false
premise.

### 2026-09-25 · 33 — Rescoring from stored outputs, so a metric change costs $0

`scripts/rescore.py` + `make rescore DATASET_ID=... MATCH=... OUT=...`.

Scores were only ever computed at run time, so every change to a metric meant re-running
the sweep: ~$1.45 and 80 minutes to answer "what would this look like measured
differently". That is why the `rougeLsum` defect survived two sweeps — checking it would
have cost another one. The outputs are the expensive part; the scores are arithmetic over
them.

Rescored runs go to a **separate directory**, never over the originals: the originals are
the record of what was measured and paid for, and a rescored run under the same
`config_id` would average two different metrics into one row. `EVAL_RUNS_DIR` points the
leaderboard at them. Each carries `rescored_from`, `rescored_at` and the scorer's sha256,
so a rescored run can never be mistaken for a measured one.

**A bug caught while testing it**: the first version carried a fixed list of fields across
(`latency_ms`, `tokens_in`, `tokens_out`, `cost_usd`) and silently dropped `truncated` and
`reasoning_tokens`, which come from `Result.extra` at call time and cannot be recovered
afterwards. The rule is now "keep everything the new scorer does not itself produce".

Makefile help gained a RE-MEASURE section and a SCOPING section (`MATCH`, `EVAL_RUNS_DIR`).
144 runs rescored; `make ci: green`.

### 2026-09-25 · 34 — Silver, measured. It is a biased proxy, not just a noisy one.

Item 4 of the post-review plan, recomputed with the FIXED scorer (entry 31) rather than
taking the review's numbers, since everything else measured with the broken one moved.

The experiment costs **nothing**, which is the part I had wrong when I budgeted ~$1.00
for it: "author silver with model X, same prompt and settings as the arms" is *exactly
what X already produced on this dataset*. So every arm on disk is a candidate silver
author, and all 24 can be tried instead of the 3 I proposed.

Method: for each author A, use A's v1 outputs as the reference set, score every OTHER
arm's v2 outputs against them, rank those arms, and compare that ranking to the one gold
gives for the same arms. A's own row excluded throughout.

```
  CEILING (same arms, same gold, two different sets of runs):   rho = +0.928
  silver agreement with gold:   min -0.012   mean +0.352   max +0.691
  sibling lift (own family promoted):  mean +7.6 rank positions, 22 of 24 authors
```

**Robust to the scorer fix** — the only number today that was. The review measured mean
rho 0.36 and lift 7.9 with the broken scorer; the fixed scorer gives 0.35 and 7.6.

**The ceiling is the point.** Two runs of the same arms against the same gold agree at
0.928, not 1.0, so that is the most any proxy could score. A silver at 0.35 is not
"moderate agreement" — it is about a third of the agreement that was available.

**The finding that matters is the bias, not the noise.** A silver author systematically
promotes models of its own family by ~8 rank positions, for 22 of 24 authors, and
**excluding the author's own row does not remove it**. The circularity is not "the judge
scores itself first" — that part is easy to fix. It is "the judge rewards its own kind's
style", which survives every fix of that shape. So a silver-ranked leaderboard is not
merely noisier than a gold one; it is wrong in a direction you can predict from who wrote
the references.

Best authors here: `llama_s` (0.691), `deepseek_m` (0.628), `llama_m` (0.545). Worst:
`mistral_m` (-0.012), `gemma_l` (0.109), `openai_m` (0.120). An author's own quality rank
barely predicts its usefulness as a reference author — so "pick the best model to write
silver" is not a strategy the data supports.

**DECISION: the $1.00 silver-authoring experiment is dropped.** The question it was meant
to answer is answered, more completely, for free. Entry 12's open question is closed:
silver stays as an exhibit of measured circularity, not as a scoring target.

### 2026-09-25 · 35 — The process changes fold into `make` and the runbook

Marko's point: an entire category of analysis lands here, so it should be a harness
capability rather than a scratch script somebody has to rediscover.

- **`make silver-calibrate DATASET_ID=... REF_MATCH=... ARM_MATCH=...`** —
  `scripts/silver_calibrate.py`. Generic: the grouping key for the sibling-bias report is
  `--group-by` (default `family`, read from params), so it is not summarisation-specific.
  Prints the ceiling first, because a proxy score means nothing without it.
- **`make rescore DATASET_ID=... MATCH=... OUT=...`** — recompute scores from stored
  outputs, $0 (entry 33).
- **`make leaderboard ... MATCH=_v2`** — scope a dataset that has grown across config
  versions, instead of deleting the older runs.
- Makefile help gained `TRUST THE REFERENCE?`, `RE-MEASURE` and `SCOPING` sections.
- README gained four sections: *Is the ranking real?*, *Re-measuring without re-running*,
  *Do you trust your reference?*, *Scoping a dataset that has grown* — each stating the
  mistake that motivated it, including that deleting runs to shorten a table is what cost
  18 arms of paid results here.

`make ci: green`.
