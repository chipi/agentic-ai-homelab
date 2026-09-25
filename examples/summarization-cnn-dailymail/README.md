# Summarising news, 24 models at once

One task — summarise a news article in 2–3 sentences — measured across 24 hosted models
from 8 vendors, on three axes at once: **quality, cost and wall-clock speed**.

It is a worked example for [`../eval-harness`](../eval-harness), and it is also a record
of what a small eval can and cannot tell you. Most of what is interesting here was found
by *disbelieving the first answer*: several headline findings in
[`../EVAL_NOTES.md`](../EVAL_NOTES.md) were retracted after the numbers were checked
properly, including one caused by a one-line bug in this example's own scorer.

---

## Get the data

**Nothing is committed.** CNN/DailyMail belongs to its publishers; this repo ships a
download recipe, never the text.

```bash
cd examples/summarization-cnn-dailymail
uv sync                       # provisions its own Python 3.11 and deps
uv run fetch.py --n 20        # ~1 second, stdlib only, no `datasets` library
```

That writes 20 articles into `../eval-harness/data/sources/cnn_dailymail_20/` and their
human-written highlights into `../eval-harness/data/references/gold/cnn_dailymail_20/`.
Both paths are gitignored.

**Why this dataset.** `abisee/cnn_dailymail` is Apache-2.0 — the only clearly-licensed
option among the usual summarisation benchmarks — and it is the most-cited baseline, so
published ROUGE numbers exist to sanity-check ours against. That is the point of using a
standard set rather than inventing data: somebody else's baseline is a check on your
instrument.

**Why the references are gold.** `highlights` are written by the journalists who filed
the article. Human-authored, so `references/gold/`. Most evals never get this, which is
what makes the silver experiment below possible.

## Run it

```bash
cp ../eval-harness/.env.example ../eval-harness/.env      # point at your proxy
cd ../eval-harness

make experiment-dry-run CONFIG=../summarization-cnn-dailymail/configs/arm_qwen_s.yaml
make sweep CONFIGS="../summarization-cnn-dailymail/configs/arm_*.yaml" REPEAT=3

# scores are written rounded; regenerate them at full precision before testing ties
make rescore DATASET_ID=cnn_dailymail_20 MATCH=_v2
EVAL_RUNS_DIR=data/runs-rescored make leaderboard DATASET_ID=cnn_dailymail_20
```

The `rescore` step is not optional for the numbers below. Run scores land on disk rounded
to 6 decimals, which is enough to report and not enough to tell a genuine tie from a
rounding artifact — and the significance test cares. `make leaderboard` says so when it
sees low-precision runs.

Dry-run first; it costs nothing and tells you what the sweep will. The full 24-arm sweep
at `REPEAT=3` is **1440 calls, ~$1.45, ~80 minutes** — most of it waiting on providers.

Validating a change rather than measuring something? Use four cheap arms and a scratch
directory, so a smoke pass cannot add repeats to a real sweep's arms:

```bash
EVAL_RUNS_DIR=/tmp/smoke make sweep REPEAT=1 \
  CONFIGS="../summarization-cnn-dailymail/configs/arm_{qwen_s,glm_s,gemma_m,mistral_s}.yaml"
```

## What is held constant

Every arm shares the dataset, the prompt file, temperature 0, `max_tokens: 1200` and
`reasoning: {enabled: false}`.

One exception, disclosed because the fingerprint records it: `mistral_l` was rate-limited
out of the sweep and re-run afterwards, by which time the adapter had changed — so its
three runs carry a different `adapter.sha256` than the other 69. Every run also carries
`harness.dirty: true`, meaning the recorded commit does not identify the code that ran. Only the model varies — and the run
fingerprint records all of it, so "we varied one thing" is *checkable* rather than
asserted.

The prompt lives in `prompt.txt`, is 119 bytes, and its sha256 is in every fingerprint:

> Summarise this news article in 2-3 short sentences, in the terse style of a news wire
> summary. Output only the summary.

This is **not** prompt optimisation. A per-model prompt would make the comparison
meaningless, so the same bytes go to every model and the record proves it.

**Reasoning is off everywhere.** Where a model's endpoint makes reasoning mandatory it is
excluded and replaced by the nearest same-family model that allows it — `claude-opus-5`
rather than 5.5, `glm-4.6` rather than 5.3-prime. Verified rather than assumed: every run
records `reasoning_tokens` from the provider's own accounting, and they are all zero.

## The arms

8 families × 3 **price tiers**. `price_tier`, not "size" — it is the vendor's own
small/mid/large product step, and every family mixes generations within it (qwen's
"large" is the *oldest* of its three). This experiment cannot attribute a difference
between tiers to model size, and no conclusion here does.

| | small | mid | large | weights |
|---|---|---|---|---|
| anthropic | haiku-4.5 | sonnet-5 | opus-5 | closed |
| openai | gpt-5.4-mini | gpt-5.5 | gpt-6-sol | closed |
| llama | 4-scout | 3.3-70b | 4-maverick | open |
| gemma | 3-27b | 4-26b-a4b | 4-31b | open |
| qwen | 3.8-flash | 3.7-plus | 3-max | open |
| deepseek | v4-flash | v4.1-flash | v4-pro | open |
| glm | 4.5-air | 4.6 | 5 | open |
| mistral | small-3.2 | medium-3.1 | large-2512 | open |

`model_provenance.json` records what each proxy alias resolved to, because a run's
fingerprint stores the upstream model and a gateway alias is not one.

## Quality, in two facets that disagree on purpose

ROUGE F1 against a single reference is a **length ranking wearing a quality costume**:
across these 24 arms, ρ(output words, precision) = −0.73 and ρ(words, recall) = +0.81.
Choosing recall over F1 does not remove the bias, it flips it. So both ends are measured
deliberately:

- **`coverage`** — recall with the output clipped to *that item's* reference length. Every
  arm is judged on the same budget the human used, so writing more cannot buy coverage;
  only putting the important thing first can.
- **`concision`** — precision over the whole output. Padding is punished here exactly as
  raw recall rewards it.

ρ(coverage, concision) = **+0.25** — related but far from the same ordering, which is the
point of carrying both. Which one you want is a product decision the eval refuses to make
for you. `PRIMARY_METRIC = "coverage"`; pass `--sort concision` for the other view.

**Neither is length-neutral, and `coverage` is not the length-controlled one.** ρ(words,
coverage) = +0.28 against ρ(words, rougeLsum) = −0.30: the same magnitude, opposite sign.
Worse, the clip only binds above the reference length — **205 of 1440 outputs (14%) are
shorter than the reference and are never clipped at all**, up to 37% for one arm. So
"judged on the same budget" holds for the verbose arms and not for the terse ones.
Coverage earns its place by being the interpretable question ("did the summary carry the
story"), not by being bias-free.

`grounding` (share of summary bigrams present in the article) rides along as a third
facet: high means extractive and safe, low means abstractive — which is either a good
paraphrase or a fabrication, and this cannot tell them apart. Read it beside ROUGE, never
instead of it. It is not length-neutral either (ρ = +0.25), and the output says so.

**Format compliance is computed, not eyeballed** — `fmt_narration`, `fmt_label`,
`fmt_markdown`, `fmt_bullets`, `fmt_paragraphs`, `fmt_overlong`, on every output. This
exists because five outputs were once read by hand and 1440 declared clean; computing it
over all of them finds **77 of 1440** hit at least one flag — including four where a model
wrote its reasoning out in the open and scored 0.10 for it.

## What 20 articles actually showed

- **Which article you drew matters ~28× more than which model wrote the summary.** Of the
  variance in `coverage`, **73% is between articles and 2.6% between arms.** This is why
  the comparison is paired — ranking arms *within* each article removes the article term,
  though ~24% of interaction and repeat variance remains after it.
- **Temperature 0 is not deterministic.** Only **9.8%** of outputs were byte-identical
  across three repeats; **12 of 24 arms produced zero identical outputs**. `REPEAT=3` is
  not caution here, it is the minimum.
- **Price buys very little on this task.** The dearest arm costs **202×** the cheapest and
  ranks **9th of 24** on the primary facet. The Pareto frontier keeps 10 of 24 arms; the
  other 14 are beaten on quality *and* cost *and* speed simultaneously.
- **A model-authored reference is biased, not just noisy.** See below.

The leaderboard says all of this itself, and refuses to present an ordering its own data
cannot support:

```
IS THE ORDERING REAL?   metric=coverage  k=24 arms  N=20 items
  global test (permutation on within-item ranks): p = 0.0054 -> an arm effect exists
  Nemenyi critical difference = 8.13 rank positions; observed span = 8.57
  pairs distinguishable: 1 of 276
```

One pair out of 276 — `deepseek_s` over `qwen_m`. An effect exists; almost no *specific*
claim about which model beats which survives accounting for 276 comparisons. A leaderboard
that printed a confident 1-to-24 ordering from this data would be lying, and most do.

**`concision` separates 33 pairs, and that is mostly not what it looks like.** Of those 33,
**27 are pairs that output length alone also separates, with the shorter arm winning, and
0 go the other way.** Concision is precision, ρ(words) = −0.73, so it is largely detecting
*writes short* rather than *writes well*. A facet that resolves many pairs is not thereby
the more informative one, and this is the example's own instrument teaching that.

## Can you trust a model-written reference?

Usually there is no gold, so a strong model writes the references — "silver" — and you
rank candidates against those. Here gold exists, so the proxy can be *measured*:

```bash
make silver-calibrate DATASET_ID=cnn_dailymail_20 REF_MATCH=_v1 ARM_MATCH=_v2
```

It costs nothing: "author silver with model X using the same prompt and settings as the
arms" is exactly what X already produced, so all 24 arms are tried as authors.

```
ceiling (same arms, same gold, two run sets):   rho = +0.924
silver agreement with gold:   -0.013 .. +0.697, mean +0.326
sibling lift:  +7.4 rank positions, positive for 22 of 24 authors
```

Read against the **ceiling**, not against 1.0: two runs of the same arms against the same
gold only agree at 0.92, so that is the most any proxy here could score.

The last line is the finding. **A silver author promotes models of its own family**, and
excluding the author's own row does not remove it — the circularity is not a judge scoring
*itself*, it is a judge rewarding its own kind's style. A silver-ranked leaderboard is not
merely noisier than a gold one; it is wrong in a direction you can predict from who wrote
the references.

Two caveats on that number, because a single mean hides them:

- **The lift is worst where the author is worst.** ρ(author agreement, sibling lift) =
  −0.70: the four authors above ρ 0.5 average **+4.2** positions, the twelve below ρ 0.3
  average **+9.4**. "~7 positions" is an average dominated by authors you would not choose.
- **Family and output length are entangled** — models of a family write similar amounts —
  so part of this is length preference rather than "style". Not fully separated here.

And the part that matters outside this example: **the best author was `llama_s`, which
ranks 14th of 24 as a summariser.** Being good at the task and being good at judging it
are only loosely related, so "use your strongest model to write the references" is a
weaker heuristic than it sounds — and in the case silver is actually *for*, no gold
exists, so you cannot check which author you got.

## Files

| | |
|---|---|
| `fetch.py` | download recipe — stdlib only, writes sources + gold |
| `prompt.txt` | the one prompt, shared by every arm, hashed into every fingerprint |
| `adapter.py` | the integration seam: `call_system`, `score`, `warmup`, `fingerprint` |
| `configs/arm_*.yaml` | 24 arms; only `model` and the price fields differ |
| `model_provenance.json` | what each proxy alias resolved to upstream |
| `reference/` | configs for authoring a reference tier, and when not to |
| `pyproject.toml`, `uv.lock` | isolated environment; `uv sync` provisions its own Python |

## Not covered

- **20 articles.** Everything above rests on a 20-article sample, which is why the
  critical-difference line matters so much.
- **One reference per article.** ROUGE against a single human summary is a weak proxy; two
  valid summaries can share few n-grams.
- **`grounding` is ours**, ~20 lines, not a standard metric and not comparable to any
  published number.
- **Speed is machine-bound.** The latency column mixes this machine, the proxy and the
  upstream provider. It is a property of your setup, not of the model — which is
  deliberate: the same experiment measures how fast *your* machine is at *this* task.
- **No local model arm yet.** The ML-vs-LLM contrast this example is named for — a
  classical seq2seq summariser against the hosted models — is not built.
