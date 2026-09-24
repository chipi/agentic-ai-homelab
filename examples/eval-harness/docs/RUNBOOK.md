# Runbook — from raw inputs to a defensible baseline

Follow this top to bottom. It is the same path `make help` lists, with the
reasoning attached. You should not need to open a script.

---

## 0. Prove it works before you touch it

```bash
make demo
```

That freezes a dataset from the bundled samples, materializes it, runs an
experiment three times, and validates the tree. No API key. If that works, the
skeleton is wired correctly and anything that breaks later is your change.

---

## 1. Put your inputs in `data/sources/`

Anything file-shaped: transcripts, tickets, documents, diffs, JSON payloads.

**`sources/` is immutable.** Once an item is in a dataset, its bytes are what a
published number was measured on. If an input genuinely changes, that is a *new*
dataset (`_v2`), never an edit in place. This is not bureaucracy — editing a
source silently invalidates every number already reported against it, and
nothing will tell you.

---

## 2. Freeze a selection

```bash
make dataset-create DATASET_ID=my_v1
make dataset-create DATASET_ID=my_smoke_v1 ARGS="--limit 5"     # a fast cut
```

This writes `data/datasets/my_v1.json`: the item list plus a **sha256 per item**.

The `dataset_id` is the comparison contract. Every run records it, and
`run-compare` refuses to compare across two different ones. Name it for what it
*is* (`support_tickets_2026q1_v1`), not for what you were doing at the time
(`test2`).

---

## 3. Materialize

```bash
make dataset-materialize DATASET_ID=my_v1
```

Copies the items into `data/materialized/<dataset_id>/` and **re-verifies every
hash**. If a source changed since the freeze, this fails loudly rather than
quietly measuring different bytes than the dataset claims.

`materialized/` is derived. Delete it any time; `make dataset-materialize`
rebuilds it. If something in there cannot be rebuilt, it is in the wrong place.

---

## 4. Point the runner at your system

Edit **one function**, `run_item()` in `scripts/experiment_run.py`:

```python
def run_item(item, item_path, params):
    result = your_system.process(item_path.read_text(), **params)
    return {"accuracy": score(result), "latency_ms": result.elapsed_ms}
```

Whatever keys you return become the metric names. The aggregate is their mean
across items.

Then describe the experiment in `data/configs/<name>.yaml`:

```yaml
config_id: my_config_v1
dataset_id: my_v1
params:
  model: your-model
  temperature: 0.0
```

---

## 5. Measure the arm's own noise — **before** you compare anything

```bash
make experiment-run CONFIG=data/configs/my_config.yaml REPEAT=3
```

Output ends with:

```text
Arm spread over 3 repeats (max - min on identical input):
  accuracy     spread=0.043888   treat deltas below 0.043888 as noise
```

**This step is the difference between measuring and guessing.** A real example
from the project this came from: one model showed **0.058 spread on
byte-identical input** — wider than most of the deltas people were arguing
about. Without knowing that, every one of those arguments was about noise.

If the spread is `0.000000`, the arm is deterministic and any delta is real.
Write the number down; you need it in step 7.

---

## 6. Run the arms you want to compare

```bash
make experiment-run CONFIG=data/configs/arm_a.yaml
make experiment-run CONFIG=data/configs/arm_b.yaml
make runs-list
```

A run is only attributable if it knows its build. `runs-list` marks runs from a
dirty tree with `*` — their `build.ref` does not describe what actually ran.
For anything you intend to promote, commit first and re-run.

---

## 7. Compare, with the noise floor you measured

```bash
make run-compare BASE=<run_id> CAND=<run_id> NOISE=0.043888
```

Read the verdict column, not the delta. A `+0.02` that is below your measured
spread is **noise**, and the tool says so. Without `NOISE=` it nags, because a
delta judged against nothing is not evidence.

It refuses outright if the two runs used different `dataset_id`s.

---

## 8. Promote — a decision, not a copy

```bash
make promote RUN=<run_id> REASON="beat prev baseline by 6% on my_v1 n=40, spread 0.004"
```

Refused if the run came from a dirty tree, or if the reason is a single word.
Both refusals exist for the same reason: in six months, *"why is this the
baseline?"* must have an answer.

The previous baseline is archived under `data/baselines/superseded/`. A baseline
is never edited, only superseded.

```bash
make baselines-list
```

---

## 9. Validate before you trust anything

```bash
make validate
```

Six checks: schema conformance, every run's `dataset_id` resolves, every run
identifies its build, materialized copies still match their hashes, no two
configs reporting byte-identical scores, and no baseline pointing at a deleted
run.

The duplicate-score check catches a specific and nasty failure: two
independent arms do not agree to full float precision. When they do, one of them
is not its own measurement — a copied number, a mis-wired arm, a cached result.

Run it in CI. It exits non-zero.

---

## 10. Optional — the judge panel

When the cheap metric is biased in your domain but you have an expensive judge
you trust:

```bash
make judge      # FakeJudge, keyless
```

Triage on the cheap metric, decide with the judge, cost-capped with a mid-run
abort that preserves partial results. Knobs in `config.example.yaml`; the
reasoning is in the main README.

---

## Choosing what to evaluate against

The **system under test** is recorded as `build.ref` by `build_info()` in
`scripts/_common.py`. It defaults to this tree's git SHA, which is right only if
this tree *is* the system.

If you are evaluating something installed — a package, a container, a service —
change `build_info()` to report *that* thing's identity: a version, an image
digest, a pinned dependency ref. Pin it explicitly rather than tracking
`latest`: an eval against a moving target measures the target's movement, and
you will spend a day attributing it to your change.

---

## When a number looks wrong

In order, because each is cheaper than the next:

1. `make validate` — is the tree even consistent?
2. `make runs-list` — was the run from a dirty tree?
3. `REPEAT=3` — is the delta inside the arm's own spread?
4. Same `dataset_id` on both sides? (`run-compare` refuses, but check the ids)
5. Did a source change? `make dataset-materialize --force` re-verifies hashes.

Most "regressions" are one of the first three.
