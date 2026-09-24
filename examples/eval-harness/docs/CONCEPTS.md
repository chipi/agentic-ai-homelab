# Concepts — why this refuses things

The tooling is small. The discipline is the product. Each rule below is
enforced in code, and each exists because its absence produced a wrong answer
that nobody noticed.

---

## Three inputs, or the number means nothing

Every run records three things:

| input | field | drop it and… |
| --- | --- | --- |
| **system under test** | `build.ref` | you cannot tell a code change from an eval change |
| **instrument** | `config_id` | you cannot tell a config change from a code change |
| **data** | `dataset_id` | you cannot compare anything to anything |

`make validate` fails on a run missing any of them. `EVAL_BUILD_REF` sets the
first when the harness lives outside a git repo — a version, an image digest, a
pinned dependency ref, whatever actually identifies the thing being measured.

**Pin it.** An eval against a moving target measures the target's movement, and
you will lose a day attributing that to your change.

---

## `dataset_id` is a contract, not a label

> A metric compared across two different `dataset_id`s is not a comparison.
> It is a coincidence.

`make run-compare` refuses outright when the two runs disagree. Not a warning —
a refusal, because a warning above a number that looks authoritative gets
scrolled past.

This is also why `sources/` is immutable and why a dataset records a sha256 per
item. If an input changes under a frozen dataset, every number already reported
against it is describing bytes that no longer exist.
`make dataset-materialize` re-verifies every hash and fails loudly rather than
quietly measuring something else.

When data genuinely changes, that is a new version — `my_corpus_v2` — never an
edit in place.

---

## Measure the arm's own noise before believing any delta

```bash
make experiment-run CONFIG=... REPEAT=3
```

```text
Arm spread over 3 repeats (max - min on identical input):
  overlap_f1   spread=0.043888   treat deltas below 0.043888 as noise
```

A real case from the project this came from: an ASR model showed **0.058 WER
spread on byte-identical input** — wider than most of the deltas people were
arguing about. Every one of those arguments was about noise, and nobody knew,
because nobody had measured the arm against itself.

`run-compare` takes `NOISE=` and marks anything at or below it as noise. Omit it
and the tool nags, because a delta judged against nothing is not evidence.

`NOISE=0` is a real answer — it means the arm is deterministic — and is treated
differently from omitting the flag.

---

## Gold is not silver

| | |
| --- | --- |
| **gold** | human-authored or human-reviewed. The only thing you can honestly call correct. |
| **silver** | model-generated. Consistent, cheap, plentiful — and it encodes that model's opinion, including its mistakes. |

Silver is a legitimate starting point: it lets you **rank arms against each
other** today. It is not a claim about correctness, and a number scored against
it must say so.

Every run records `reference_tier`. The manifest beside the references carries
the caveat in full. The failure this prevents is quiet: silver numbers get
quoted in a decision six months later as though they were ground truth, and the
model that authored them is the one being evaluated.

---

## Cost and speed are part of quality

A run records `latency_ms`, `tokens_in`, `tokens_out` and `cost_usd` per item,
and totals for the ones you are billed for. "Model B scores higher" and "model
B scores higher and costs 4× per item" are different findings, and only one of
them is a decision.

Prices live in the experiment config, not in code, so a run records the prices
it was costed at. A figure computed from today's price list is not comparable to
one from last quarter without saying so.

---

## A baseline is a decision

`make promote` refuses three things:

- a run from a **dirty tree** — its `build.ref` does not describe what ran
- a run whose **build is unknown** — a different and worse problem, so it takes
  its own flag
- a **one-word reason** — because *"why is this the baseline?"* must have an
  answer in six months

Baselines are frozen. Promoting a new one archives the old under
`superseded/` rather than overwriting it.

---

## Two arms cannot agree to full precision

`make validate` fails when two different configs report byte-identical scores on
the same dataset. Independent arms do not agree to seventeen significant
figures; when they do, one of them is not its own measurement — a copied number,
a mis-wired arm, a cached result.

This check exists because exactly that happened: a published figure for one
model turned out to be another model's output, identical to the last digit,
sitting in a report for months.

---

## Why so many refusals

A tool that always produces a number teaches people to trust numbers. The
refusals are the part that makes the numbers worth trusting — they are the
difference between a measurement and a plausible-looking figure.

If a refusal is wrong for your situation, override it explicitly and say why in
the reason field. That override is then recorded, which is the point.
