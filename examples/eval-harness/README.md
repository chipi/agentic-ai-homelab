# Eval harness — drop-in evaluation for a project that already works

You have a project. It summarises, classifies, extracts, answers — and it
works, mostly. What you do not have is a way to tell whether a change made it
better. You swap a model or edit a prompt, read a few outputs, and form an
impression.

This is the missing half. Copy it into your project as `eval/`, write **one
function** that calls your existing code, and you have a repeatable loop:
frozen datasets, runs that know what produced them, cost and speed alongside
quality, and comparisons that **refuse** to mislead you.

```bash
cp -r eval-harness your-project/eval && cd your-project/eval
make demo        # the whole loop on bundled data — no API key, no network
make help        # the verbs, in the order you need them
```

It imports nothing from your project and your project imports nothing from it.

---

## Why evaluation usually fails

Not for lack of a metric. It fails because the numbers turn out not to mean
what people thought:

| what goes wrong | what this does about it |
| --- | --- |
| two numbers measured on different data, compared anyway | `run-compare` **refuses** across `dataset_id`s |
| a delta smaller than the run-to-run jitter, called an improvement | `REPEAT=3` reports the arm's own spread; deltas below it are marked noise |
| nobody knows which code produced a number | every run records `build.ref`; `validate` fails without it |
| a source file changed under a frozen dataset | every item is hashed; `materialize` re-verifies and fails loudly |
| model-generated references quoted as ground truth | gold and silver are distinct; every run records which it used |
| "model B is better" with no mention of 4× the cost | cost, tokens and latency recorded beside quality |
| a baseline nobody can justify | `promote` refuses a dirty build, an unknown build, or a one-word reason |

The refusals are the product. A tool that always yields a number teaches people
to trust numbers.

---

## How it works

Five directories and a contract between them:

```text
data/sources/        your raw inputs — IMMUTABLE, never edited in place
      ↓  make dataset-create          freeze a selection + a sha256 per item
data/datasets/       the dataset_id — the thing that makes two numbers comparable
      ↓  make dataset-materialize     rebuild run inputs, re-verify every hash
data/materialized/   derived, regenerable, disposable
      ↓  make reference-create        ground truth to score against (gold | silver)
data/references/
      ↓  make experiment-run          → scores + cost + speed + build provenance
data/runs/
      ↓  make run-compare / make judge
data/baselines/      make promote — the number future work is judged against
```

`make validate` checks the whole tree — six integrity rules, exits non-zero, so
it can gate CI.

### The three inputs

Every run records three things, and is worthless without all of them:

- **system under test** — `build.ref`, set by `EVAL_BUILD_REF` or the git SHA
- **instrument** — `config_id`, the arm you ran
- **data** — `dataset_id`, what it was measured on

Drop any one and a delta cannot be attributed to anything.

---

## Integrating your system

One function, `call_system()` in `scripts/adapter.py`:

```python
def call_system(text, params):
    from myproject.summarise import summarise        # your existing code
    out = summarise(text, model=params["model"])
    return Result(output=out.text,
                  tokens_in=out.usage.prompt_tokens,
                  tokens_out=out.usage.completion_tokens)
```

And one more, `score()`, for what "good" means in your domain. That is the
whole integration — no refactor, no wrapper, no base class.

Arms are **config files**, not code edits: four models to compare is four YAML
files sharing a `dataset_id`.

→ **[docs/INTEGRATION.md](docs/INTEGRATION.md)** — the first hour, concretely.

---

## Is the ranking real?

A table sorted by a mean always produces an ordering. Whether that ordering survives
re-running the experiment is a different question, and `make leaderboard` answers it
before it shows you anything else:

```
IS THE ORDERING REAL?   metric=coverage  k=24 arms  N=20 items
  global test (permutation on within-item ranks): p = 0.0066 -> an arm effect exists
  Nemenyi critical difference = 8.13 rank positions; observed span = 7.20
  pairs distinguishable: 1 of 276
```

Three readings, all computed over the whole table at once:

- **Global test** — rank every arm *within* each item, then ask whether the average ranks
  are further apart than chance. On a real dataset most variance is "some items are hard
  for everyone" (66% here, against 3% between arms), and ranking inside the item is what
  removes it. If this fails, no ordering is supported and the output says so.
- **Nemenyi critical difference** — from the number of arms and items alone, how far apart
  two average ranks must be before that *pair* is distinguishable. Applied to every pair
  simultaneously, so it accounts for the fact that 24 arms means 276 comparisons and ~14
  of them will look significant by luck.
- **Rank intervals** — resample the items, re-rank everything from scratch, report where
  each arm lands. Context, not a pairwise claim; the critical-difference line is the claim.

What this deliberately does **not** do is walk down the table comparing each arm to a
running "leader". That is a sorting algorithm, not a comparison: walked bottom-up instead
of top-down it partitions the same arms differently, and it once supported both a finding
and its retraction from one dataset.

## Re-measuring without re-running

Scores are arithmetic over outputs, and outputs are the expensive part. So a metric change
should not cost a sweep:

```
make rescore DATASET_ID=my_v1 MATCH=_v2
EVAL_RUNS_DIR=data/runs-rescored make leaderboard DATASET_ID=my_v1
```

Rescored runs go to a separate directory carrying `rescored_from`, `rescored_at` and the
scorer's sha256, so a recomputation can never be mistaken for a measurement. Latency, cost
and token counts are carried across untouched — they describe the call that happened, not
how it was later measured.

This exists because a scorer bug survived two full sweeps: checking it would have cost a
third. When verifying a measurement is expensive, it does not get verified.

## Do you trust your reference?

Most of the time there is no gold, so a strong model writes the references — "silver" — and
you rank candidates against those. This asks whether that ranking matches the one real
ground truth would have given:

```
make silver-calibrate DATASET_ID=my_v1 REF_MATCH=_v1 ARM_MATCH=_v2
```

It costs nothing, because "author silver with model X using the same prompt and settings as
the arms" is exactly what X already produced — so every arm on disk is a candidate author
and all of them are tried.

Read the result against the **ceiling** it prints. Two runs of the same arms against the
same gold do not rank identically either, so that retest correlation is the best any proxy
could score. On the bundled example: ceiling 0.93, silver authors 0.00–0.69 (mean 0.35).

The number that matters most is the last one. Grouping arms by `family`, a silver author
**promotes models of its own kind by ~8 rank positions, for 22 of 24 authors** — and
excluding the author's own row does not remove it, because the bias is not an author
scoring itself, it is an author rewarding its own kind's style. A silver-ranked leaderboard
is not merely noisier than a gold one; it is biased in a direction you can predict from who
wrote it.

## Scoping a dataset that has grown

A dataset accumulates arms across config versions, and v1 and v2 of one arm are different
measurements that must not share a row:

```
make leaderboard DATASET_ID=my_v1 MATCH=_v2     only the v2 arms
EVAL_RUNS_DIR=<dir> make ...                    run or read somewhere else
```

`EVAL_RUNS_DIR` is how a smoke pass avoids adding repeats to a real sweep's arms and
silently moving numbers you have already reported. Use it whenever you are validating a
change rather than measuring something.

**Deleting old runs to make a table shorter is not the alternative to scoping it.** That is
how 18 arms of paid results were lost during this harness's own development.

## Docs

| | |
| --- | --- |
| **[INTEGRATION.md](docs/INTEGRATION.md)** | plugging in an existing system; getting ground truth when you have none |
| **[RUNBOOK.md](docs/RUNBOOK.md)** | the operational walk, step by step, with the reasoning |
| **[CONCEPTS.md](docs/CONCEPTS.md)** | why each refusal exists, and the failure it prevents |

---

## The judge panel

The harness this grew around, unchanged. Given many candidate runs: narrow to
finalists (top-K per stratum + floor + global cap), score each with an LLM
judge, **abort mid-run** if a cost cap is hit, aggregate to per-dimension means,
and flag finalists where two judges disagree.

```bash
make judge                                  # FakeJudge — no API key
ANTHROPIC_API_KEY=... python runner.py --config config.example.yaml
```

Use it when the cheap metric is known to be biased in your domain but you have
an expensive judge you trust: cheap metric for triage, judge for the answer.

Cost discipline is a **mid-run abort, not a pre-flight estimate** — estimates
are usually wrong, and an abort stops the bill the moment the cap is hit, with
partial results preserved so a blown budget still yields a usable report.

---

## Files

| Path | What it is |
| --- | --- |
| `Makefile` | the verbs — start with `make help` |
| `scripts/adapter.py` | **the integration seam** — the file you edit |
| `scripts/dataset_create.py` | freeze a selection into a `dataset_id` |
| `scripts/materialize.py` | build run inputs, verifying every hash |
| `scripts/reference_create.py` | author gold/silver ground truth |
| `scripts/experiment_run.py` | run an arm → scores, cost, speed, provenance |
| `scripts/compare_runs.py` | compare two runs, or refuse |
| `scripts/promote_baseline.py` | run → baseline, or refuse |
| `scripts/validate_tree.py` | six integrity checks |
| `scripts/list_runs.py` | what runs and baselines exist |
| `schemas/` | the three contracts: dataset, metrics, baseline |
| `runner.py`, `judges.py` | the judge panel |

Bundled providers: `echo` (no network), `anthropic`, and anything
OpenAI-compatible including OpenRouter. Most real integrations delete all three
and call one function.

---

## See also

- [`docs/cloud-ai-workflow.md`](../../docs/cloud-ai-workflow.md) — the cost-gate
  doctrine this composes with.
- [`examples/claude-api-with-caching/`](../claude-api-with-caching/) — the
  simpler companion. If your eval is "run a prompt once and look at the
  output", use that; this is overkill.
