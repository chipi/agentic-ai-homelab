# Evaluation report — 24 LLMs on news summarisation

**Dataset** `cnn_dailymail_200` · 200 articles · human-written gold references
**Arms** 24 hosted models, 8 vendors, 3 price tiers each
**Design** 1 pass per arm · 4,800 calls · $4.93 · identical prompt, temperature 0, reasoning off
**Date** 2026-09-26 · **Harness** `examples/eval-harness` · **Journal** [`EVAL_NOTES.md`](EVAL_NOTES.md)

> **This report was re-measured at n=200 on 2026-09-26.** It previously covered
> `cnn_dailymail_20` — 20 articles, 3 repeats, $1.45 — and several of its headline claims
> did not survive. Where a number changed, the old one is named rather than quietly
> replaced; §6 carries the full list. The 20 articles are a subset of these 200, so every
> result below is also reported on the **180 that took no part** in the earlier run.

---

## Executive summary

**Two hundred articles separate a top group and a price verdict, and still cannot rank 24
models.** Those are different questions, and conflating them is the easiest way to misread
this report in either direction.

**The expensive arms do not earn their price, and this is now the firmest result here.**
`deepseek_m` at **$0.0296** per 200 articles beats `anthropic_l` at **$1.9652** — 66×
dearer — by +0.0306 coverage, p = 0.0000, and it holds on the 180 out-of-sample articles
and on the literature-standard metric too. At n=20 that same comparison came back
"not separated"; the question was never unanswerable, twenty articles just could not
answer it.

| pre-registered pair | all 200 | 180 held out |
|---|---|---|
| `deepseek_m` > `anthropic_l` (66× dearer) | +0.0306, p=0.0000 | +0.0308, p=0.0000 |
| `deepseek_m` > `anthropic_m` (38×) | +0.0224, p=0.0006 | +0.0224, p=0.0010 |
| `deepseek_m` > `openai_l` (18×) | +0.0193, p=0.0032 | +0.0171, p=0.0153 |
| `deepseek_s` > `qwen_m` (control) | +0.0255, p=0.0000 | +0.0208, p=0.0003 |

All four survive a Holm step-down on `coverage`, in both cuts. **$1.9652 buys 15th place;
$0.0296 buys 1st.**

**Seventeen of 24 arms are off the table entirely**, with no statistics required: each is
beaten by some other arm on quality *and* cost *and* speed at once. Seven remain on the
frontier. That is the most directly actionable output here.

**Resolution improved tenfold, and it was not enough to rank.** Pairs separated on
`coverage` went from **1 of 276** at n=20 to **34 of 276** at n=200 (25 on the held-out
180). The critical difference fell from 8.13 rank positions to 2.57. A leaderboard
printing a smooth 1-to-24 ordering is still asserting hundreds of comparisons it cannot
support.

**The n=20 ranking largely did not survive.** Spearman between the two orderings of the
same 24 arms is **+0.667**. `qwen_s` fell 15 places, `llama_s` rose 12, `anthropic_m` fell
8. Only `deepseek_m` held its position. Any arm selected on 20 articles was selected
substantially by luck.

**And ten times the data does not stabilise a ladder.** Two *independent* 100-article
evals of these arms agree at only ρ = 0.753 and crown the same winner 58% of the time; at
20 articles it is ρ = 0.346 and 15%. What is stable is membership, not order —
`deepseek_m` has P(top 5) = 1.00, `llama_l` 0.95, `llama_m` 0.90, and everything from 13th
down has P(top 5) = 0.00.

**Which article you drew matters ~68× more than which model summarised it.** 67.8% of the
variance in the primary facet is between articles, 1.0% between arms. Without pairing, the
model signal is buried.

**Beware the metric that separates most.** Ranked by pairs distinguished —
`summary_words` 208, `grounding` 172, `concision` 146, `rouge1` 97, `rougeLsum` 95,
`coverage` 34 — the order is almost exactly how much each measure depends on output
length. The most "sensitive" metric available is a word count. An eval that picks its
headline facet by which one separates cleanest will pick a length measure and call it
quality. This replicated exactly at ten times the sample size.

**A model-authored reference ("silver") is biased, not merely noisy.** Measured at n=20
and not re-measured here: silver rankings agree with gold at ρ = 0.33 against a retest
ceiling of 0.92, and **every silver author promotes models of its own family** — +7.4 rank
positions, 22 of 24 authors, p < 0.001.

**Temperature 0 is not deterministic** — 9.8% of outputs byte-identical across three
repeats, 12 of 24 arms with none. That figure is from the n=20 run at r=3. This run is
r=1 by design (with articles available, repeats are the wrong place to spend the same
budget), so it does not re-measure it.

**Nine findings in this report's own history were retracted**, two caused by bugs in this
harness's own scorer, and three more by the n=20 sample itself. §6 records them, because
the retraction rate measures how much of a first-pass eval is instrument rather than
signal.

## 1. What was measured

One task: *summarise a news article in 2–3 short sentences, in the terse style of a news
wire summary.* One prompt, 119 bytes, stored once in `prompt.txt`, its sha256 recorded in
every run's fingerprint. Not prompt optimisation — a per-model prompt would make the
comparison meaningless.

**Corpus.** `abisee/cnn_dailymail`, Apache-2.0 per its dataset card, 200 articles from the
test split, mean 555 words. References are the `highlights` written by the journalists who
filed each article — genuinely human-authored, mean 34.7 words. The corpus is never
committed; the repo ships a download recipe (`fetch.py`, stdlib only). `fetch.py` pages
from offset 0, so the earlier 20-article slice is a **subset** of these 200 — verified, 20
of 20 — which is why every result is also given on the 180 that are new.

**Held constant.** Dataset, prompt file, temperature 0, `max_tokens` 1200,
`reasoning: {enabled: false}`. Each arm's config differs from its n=20 predecessor in
exactly two lines, `config_id` and `dataset_id`, verified by diff. Every run records
`reasoning_tokens` from the provider's own accounting: **0 on all 4,800 calls**.

**One repeat per arm, not three.** With articles available, repeats are the wrong place to
spend the same budget — at fixed cost, n=60/r=1 gave sd(delta) 0.0090 against n=20/r=3 at
0.0133. The consequence is stated rather than hidden: this run measures no within-arm
variance, and the determinism figures in §3.3 come from the earlier r=3 sweep.

**Provenance caveats.** All 24 runs record `harness.dirty: true`. The cause is now known:
`_fingerprint.py` derives that flag from `git status --porcelain`, which counts UNTRACKED
files, and a sweep's own configs are untracked at the moment it starts. The fix is
procedural — commit configs before launching — and it was applied for the last 16 arms but
not the first 8, which therefore sit on an earlier commit. The measurement is unaffected:
the fingerprint stores content, not pointers (`arm.params` inline, `items_sha256`,
`adapter.sha256`, `prompt_sha256`, the resolved upstream model id).

**Reasoning off, verified not assumed.** Where a vendor's endpoint makes reasoning
mandatory, that model is excluded and the nearest same-family model that permits
reasoning-off is used instead (`claude-opus-5` not 5.5; `glm-4.6` not 5.3-prime). Every
run records `reasoning_tokens` from the provider's own accounting: **0 on all 4,800 calls.**

**Arms.** 8 families × 3 **price tiers**. Price, not size: every family mixes model
generations within its tier ladder (qwen's "large" is the *oldest* of its three), so this
experiment cannot attribute any difference between tiers to model size, and does not.

---

## 2. How quality was measured, and what each measure is biased toward

This is the part that decided the results, twice.

**ROUGE F1 against a single reference is a length ranking in a quality costume.** Across
these 24 arms, ρ(output words, precision) = **−0.73** and ρ(words, recall) = **+0.81**.
Choosing recall over F1 does not remove the bias — it flips its sign. Any single-number
quality claim on this task is substantially a claim about output length.

So quality is carried by two facets chosen to pull in opposite directions:

| facet | what it is | length bias |
|---|---|---|
All correlations below are **across the 24 arm means**, not across individual outputs —
the same basis as the n=20 version of this table, so the two are comparable. (Pooled over
all 4,800 outputs the same relationships are much weaker, because the article effect
dominates any single row; that is a different quantity and is not what this table reports.)

| facet | what it is | length bias, n=200 | was, n=20 |
|---|---|---|---|
| **`coverage`** | rougeLsum **recall**, output clipped to that item's reference length | ρ(words) = **+0.07** | +0.28 |
| **`concision`** | rougeLsum **precision**, whole output | ρ(words) = **−0.84** | −0.73 |
| `rougeLsum` | sentence-level LCS F1, the CNN/DM convention | ρ(words) = **−0.31** | −0.30 |
| `rouge1` | unigram F1 | ρ(words) = **−0.35** | −0.21 |
| `grounding` | share of summary bigrams present in the article | ρ(words) = **+0.12** | +0.25 |

ρ(coverage, concision) = **+0.36** — related, not independent, and not opposed. Both are
kept because which one you want is a product decision the eval must not make for you.

**`coverage` came out much closer to length-neutral at n=200 than at n=20** — |ρ(words)|
0.07 against `rougeLsum`'s 0.31 — where at n=20 the two were indistinguishable at 0.28 and
0.30, and this report said so. That earlier reading was not wrong about the data it had; 24
points is a thin basis for a correlation, and the honest conclusion is that the n=20 figure
could not support the claim either way.

The clip still only binds *above* the reference length: **577 of 4,800 outputs (12.0%) are
shorter than their reference and are never clipped at all**. `coverage` is the primary
facet because it asks the interpretable question ("did the summary carry the story"), not
because it is unbiased.

**`grounding` cannot tell a good paraphrase from a fabrication.** High means extractive,
low means abstractive; which of those is a hallucination it has no way to know. It is also
not length-neutral. Read beside ROUGE, never instead of it. It is ~20 lines of our own
code and is not comparable to any published number.

**Format compliance is computed over every output, not sampled.** Six flags:
`fmt_narration`, `fmt_label`, `fmt_markdown`, `fmt_bullets`, `fmt_paragraphs`,
`fmt_overlong`. **262 of 4,800 outputs (5.5%)** trip at least one — the same rate as at n=20 (5.3%). This exists because five
outputs were once read by hand and all 1440 declared clean.

**Speed is machine-bound and not a model property.** The latency column mixes this
machine, a local proxy, and the upstream provider. One value is a known artifact:
`mistral_l`'s 16100 ms includes retry backoff from its rate-limited recovery run.

---

## 3. Results

All 24 arms, ranked by `coverage`. Costs are for one 200-article pass. `n20` is the arm's
rank in the earlier 20-article run, over the same 24 arms.

| arm | coverage | concision | rougeLsum | rouge1 | words | $/200 | ms | flags | n20 → n200 |
|---|---|---|---|---|---|---|---|---|---|
| deepseek_m | **0.3460** | 0.2539 | 0.3188 | 0.3612 | 57 | 0.0296 | 1595 | 0.01 | 1 → 1 |
| llama_l | 0.3387 | 0.2714 | **0.3221** | **0.3636** | 49 | 0.0344 | 3473 | 0.00 | 3 → 2 |
| llama_m | 0.3382 | 0.2616 | 0.3098 | 0.3477 | 49 | 0.0217 | 4045 | 0.01 | 5 → 3 |
| llama_s | 0.3333 | 0.2475 | 0.3081 | 0.3526 | 56 | 0.0162 | 2388 | 0.01 | **16 → 4** |
| deepseek_l | 0.3325 | 0.2595 | 0.3116 | 0.3547 | 50 | 0.0556 | 2665 | 0.00 | 10 → 5 |
| glm_m | 0.3320 | 0.2566 | 0.3080 | 0.3517 | 50 | 0.0300 | 3230 | 0.01 | 13 → 6 |
| deepseek_s | 0.3285 | 0.2628 | 0.3081 | 0.3504 | 48 | 0.0198 | 2753 | 0.01 | **2 → 7** |
| openai_m | 0.3268 | 0.2787 | 0.3122 | 0.3599 | 42 | 0.2965 | 1745 | 0.00 | 11 → 8 |
| openai_l | 0.3268 | **0.2800** | 0.3151 | 0.3620 | 42 | 0.5352 | 1775 | 0.01 | 12 → 9 |
| mistral_s | 0.3255 | 0.2346 | 0.2895 | 0.3285 | 54 | **0.0099** | 2820 | 0.18 | 6 → 10 |
| anthropic_s | 0.3238 | 0.2084 | 0.2815 | 0.3259 | 71 | 0.2611 | 2025 | 0.08 | 8 → 11 |
| anthropic_m | 0.3236 | 0.2207 | 0.2903 | 0.3347 | 64 | 1.1218 | 3034 | 0.03 | **4 → 12** |
| gemma_l | 0.3204 | 0.2739 | 0.3086 | 0.3511 | 42 | 0.0173 | 2591 | 0.00 | 17 → 13 |
| openai_s | 0.3171 | 0.2508 | 0.2977 | 0.3506 | 48 | 0.0622 | **1277** | 0.01 | 18 → 14 |
| anthropic_l | 0.3155 | 0.2092 | 0.2878 | 0.3289 | 75 | **1.9652** | 3402 | 0.23 | **9 → 15** |
| glm_s | 0.3139 | **0.2800** | 0.3012 | 0.3489 | **39** | 0.0110 | 1610 | 0.00 | 21 → 16 |
| gemma_m | 0.3136 | 0.2661 | 0.3016 | 0.3442 | 44 | 0.0123 | 1873 | 0.00 | 22 → 17 |
| glm_l | 0.3124 | 0.2456 | 0.2939 | 0.3334 | 65 | 0.0750 | 5689 | 0.38 | 14 → 18 |
| gemma_s | 0.3120 | 0.2328 | 0.2835 | 0.3215 | 53 | 0.0126 | 6956 | 0.01 | 20 → 19 |
| qwen_l | 0.3108 | 0.2309 | 0.2803 | 0.3309 | 55 | 0.0842 | 2945 | 0.01 | 15 → 20 |
| mistral_l | 0.3080 | 0.2356 | 0.2798 | 0.3188 | 48 | 0.1167 | 11045 | **0.93** | 24 → 21 |
| qwen_s | 0.3068 | 0.2600 | 0.2874 | 0.3360 | 43 | 0.0099 | 25038 | 0.00 | **7 → 22** |
| mistral_m | 0.3043 | 0.2507 | 0.2806 | 0.3197 | 43 | 0.0871 | 2654 | 0.01 | 19 → 23 |
| qwen_m | 0.3030 | 0.2206 | 0.2737 | 0.3164 | 57 | 0.0417 | 1534 | 0.00 | 23 → 24 |

Spearman between the n=20 and n=200 orderings: **+0.667**.

### 3.1 Is the ordering real?

Friedman-style permutation test on within-item ranks, with a Nemenyi critical difference
applied simultaneously to all 276 pairs:

| metric | p | critical difference | observed span | pairs distinguishable |
|---|---|---|---|---|
| `coverage` | 0.0002 | 2.57 | 4.46 | **34** / 276 |
| `rougeLsum` | 0.0002 | 2.57 | 5.69 | 95 / 276 |
| `rouge1` | 0.0002 | 2.57 | 5.63 | 97 / 276 |
| `concision` | 0.0002 | 2.57 | 9.66 | 146 / 276 |
| `grounding` | 0.0002 | 2.58 | 13.99 | 172 / 276 |
| `summary_words` | 0.0002 | 2.57 | 18.23 | 208 / 276 |

On the **180 held-out** articles, `coverage` gives p = 0.0002, CD 2.71, span 4.26, **25 of
276**. At n=20 the same metric gave 1 of 276 against a CD of 8.13 — wider than the entire
table's span, which is why nothing separated.

Membership is far better determined than order. From 2,000 item-resamples:

```
  arm            avg rank   P(1st)   P(top 5)   P(bot 5)
  deepseek_m        10.00     0.76       1.00       0.00
  llama_l           10.83     0.10       0.95       0.00
  llama_m           11.07     0.11       0.90       0.00
  llama_s           11.56     0.02       0.59       0.00
  deepseek_l        11.03     0.01       0.53       0.00
  glm_m             11.24     0.01       0.47       0.00
  …
  qwen_m            14.36     0.00       0.00       0.96
  mistral_m         14.47     0.00       0.00       0.88
```

`deepseek_m` is in the top five in every resample. Which of the six *is* first is not a
claim this data supports.

### 3.1b Decision questions, asked one at a time

§3.1 asks "which of all 276 pairs differ?" and pays the multiplicity price for all 276.
That is the right price for that question and the wrong question for a decision. These
four pairs were **named before the last arm finished running**, and are Holm-corrected as
a family of four:

| question | metric | all 200 | 180 held out |
|---|---|---|---|
| `deepseek_m` vs `anthropic_l` — is 66× the price worth it? | coverage | +0.0306, 114/200, **p=0.0000** | +0.0308, 102/180, **p=0.0000** |
| | rougeLsum | +0.0310, 139/200, **p=0.0000** | +0.0331, 127/180, **p=0.0000** |
| `deepseek_m` vs `anthropic_m` — 38× | coverage | +0.0224, 112/200, **p=0.0006** | +0.0224, 104/180, **p=0.0010** |
| `deepseek_m` vs `openai_l` — 18× | coverage | +0.0193, 96/200, **p=0.0032** | +0.0171, 85/180, **p=0.0153** |
| | rougeLsum | +0.0037, 107/200, p=0.47 | +0.0038, 97/180, p=0.47 |
| `deepseek_s` vs `qwen_m` — the control | coverage | +0.0255, 107/200, **p=0.0000** | +0.0208, 93/180, **p=0.0003** |

All four separate on `coverage` in both cuts. On `rougeLsum` three of four do; the
`openai_l` comparison is the one the facets disagree about, and it is disclosed rather
than dropped.

Unlike the six pairs in the n=20 version of this section, these were fixed in advance, so
no fishing correction is owed beyond the family Holm.

### 3.2 Variance decomposition (`coverage`)

| source | share |
|---|---|
| between articles | **67.8%** |
| between arms | **1.0%** |
| residual | 31.2% |

Which article you drew moves the number ~68× more than which model wrote the summary.
(At n=20 this read 73.5 / 2.6 / 23.9; the shape is unchanged, and the arm share shrinking
is expected when the article pool widens.)

### 3.3 Determinism at temperature 0

**Not re-measured here.** This run is r=1. From the earlier r=3 sweep: 47 of 480 (9.8%)
article-outputs byte-identical across three repeats, and 12 of 24 arms with none at all.
Nothing in this run contradicts that; nothing in it confirms it either.

### 3.4 Pareto frontier (coverage / cost / latency)

**7 of 24 arms**: `deepseek_m`, `llama_m`, `llama_s`, `mistral_s`, `openai_s`, `glm_s`,
`qwen_m`. The other **17 are beaten on quality *and* cost *and* speed** by some other arm
— off the table at any budget, with no statistics required.

At n=20 the frontier held 10 arms. The three that dropped off did so because more data
moved their quality estimate, not because their cost or latency changed — a reminder that
even the statistics-free part of this report depends on the sample.

### 3.5 Can a model-authored reference be trusted?

Every arm used in turn as the silver author, its own row excluded, ranking the other 23:

| | |
|---|---|
| retest ceiling (same arms, same gold, two run sets) | **ρ = +0.924** |
| silver agreement with gold | **−0.013 … +0.697**, mean **+0.326** |
| best authors | `llama_s` (0.697), `deepseek_m`, `llama_m` |
| worst author | `mistral_m` (−0.013) |
| sibling lift (own family promoted) | **+7.4** rank positions, positive for **22 of 24** |
| ρ(author agreement, sibling lift) | **−0.70** |

The lift is worst where the author is worst: authors above ρ 0.5 average +4.2 positions,
those below ρ 0.3 average +9.4.

---

### 3.6 How much data does a ranking need?

Measured from these runs at no extra cost: draw two **disjoint** subsets of *n* articles,
rank all 24 arms independently in each, and correlate the two orderings. Neither half is
treated as truth.

| items per half | ρ(half A, half B) | 5th pct | P(both crown the same arm) | median rank move |
|---|---|---|---|---|
| 10 | 0.224 | −0.135 | 0.11 | 4.68 |
| 20 | **0.346** | 0.057 | **0.15** | 3.75 |
| 50 | 0.579 | 0.362 | 0.27 | 2.55 |
| 100 | **0.753** | 0.624 | **0.58** | 1.56 |

At 20 articles — the size of the original experiment — two independent evals of these arms
agree at ρ = 0.35 and pick the same winner 15% of the time, against 4% from chance among
24. At 100 they still disagree at ρ = 0.75.

This is the most transferable result in the report: it is about evaluation rather than
about 24 models, and it does not go stale when the models change.

## 4. Discussion

**The experiment's resolution is set by the corpus, not the models.** With 67.8% of
variance between articles and 1.0% between arms, the paired design is doing nearly all the
work. This is not a small-sample complaint that more data fixes at the margin — it is the
shape of the task. Ten times the articles moved `coverage` from 1 separated pair to 34, and
still left the top six mutually indistinguishable.

**Discriminating power is not informativeness.** Ranked by pairs separated:
`summary_words` (208) > `grounding` (172) > `concision` (146) > `rouge1` (97) >
`rougeLsum` (95) > `coverage` (34). That is almost exactly the order of how much each
measure depends on output length or extractiveness — and it is the same order as at n=20,
so it is a property of the metrics rather than of the sample. The most "sensitive" metric
available is a word count. An eval that picks its headline metric by which one separates
cleanest will pick a length measure and call it quality.

**Price behaves almost independently of quality, and now demonstrably so.** `anthropic_l`
at **$1.9652** ranks 15th; `deepseek_m` at **$0.0296** ranks 1st, and the gap is separated
at p = 0.0000 in both item cuts and on both ROUGE facets. At n=20 the same comparison was
"not separated" (p = 0.52) and the honest reading was *"if a model 66× cheaper cannot be
shown to be worse, the expensive one has not earned its price."* That reading was right,
and the stronger version is now available: it **is** shown to be better.

**The eliminations are the actionable output.** 17 of 24 arms are beaten on quality *and*
cost *and* speed simultaneously. No statistics are required for that, and it answers the
question a team actually has — not "which is best" but "which are not worth considering".

**A ladder needs more data than a decision, and possibly more than exists.** §3.6 measures
it: two independent 100-article evals of these arms still disagree at ρ = 0.753. The gap
between 1st and 3rd here is 0.0078 coverage; between 2nd and 3rd, 0.0005. Closing the
latter needs a sample in the six figures. The correct output is therefore a *set* — the
six arms with P(top 5) ≥ 0.47 — not a podium.

**Selection on a small sample is expensive in a way that does not announce itself.** The
n=20 ordering and the n=200 ordering of the same 24 arms correlate at 0.667. `qwen_s` was
7th and is 22nd; `llama_s` was 16th and is 4th. Anyone who had shortlisted the n=20 top
five would have carried two arms that belong in the bottom half and missed two that belong
at the top.

**No family's tier ladder predicts quality.** `deepseek` runs mid > large > small,
`llama` large > mid > small, `anthropic` mid > small > large, `mistral` small > large >
mid. Since each ladder mixes model generations with price steps, this experiment cannot
say whether that is size, generation, or noise.

**Silver's problem is direction, not magnitude.** (From n=20; not re-measured.) A noisy
proxy costs precision; a proxy that promotes the author's own family by 7 rank positions
produces a *wrong ranking that looks clean*. Excluding the author's own row does not remove
it, because the bias is stylistic affinity rather than self-preference — and the case
silver exists for is the one where there is no gold to detect it with.

**Format contamination is rare but concentrated.** By flag rate per output: `mistral_l`
0.93, `glm_l` 0.38, `anthropic_l` 0.23, `mistral_s` 0.18, `anthropic_s` 0.08 — every other
arm at or below 0.01. The two arms with the worst format compliance are also the two
dearest, which is worth noticing before paying for either.


## 5. What this experiment cannot say

- **Which model is best.** 34 of 276 pairs separate on the primary facet, and none of them
  are inside the top six. The output is a set, not a winner.
- **Whether the ordering would hold on another 200 articles.** Measured, and it largely
  would not: two independent 100-article evals agree at rho = 0.753 (section 3.6).
- **Anything about model size.** The tier axis is price, and confounds generation.
- **Whether abstractive outputs are accurate.** No metric here detects fabrication;
  `grounding` measures extractiveness and cannot distinguish paraphrase from invention.
- **How these models rank with reasoning enabled**, on a different prompt, on longer
  inputs, or on any other corpus.
- **How fast the models are.** Latency is a property of this machine, this proxy and the
  upstream provider on the day.
- **Anything comparable to published ROUGE.** `rougeLsum` here uses a local sentence
  splitter rather than NLTK's, and `grounding`/`concision`/`coverage` are ours.
- **ML versus LLM.** The classical-baseline arm this example is named for is not built.
- **Within-arm variance.** This run is r=1; the determinism figures are from the earlier
  r=3 sweep and were not re-measured.

---

## 6. Corrections, and why they belong in the report

Nine findings were retracted during this work. They are listed because the retraction rate
*is* a result: it measures how much of a first-pass eval is instrument rather than signal.
The first six came from bugs and from reading samples; the last three came from the sample
size itself, and only the re-measurement at n=200 exposed them.

| retracted claim | what was actually true | cause |
|---|---|---|
| "`llama_l` is the only separated arm" | nothing was separated by that method | band-walk depended on traversal direction |
| "nothing is distinguishable at n=20, at any number of arms" | up to 33 pairs separate | `rougeLsum` was silently plain `rougeL` |
| "the arm effect is substantially a length effect" | true for the *pairwise* signal, false for the global one | over-correction of the above |
| "tier measures size; anthropic is flat across sizes" | tier is price and confounds generation | assumed, never checked |
| "no arm emitted preamble or bullets" | 77 of 1440 outputs trip a format flag | read 5 outputs, generalised to 1440 |
| "Anthropic arms bill hidden reasoning tokens" | provider reports 0 on all 1440 calls | inferred from a token/word ratio |
| "`deepseek_m` vs `anthropic_l` is not separated" (p=0.52) | separated at p=0.0000, both cuts, both metrics | 20 articles could not resolve a real 0.031 gap |
| "10 of 24 arms are on the Pareto frontier" | 7 of 24 | three arms' quality estimates moved with more data |
| "CI stops baking a 990 MB model" (commit c7f47e4c) | it kept shipping, restored from cache | manifest drives the preload, not the artifact |

Two were caused by defects in this harness's own scorer, and three by trusting 20 articles.
**All of the first six were found by adversarial review, none by the person who produced
them**; the last three were found by re-measuring and by a log line added in the same
commit whose claim it falsified. Two further rounds of review
found stale numbers in the first published version of this example's README, and a bug that
would have crashed a fresh clone *after paying for its first API call*.

The practical lessons, all now enforced in code:

1. **If it can be computed over the whole corpus, it must not be reported from a sample.**
2. **Verifying a measurement must be cheap** — `make rescore` recomputes scores from stored
   outputs for $0, because when checking a metric cost $1.45 and 80 minutes, it went
   unchecked through two sweeps.
3. **A comparison method whose answer depends on traversal order is not a comparison.**
4. **Never delete measurements to tidy a table.** 18 arms of paid results were lost that
   way during this work; the fix is scoping (`--match`, `EVAL_RUNS_DIR`), not deletion.
5. **A power calculation fed a delta from the pilot inherits the pilot's error.** Journal
   entry 40 predicted `deepseek_m` vs `deepseek_s` needed n~2472, from a delta measured on
   20 articles. It separated at 200. The arithmetic was fine; the input was not.
6. **Report the claim and the check in the same commit.** The line that caught the cache
   claim above was added by the commit that made it.

---

## 7. Reproduction

```bash
cd examples/summarization-cnn-dailymail
uv sync
uv run fetch.py --n 200

cd ../eval-harness
cp .env.example .env                      # point at a proxy
make dataset-create      DATASET_ID=cnn_dailymail_200 ARGS='--source-dir data/sources/cnn_dailymail_200'
make dataset-materialize DATASET_ID=cnn_dailymail_200
make sweep CONFIGS="../summarization-cnn-dailymail/configs/arm_*_n200.yaml" REPEAT=1
make leaderboard DATASET_ID=cnn_dailymail_200

# the two questions the leaderboard cannot answer on its own
make holdout   DATASET_ID=cnn_dailymail_200 EXCLUDE=cnn_dailymail_20
make pair-test DATASET_ID=cnn_dailymail_200 A=cnn_deepseek_m_n200_v1 B=cnn_anthropic_l_n200_v1 FAMILY=4
python scripts/rank_stability.py --dataset-id cnn_dailymail_200
```

No `rescore` step is needed here. It was, for the n=20 sweep: scores were written rounded
to 6 decimals, which cannot tell a genuine tie from a rounding artifact, and the tie
tolerance is load-bearing for `coverage` (13-23% of arm pairs tie exactly on an item,
depending on how short the reference is). Score precision is 10 decimals since journal
entry 31, and the leaderboard warns if it ever reads runs written at less.

Expect different absolute numbers. Providers update models behind stable names, and
`reasoning_tokens`, `providers_seen` and the resolved upstream model id are recorded per run
precisely so a future divergence can be attributed rather than guessed at.
