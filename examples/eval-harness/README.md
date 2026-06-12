# Eval harness — provider-agnostic, cost-capped, judge-paneled

Provider-agnostic harness for running LLM evals at scale. Shape extracted
from `podcast_scraper-FUTURE/src/podcast_scraper/evaluation/finale_runner.py`
(633 lines) and genericized down to the four operations that compose:

1. **Promote** — given a pool of candidate runs ranked by a primary
   metric, narrow it down to finalists via top-K-per-stratum + floor +
   global cap, with a carte-blanche override for "always include this
   one even if its cheap metric says no".
2. **Judge** — for each finalist, score every item with an LLM judge.
   Stop mid-run if a cost cap is exceeded; preserve partial results so
   a budget-blown sweep still yields a usable report.
3. **Aggregate** — reduce per-item scores to per-dimension means. If a
   cross-judge is configured, compute pairwise agreement and flag
   contested finalists.
4. **Report** — write `finalists.jsonl`, `report.json`, and `report.md`
   to a stamped output dir.

Each step is one function. Compose them in `runner.py`; swap judges in
`judges.py`; tune knobs in `config.example.yaml`. The harness is ~250
lines total.

## When to use this shape

- You have **many candidate runs** of an experiment (model × prompt ×
  hyperparam sweeps) and want to pick winners.
- The cheap metric (ROUGE / cosine / BLEU / exact-match) is **known to
  be biased** in your domain, but you have an LLM judge that's expensive
  but trustworthy. You want to use the cheap metric for triage and the
  LLM judge for the final answer.
- You need **cost discipline** baked in — at scale, an eval sweep can
  blow $100s in minutes without it.
- You want **adversarial verification** for high-stakes calls — two
  independent judges, contested-flag when they disagree.

If your eval is "run a prompt once and look at the output", this is
overkill. Use `examples/claude-api-with-caching/` instead.

## Files

| File | What it holds |
|---|---|
| `runner.py` | The 4 operations + a `main()` that wires them via a YAML config |
| `judges.py` | Judge protocol + `FakeJudge` (deterministic, for tests) + `LLMJudge` (Anthropic-shaped) |
| `config.example.yaml` | All the knobs documented inline |
| `requirements.txt` | `anthropic`, `pyyaml` |

## Run the demo

The harness ships with `FakeJudge` so it runs without any API key —
exercises the promotion + aggregation paths against synthetic scores.

```bash
cd examples/eval-harness
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python runner.py --config config.example.yaml --use-fake-judge
```

Switch to a real Claude judge:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python runner.py --config config.example.yaml
```

Output lands in `out/<tag>/` per the config.

## Adapting

The four operations are intentionally narrow. Each one is one
function, ~30-50 lines. To adapt:

| Want to change | Edit |
|---|---|
| Primary ranking metric (default: `primary_score`) | `RunCandidate` field + `load_run_candidate` |
| Stratification rule (default: substring match on `run_id`) | `_classify_stratum` in `runner.py` |
| Promotion rule (default: top-K + floor + global-cap) | `promote_finalists` in `runner.py` |
| Judge interface | Adapt the `Judge` protocol in `judges.py` |
| Cross-judge agreement threshold (default: 0.5 on a 1-5 scale) | `aggregate_finalist` in `runner.py` |
| Output format | `write_report` in `runner.py` |

Real-world ratio: the shape stays; the specifics swap. The
podcast_scraper version of this harness has 633 lines because of
domain wiring (transcript materialization, multi-judge orchestration,
NER scoring, embedding-cosine handling). The shape underneath those
is what's here.

## Cost discipline notes

The cost cap is a **soft mid-run abort**, not a pre-flight estimate.
This is deliberate:

- Pre-flight estimates are usually wrong (token counts vary,
  cache hits change pricing).
- Mid-run abort guarantees the bill stops growing the moment the cap
  is hit, even if the estimate was way off.
- Partial results are written every N items so a budget-blown sweep
  yields *something*. A sweep that promotes 12 finalists but only
  scores 4 of them is still useful — the report tells you which 4.

The pattern composes with the broader [`docs/cloud-ai-workflow.md`](../../docs/cloud-ai-workflow.md)
cost-gate discipline — env-var-driven soft + hard limits at the
provider-client layer.

## See also

- [`docs/cloud-ai-workflow.md`](../../docs/cloud-ai-workflow.md) — Pillar 3
  narrative including prompt-caching, batch API, cost-gate doctrine.
- [`examples/claude-api-with-caching/`](../claude-api-with-caching/) —
  the simpler companion for single-prompt work.
- Source shape: `podcast_scraper-FUTURE/src/podcast_scraper/evaluation/finale_runner.py`
  (not in this repo; operator-local reference).
