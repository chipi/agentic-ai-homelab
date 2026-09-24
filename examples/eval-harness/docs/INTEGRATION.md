# Integrating your existing system

**The situation this is written for:** you have a working project. It has code
that does something — summarises, classifies, extracts, answers — and it has
data. What it does not have is evaluation. You change a prompt or swap a model
and you find out whether it helped by reading a few outputs and forming an
impression.

**What this costs you:** one function, and a YAML file per thing you want to
compare. No refactor. Your code does not move, does not get wrapped, does not
learn about this harness. The harness calls you.

---

## Where it goes

Copy this directory into your project as `eval/`:

```bash
cp -r eval-harness /path/to/your-project/eval
cd /path/to/your-project/eval
make demo        # proves the plumbing, no API key
```

Add `eval/data/runs/` and `eval/data/materialized/` to your `.gitignore` (the
bundled `.gitignore` already does this if you keep it).

It has **no dependency on your project** and your project has none on it. It
shells out to nothing, imports nothing of yours until you tell it to. That
isolation is deliberate: an eval harness that requires a refactor does not get
adopted, and one that entangles with the system it measures stops being able to
measure it.

---

## The one function

`scripts/adapter.py`, `call_system()`. It receives one item's text and the
config's `params`, and returns what your system produced:

```python
def call_system(text: str, params: Dict[str, Any]) -> Result:
    from myproject.summarise import summarise          # your existing code
    out = summarise(text, model=params["model"], temperature=params["temperature"])
    return Result(output=out.text,
                  tokens_in=out.usage.prompt_tokens,
                  tokens_out=out.usage.completion_tokens)
```

That is the integration. Everything else — freezing the dataset, hashing it,
recording which build ran, timing the call, aggregating, refusing bad
comparisons — is generic and already written.

**Return what you can, omit what you cannot.** Every field beyond `output` is
optional. If your system cannot report token counts, leave them out; the
harness records what arrives and skips what does not.

### If your system is not a function call

- **A CLI** — `subprocess.run([...], capture_output=True)`, return stdout.
- **An HTTP service** — `httpx.post(...)`, return the response field.
- **A pipeline stage** — call the stage directly. You usually do not need the
  whole pipeline; you need the stage you are changing.

If calling one stage in isolation turns out to be hard, that is worth knowing
on its own. A stage you cannot invoke without booting everything is a stage you
cannot measure, and that is a design finding, not an eval problem.

---

## The second function

`score()`, in the same file. It receives your system's output and the reference
for that item, and returns numbers:

```python
def score(output: str, reference: Optional[str]) -> Dict[str, float]:
    return {"rouge_l": rouge_l(output, reference),
            "has_required_section": 1.0 if "Summary:" in output else 0.0}
```

It is called with `reference=None` when no ground truth exists yet, so the same
adapter works before and after you have references.

**The shipped default is a placeholder.** Token-overlap F1 — enough to make the
loop run and rank arms crudely, not enough to defend a decision. Replace it
with what your domain actually rewards.

---

## What an "arm" is

A thing you want to compare, expressed as a config file — not a code edit:

```yaml
# data/configs/sonnet.yaml
config_id: sonnet_v1
dataset_id: my_corpus_v1
params:
  provider: anthropic
  model: claude-sonnet-4-6
  temperature: 0.0
  prompt: "Summarise the following transcript in 5 bullets:"
  usd_per_mtok_in: 3.0        # so the run records what it cost
  usd_per_mtok_out: 15.0
```

Four models to compare is four of these files, same `dataset_id`. The knobs
live in the config so an arm is reproducible and diffable; keeping them in code
means "which settings produced this number?" has no answer.

Prices live in the config too, deliberately: they change, and a run should
record the prices it was costed at.

---

## Getting ground truth when you have none

Most projects do not have it. The sequence that works:

1. **Pick your best model** and author references with it:
   ```bash
   make reference-create DATASET_ID=my_v1 CONFIG=data/configs/sonnet.yaml
   ```
   That writes **silver** — model-generated. It is not correct, it is
   *consistent*, which is enough to rank other arms against it.

2. **Review a few by hand.** Where you agree with the output, you now have gold.
   Re-run with `TIER=gold` once a human has actually checked them.

3. **Never let the distinction blur.** A run records which tier it scored
   against, and `make runs-list` shows it. Silver-scored numbers are for
   ranking arms against each other; they are not a claim about correctness, and
   publishing them as one is how eval loses credibility internally.

Cost control: `--limit 10`. Ten references is enough to rank four arms, and you
can extend later without re-authoring what you have.

---

## What you get, in exchange for that one function

| | |
| --- | --- |
| a frozen dataset | a `dataset_id` plus a sha256 per item — the thing that makes two numbers comparable |
| provenance | every run records which build produced it |
| noise floor | `REPEAT=3` reports the arm's own spread, so you stop promoting jitter |
| cost and speed | per item and totalled, alongside quality |
| refusals | cross-dataset comparisons, dirty-tree promotions and unreasoned baselines are blocked, not warned about |
| integrity | `make validate` fails CI on a tree that has drifted |
| a judge panel | when the cheap metric is biased and you need an LLM to adjudicate |

---

## The first hour, concretely

```bash
cp -r eval-harness your-project/eval && cd your-project/eval
make demo                                     # plumbing works

cp ../some/real/items/* data/sources/         # your data
make dataset-create DATASET_ID=pilot_v1 ARGS="--limit 10"
make dataset-materialize DATASET_ID=pilot_v1

$EDITOR scripts/adapter.py                    # call_system() -> your code
make reference-create DATASET_ID=pilot_v1 CONFIG=data/configs/best_model.yaml

make experiment-run CONFIG=data/configs/arm_a.yaml REPEAT=3   # + the noise floor
make experiment-run CONFIG=data/configs/arm_b.yaml
make run-compare BASE=<a> CAND=<b> NOISE=<the spread you just measured>
```

Ten items keeps the first pass cheap. Widen the dataset once the loop works —
and widen it *before* you trust any ranking, because ten items is a smoke test,
not evidence.

Then read [`RUNBOOK.md`](RUNBOOK.md) for the day-to-day, and
[`CONCEPTS.md`](CONCEPTS.md) for why the refusals exist.
