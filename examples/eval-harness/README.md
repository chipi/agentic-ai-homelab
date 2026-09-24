# Eval harness — a drop-in skeleton for evaluating a system against frozen data

Copy this directory into a project, point it at your inputs, and you have the
whole loop: a **frozen dataset**, **runs** that know what produced them,
**comparisons** that refuse to lie, **baselines** you can defend, and an
**LLM judge panel** with a cost cap.

```bash
make demo        # the entire loop on bundled sample data — no API key needed
make help        # the verbs, in the order you need them
```

It is deliberately small. Six scripts, three schemas, one Makefile. You should
be able to read all of it in a sitting, because you will need to change one
function in it.

---

## The idea

Most eval tooling produces numbers. The hard part is making numbers *mean*
something, and that comes down to three inputs:

| input | recorded as | without it |
| --- | --- | --- |
| **system under test** | `build.ref` on every run | you cannot tell a code change from an eval change |
| **instrument** | `config_id` | you cannot tell a config change from a code change |
| **data** | `dataset_id` | you cannot compare anything to anything |

Every run here records all three. The tooling then **refuses** the comparisons
that would be meaningless — which is the part that makes it worth having:

- different `dataset_id` → refused outright
- a delta smaller than the arm's own run-to-run spread → reported as noise
- promoting a run from a dirty tree → refused
- promoting without a reason → refused

> A metric compared across two different `dataset_id`s is not a comparison.
> It is a coincidence.

---

## The loop

```text
data/sources/        your raw inputs — IMMUTABLE, never edited in place
      ↓  make dataset-create
data/datasets/       a frozen selection + a sha256 per item. This is the contract.
      ↓  make dataset-materialize
data/materialized/   derived run inputs, every hash re-verified
      ↓  make experiment-run
data/runs/           metrics.json (scores + dataset_id + config_id + build) + predictions
      ↓  make run-compare / make judge
data/baselines/      make promote — the number future work is judged against
```

`make validate` checks the whole tree at any point.

---

## Wiring in your system

**One function.** `run_item()` in `scripts/experiment_run.py` is the only place
that knows what is being evaluated. It takes an item and returns a dict of
numbers; whatever keys you return become your metrics.

```python
def run_item(item, item_path, params):
    result = your_system.process(item_path.read_text(), **params)
    return {"accuracy": score(result), "latency_ms": result.elapsed_ms}
```

Everything else — freezing, hashing, provenance, aggregation, refusals — is
bookkeeping that does not care about your domain.

**`build_info()`** in `scripts/_common.py` identifies the system under test. It
defaults to the git SHA of this tree; change it to whatever actually identifies
your system — a package version, an image digest, a pinned dependency ref.

---

## Files

| Path | What it is |
| --- | --- |
| `Makefile` | the verbs — start with `make help` |
| `docs/RUNBOOK.md` | the walk-through, with the reasoning |
| `scripts/dataset_create.py` | freeze a selection of sources into a `dataset_id` |
| `scripts/materialize.py` | build run inputs, verifying every hash |
| `scripts/experiment_run.py` | run a config against a dataset → a run dir |
| `scripts/compare_runs.py` | compare two runs, or refuse |
| `scripts/promote_baseline.py` | run → baseline, or refuse |
| `scripts/validate_tree.py` | six integrity checks over the tree |
| `scripts/list_runs.py` | what runs and baselines exist |
| `schemas/` | the three contracts: dataset, metrics, baseline |
| `runner.py` | the judge panel: promote → judge → aggregate → report |
| `judges.py` | `Judge` protocol, `FakeJudge` (keyless), `LLMJudge` |
| `config.example.yaml` | the judge panel's knobs |

---

## The judge panel

`runner.py` is the original harness this skeleton grew around, and it still
does exactly what it did: given many candidate runs, narrow them to finalists
(top-K per stratum + floor + global cap), score each with an LLM judge, stop
mid-run if a cost cap is exceeded, aggregate to per-dimension means, and flag
finalists where two judges disagree.

```bash
make judge                                  # FakeJudge, no API key
ANTHROPIC_API_KEY=... python runner.py --config config.example.yaml
```

Use it when the cheap metric is known to be biased in your domain but you have
an expensive judge you trust: cheap metric for triage, judge for the answer.

**Cost discipline is a mid-run abort, not a pre-flight estimate.** Estimates are
usually wrong; an abort guarantees the bill stops the moment the cap is hit, and
partial results are written so a budget-blown sweep still yields a usable
report.

---

## Adapting

| Want to change | Edit |
| --- | --- |
| what an item's score is | `run_item()` in `scripts/experiment_run.py` |
| what identifies your build | `build_info()` in `scripts/_common.py` |
| what counts as an item | `--glob` on `make dataset-create` |
| which integrity rules apply | the `vN_*` functions in `scripts/validate_tree.py` |
| promotion rule for the judge panel | `promote_finalists` in `runner.py` |
| judge interface | the `Judge` protocol in `judges.py` |

---

## See also

- [`docs/cloud-ai-workflow.md`](../../docs/cloud-ai-workflow.md) — the cost-gate
  doctrine this composes with: env-driven soft and hard limits at the provider
  client layer.
- [`examples/claude-api-with-caching/`](../claude-api-with-caching/) — the
  simpler companion for single-prompt work. If your eval is "run a prompt once
  and look at the output", use that instead; this is overkill.
