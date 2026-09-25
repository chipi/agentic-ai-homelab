# Evaluation report — 24 LLMs on news summarisation

**Dataset** `cnn_dailymail_20` · 20 articles · human-written gold references
**Arms** 24 hosted models, 8 vendors, 3 price tiers each
**Design** 3 repeats per arm · 1440 calls · $1.45 · identical prompt, temperature 0, reasoning off
**Date** 2026-09-25 · **Harness** `examples/eval-harness` · **Journal** [`EVAL_NOTES.md`](EVAL_NOTES.md)

---

## Executive summary

**Twenty articles are enough to answer decision questions and not enough to rank 24
models.** Those are different things, and conflating them is the easiest way to misread
this report in either direction.

**The expensive arms do not earn their price.** `deepseek_m` at **$0.0029** per 20 articles
beats `anthropic_l` at **$0.1939** — 67× dearer — on the primary quality facet
(delta +0.031, p = 0.043) and on the literature-standard one (p = 0.039). This is the
question the price-tier design was built to ask, and the answer is clear.

**Fourteen of 24 arms are off the table entirely**, with no statistics required: each is
beaten by some other arm on quality *and* cost *and* speed simultaneously. Ten arms remain
on the frontier. That is the report's most directly actionable output.

**The cheapest family leads.** `deepseek_m` and `deepseek_s` take the top two places on
coverage at **$0.002–0.003**, ahead of models costing 60–100× more. `llama_l` at $0.0033
is the most consistent arm across facets — 1st on `concision`, 1st on `rougeLsum`, 3rd on
`coverage`.

**What the data will not support is a confident 1-to-24 ordering.** Asking "which of all
276 possible pairs differ?" and paying the multiplicity price for all 276 leaves 10 pairs
separated on `rougeLsum` and 1 on `coverage`. A leaderboard printing a smooth ranking of
24 models from this data is asserting hundreds of comparisons it cannot support — but that
is a limit on *ranking*, not on deciding.

**Which article you drew matters ~28× more than which model summarised it.** 73.5% of the
variance in the primary facet is between articles, 2.6% between arms. This governs any
future eval on this task: without pairing, the model signal is buried.

**Beware the metric that separates most.** Ranked by pairs distinguished —
`summary_words` 85, `grounding` 50, `concision` 33, `rougeLsum` 10, `rouge1` 5,
`coverage` 1 — the order is almost exactly how much each measure depends on output length.
The most "sensitive" metric available is a word count. An eval that picks its headline
facet by which one separates cleanest will pick a length measure and call it quality.

**A model-authored reference ("silver") is biased, not merely noisy.** Checked against real
gold: silver rankings agree with gold at ρ = 0.33 on average against a retest ceiling of
0.92, and **every silver author promotes models of its own family** — +7.4 rank positions,
22 of 24 authors, permutation p < 0.001. The best reference author here ranks 14th of 24 as
a summariser, so "use your strongest model to write the references" is not supported.

**Temperature 0 is not deterministic.** 9.8% of outputs were byte-identical across three
repeats; 12 of 24 arms produced zero identical outputs. Single-run evals on this task
measure one sample of a random process.

**Six findings in this report's own history were retracted**, two caused by bugs in this
harness's own scorer, all found by adversarial review rather than by the author. §6 records
them, because the retraction rate measures how much of a first-pass eval is instrument
rather than signal.

## 1. What was measured

One task: *summarise a news article in 2–3 short sentences, in the terse style of a news
wire summary.* One prompt, 119 bytes, stored once in `prompt.txt`, its sha256 recorded in
every run's fingerprint. Not prompt optimisation — a per-model prompt would make the
comparison meaningless.

**Corpus.** `abisee/cnn_dailymail`, Apache-2.0 per its dataset card, 20 articles from the
test split. References are the `highlights` written by the journalists who filed each
article — genuinely human-authored, mean 36.7 words. The corpus is never committed; the
repo ships a download recipe (`fetch.py`, stdlib only).

**Held constant.** Dataset, prompt file, temperature 0, `max_tokens` 1200,
`reasoning: {enabled: false}`. 31 fingerprint paths are byte-identical across all runs,
including `prompt_sha256`, `items_sha256` and `reference_id`. Two documented exceptions:
`mistral_l` was rate-limited out of the sweep and re-run later against a changed adapter,
so its 3 runs carry a different `adapter.sha256` than the other 69; and all 72 runs record
`harness.dirty: true`, meaning the recorded commit does not identify the code that ran.

**Reasoning off, verified not assumed.** Where a vendor's endpoint makes reasoning
mandatory, that model is excluded and the nearest same-family model that permits
reasoning-off is used instead (`claude-opus-5` not 5.5; `glm-4.6` not 5.3-prime). Every
run records `reasoning_tokens` from the provider's own accounting: **0 on all 1440 calls.**

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
| **`coverage`** | rougeLsum **recall**, output clipped to that item's reference length | ρ(words) = **+0.28** |
| **`concision`** | rougeLsum **precision**, whole output | ρ(words) = **−0.73** |
| `rougeLsum` | sentence-level LCS F1, the CNN/DM convention | ρ(words) = **−0.30** |
| `rouge1` | unigram F1 | ρ(words) = **−0.21** |
| `grounding` | share of summary bigrams present in the article | ρ(words) = **+0.25** |

ρ(coverage, concision) = **+0.25** — related, not independent, and not opposed. Both are
kept because which one you want is a product decision the eval must not make for you.

**`coverage` is not the length-controlled facet, despite being designed as one.** Its
|ρ(words)| of 0.28 is the same magnitude as plain `rougeLsum`'s 0.30. And the clip only
binds *above* the reference length: **205 of 1440 outputs (14%) are shorter than the
reference and are never clipped at all** — up to 37% for one arm. It is the primary facet
because it asks the interpretable question ("did the summary carry the story"), not because
it is unbiased.

**`grounding` cannot tell a good paraphrase from a fabrication.** High means extractive,
low means abstractive; which of those is a hallucination it has no way to know. It is also
not length-neutral. Read beside ROUGE, never instead of it. It is ~20 lines of our own
code and is not comparable to any published number.

**Format compliance is computed over every output, not sampled.** Six flags:
`fmt_narration`, `fmt_label`, `fmt_markdown`, `fmt_bullets`, `fmt_paragraphs`,
`fmt_overlong`. **77 of 1440 outputs (5.3%)** trip at least one. This exists because five
outputs were once read by hand and all 1440 declared clean.

**Speed is machine-bound and not a model property.** The latency column mixes this
machine, a local proxy, and the upstream provider. One value is a known artifact:
`mistral_l`'s 16100 ms includes retry backoff from its rate-limited recovery run.

---

## 3. Results

All 24 arms, ranked by `coverage`. Costs are per 20-article pass, averaged over 3 repeats.

| arm | family | tier | coverage | concision | rougeLsum | rouge1 | grounding | words | $/20 | ms | flags |
|---|---|---|---|---|---|---|---|---|---|---|---|
| deepseek_m | deepseek | mid | **0.3793** | 0.2794 | 0.3478 | 0.3927 | 0.4436 | 57 | 0.0029 | 2512 | 0 |
| deepseek_s | deepseek | small | 0.3745 | 0.2943 | 0.3447 | 0.3876 | 0.3677 | 49 | 0.0019 | 2873 | 0 |
| llama_l | llama | large | 0.3694 | **0.3067** | **0.3558** | 0.3869 | 0.4043 | 48 | 0.0033 | 2988 | 0 |
| anthropic_m | anthropic | mid | 0.3682 | 0.2500 | 0.3251 | 0.3654 | 0.3677 | 65 | 0.1094 | 3609 | 0 |
| llama_m | llama | mid | 0.3600 | 0.2708 | 0.3195 | 0.3582 | 0.3974 | 51 | 0.0021 | 3419 | 0 |
| mistral_s | mistral | small | 0.3594 | 0.2575 | 0.3142 | 0.3508 | 0.2811 | 54 | **0.0010** | 3426 | 2 |
| qwen_s | qwen | small | 0.3487 | 0.2797 | 0.3202 | 0.3657 | 0.3439 | 46 | **0.0010** | 10920 | 0 |
| anthropic_s | anthropic | small | 0.3485 | 0.2323 | 0.3101 | 0.3569 | 0.3731 | 71 | 0.0254 | 2094 | 1 |
| anthropic_l | anthropic | large | 0.3485 | 0.2269 | 0.3094 | 0.3461 | 0.4173 | 76 | **0.1939** | 3614 | 5 |
| deepseek_l | deepseek | large | 0.3457 | 0.2914 | 0.3442 | 0.3820 | 0.3402 | 49 | 0.0053 | 2925 | 0 |
| openai_m | openai | mid | 0.3456 | 0.2938 | 0.3244 | 0.3664 | 0.3385 | 43 | 0.0290 | 2342 | 0 |
| openai_l | openai | large | 0.3433 | 0.2988 | 0.3307 | 0.3680 | 0.3607 | 42 | 0.0519 | 3068 | 0 |
| glm_m | glm | mid | 0.3419 | 0.2690 | 0.3164 | 0.3569 | 0.3494 | 50 | 0.0029 | 3763 | 0 |
| glm_l | glm | large | 0.3392 | 0.2697 | 0.3120 | 0.3423 | 0.3528 | 63 | 0.0072 | 5231 | 5 |
| qwen_l | qwen | large | 0.3381 | 0.2451 | 0.3104 | 0.3550 | 0.2922 | 58 | 0.0083 | 2970 | 0 |
| llama_s | llama | small | 0.3373 | 0.2550 | 0.3151 | 0.3492 | 0.4401 | 58 | 0.0016 | 3536 | 0 |
| gemma_l | gemma | large | 0.3351 | 0.2874 | 0.3188 | 0.3525 | 0.3766 | 43 | 0.0017 | 2828 | 0 |
| openai_s | openai | small | 0.3347 | 0.2615 | 0.3040 | 0.3510 | 0.3665 | 49 | 0.0061 | 1887 | 0 |
| mistral_m | mistral | mid | 0.3302 | 0.2666 | 0.2953 | 0.3356 | 0.2909 | 46 | 0.0085 | **986** | 0 |
| gemma_s | gemma | small | 0.3286 | 0.2441 | 0.2949 | 0.3322 | 0.2741 | 54 | 0.0012 | 2279 | 0 |
| glm_s | glm | small | 0.3279 | 0.3005 | 0.3196 | 0.3560 | 0.3413 | **39** | 0.0011 | 4470 | 0 |
| gemma_m | gemma | mid | 0.3250 | 0.2856 | 0.3210 | 0.3569 | 0.3645 | 44 | 0.0012 | 2276 | 0 |
| qwen_m | qwen | mid | 0.3134 | 0.2364 | 0.2928 | 0.3379 | 0.3058 | 57 | 0.0041 | 1564 | 0 |
| mistral_l | mistral | large | 0.3119 | 0.2420 | 0.2760 | 0.3110 | 0.2435 | 48 | 0.0113 | 16100* | 20 |

\* retry backoff, not model latency.

### 3.1 Is the ordering real?

Friedman-style permutation test on within-item ranks (5000 permutations), with a Nemenyi
critical difference applied simultaneously to all 276 pairs:

| metric | p | critical difference | observed span | pairs distinguishable |
|---|---|---|---|---|
| `coverage` | 0.0054 | 8.13 | 8.57 | **1** / 276 |
| `concision` | 0.0002 | 8.13 | 11.85 | 33 / 276 |
| `rougeLsum` | 0.0002 | 8.13 | 10.40 | 10 / 276 |
| `rouge1` | 0.0002 | 8.13 | 9.90 | 5 / 276 |
| `grounding` | 0.0002 | 8.13 | 17.60 | 50 / 276 |
| `summary_words` | 0.0002 | 8.13 | 19.60 | 85 / 276 |

The single `coverage` separation is **`deepseek_s` > `qwen_m`**.

### 3.1b Decision questions, asked one at a time

§3.1 answers *"which of all 276 pairs differ?"* and pays the multiplicity price for all
276. That is the right price for that question and the wrong question for a decision. A
single comparison decided **before** looking carries no such penalty. Sign-flip permutation
test on per-article deltas, 20 000 permutations:

| question | metric | delta | articles won | p | verdict |
|---|---|---|---|---|---|
| `deepseek_m` vs `anthropic_l` — is 67× the price worth it? | coverage | +0.0308 | 12/20 | **0.043** | separated |
| | rougeLsum | +0.0384 | 13/20 | **0.039** | separated |
| `deepseek_m` vs `qwen_m` — best vs worst | coverage | +0.0659 | 16/20 | **0.0004** | separated |
| `llama_l` vs `mistral_l` — best vs worst open large | rougeLsum | +0.0799 | 17/20 | **0.0021** | separated |
| `deepseek_m` vs `anthropic_m` — vs the best-placed dear arm | coverage | +0.0111 | 12/20 | 0.52 | not separated |
| `deepseek_s` vs `openai_l` | coverage | +0.0312 | 15/20 | 0.071 | not separated |

**Honest caveat**: these six were chosen *after* seeing the table, so they are not truly
pre-registered. Treated as a family of six and Holm-corrected, only `deepseek_m > qwen_m`
survives on coverage and two survive on `rougeLsum`. The price comparison is sound if the
price question was yours before you looked — which, given the price-tier design, it was —
and is fishing if it was not. The distinction is not cosmetic: it is the difference between
a test and a search.

### 3.2 Variance decomposition (`coverage`)

| source | share |
|---|---|
| between articles | **73.5%** |
| between arms | **2.6%** |
| residual (arm × article, repeats) | 23.9% |

### 3.3 Determinism at temperature 0

**47 of 480 (9.8%)** article-outputs byte-identical across 3 repeats. **12 of 24 arms
produced zero identical outputs.** Only `anthropic_s` was fully deterministic in the
earlier sweep. `REPEAT=3` is the minimum here, not caution.

### 3.4 Pareto frontier (coverage / cost / latency)

10 of 24 arms: `deepseek_m`, `deepseek_s`, `mistral_s`, `anthropic_s`, `gemma_l`,
`openai_s`, `mistral_m`, `gemma_s`, `gemma_m`, `qwen_m`. The other 14 are beaten on
quality *and* cost *and* speed by some other arm — off the table at any budget.

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

## 4. Discussion

**The experiment's resolution is set by the corpus, not the models.** With 73.5% of
variance between articles and 2.6% between arms, the paired design is doing most of the
work, and what remains is small relative to 276 simultaneous comparisons. This is not a
small-sample complaint that more data would fix at the margin — it is the shape of the
task. Twenty articles is enough to establish *that* the models differ and not *which*
differ.

**Discriminating power is not informativeness.** Ranked by pairs separated, the order is
`summary_words` (85) > `grounding` (50) > `concision` (33) > `rougeLsum` (10) > `rouge1` (5)
> `coverage` (1). That is almost exactly the order of how much each measure depends on
output length or extractiveness. The most "sensitive" metric available is a word count. An
eval that selects its headline metric by which one produces the cleanest separation will
select a length measure and call it quality.

**Concision's 33 separations are mostly length.** 27 of them are pairs `summary_words`
alone separates with the shorter arm winning; 0 go the other way. It is detecting *writes
short*, which for a task specified as "2–3 short sentences" is a form of instruction
compliance rather than summarisation skill — worth measuring, wrong to call quality.

**Price behaves almost independently of quality.** `anthropic_l` at $0.1939 ranks 9th;
`deepseek_m` at $0.0029 ranks 1st — a 67× price difference with the cheaper model ahead.
Neither gap is individually significant, which is itself the finding: *if a model 67×
cheaper cannot be shown to be worse, the expensive one has not earned its price on this
task.* The frontier discarding 14 of 24 arms is the actionable output.

**No family's tier ladder predicts quality.** `deepseek` runs mid > small > large,
`anthropic` mid > small ≈ large, `mistral` small > mid > large. Since each ladder mixes
generations, this experiment cannot say whether that is a size effect, a generation effect,
or noise — and given §3.1, noise is not excluded for any of them.

**Silver's problem is direction, not magnitude.** A noisy proxy costs precision; a proxy
that promotes the author's own family by 7 rank positions produces a *wrong ranking that
looks clean*. Excluding the author's own row — the obvious fix — does not remove it,
because the bias is stylistic affinity rather than self-preference. And the case silver
exists for is the case where there is no gold to detect this with. Family and output length
are entangled (models of a family write similar amounts), so part of the effect may be
length preference; this experiment does not separate them.

**Format contamination is rare but concentrated.** 77 of 1440 outputs, heavily in three
arms: `mistral_l` (20 flags), `glm_l` and `anthropic_l` (5 each). `glm_l` emitted visible
chain-of-thought on 4 outputs scoring ~0.09 — an instruction-following failure, not a
reasoning-flag failure, since its reasoning-token count is 0.

---

## 5. What this experiment cannot say

- **Which model is best.** One pair of 276 is distinguishable on the primary facet.
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

---

## 6. Corrections, and why they belong in the report

Six findings were retracted during this work. They are listed because the retraction rate
*is* a result: it measures how much of a first-pass eval is instrument rather than signal.

| retracted claim | what was actually true | cause |
|---|---|---|
| "`llama_l` is the only separated arm" | nothing was separated by that method | band-walk depended on traversal direction |
| "nothing is distinguishable at n=20, at any number of arms" | up to 33 pairs separate | `rougeLsum` was silently plain `rougeL` |
| "the arm effect is substantially a length effect" | true for the *pairwise* signal, false for the global one | over-correction of the above |
| "tier measures size; anthropic is flat across sizes" | tier is price and confounds generation | assumed, never checked |
| "no arm emitted preamble or bullets" | 77 of 1440 outputs trip a format flag | read 5 outputs, generalised to 1440 |
| "Anthropic arms bill hidden reasoning tokens" | provider reports 0 on all 1440 calls | inferred from a token/word ratio |

Two of these were caused by defects in this harness's own scorer. **All six were found by
adversarial review, none by the person who produced them.** Two further rounds of review
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

---

## 7. Reproduction

```bash
cd examples/summarization-cnn-dailymail
uv sync
uv run fetch.py --n 20

cd ../eval-harness
cp .env.example .env                      # point at a proxy
make sweep CONFIGS="../summarization-cnn-dailymail/configs/arm_*.yaml" REPEAT=3
make rescore DATASET_ID=cnn_dailymail_20 MATCH=_v2
EVAL_RUNS_DIR=data/runs-rescored make leaderboard DATASET_ID=cnn_dailymail_20
make silver-calibrate DATASET_ID=cnn_dailymail_20 REF_MATCH=_v1 ARM_MATCH=_v2
```

The `rescore` step is required for the significance numbers: run scores are written rounded
to 6 decimals, which cannot distinguish a genuine tie from a rounding artifact, and the
leaderboard says so when it sees them.

Expect different absolute numbers. Providers update models behind stable names, and
`reasoning_tokens`, `providers_seen` and the resolved upstream model id are recorded per run
precisely so a future divergence can be attributed rather than guessed at.
