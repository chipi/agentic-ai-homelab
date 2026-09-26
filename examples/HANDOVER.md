# Handover — eval harness and the summarization example

State as of 2026-09-26. Facts and locations only; reasoning is in
[`EVAL_NOTES.md`](EVAL_NOTES.md), results in [`EVAL_REPORT.md`](EVAL_REPORT.md), forward
plan in [`EVAL_PLAN.md`](EVAL_PLAN.md).

## Repo state

Branch `eval/harness-provenance-and-journal`, 16 commits ahead of `main`, **not pushed**.
Working tree clean. `make ci` green in `examples/eval-harness`.

## What exists

| path | what |
|---|---|
| `examples/eval-harness/` | generic harness; imports nothing domain-specific |
| `examples/summarization-cnn-dailymail/` | 24-arm LLM example, own `uv` environment |
| `examples/EVAL_NOTES.md` | append-only journal, 43 entries |
| `examples/EVAL_REPORT.md` | results report |
| `examples/EVAL_PLAN.md` | plan; phases A–C done, D closed by A, E superseded |
| `examples/_shared/hf_identity.py` | HF model fingerprinting helper |

### Harness scripts added or changed this session

- `scripts/_retry.py` — retries wrapped around `call_system` and `warmup` by the harness.
  `EVAL_MAX_RETRIES` (8), `EVAL_RETRY_MAX_DELAY` (60s). Doubling backoff, capped, jittered.
  `FATAL` checked before `TRANSIENT`; status codes matched as whole numbers; `SystemExit`
  never retried. Adapters add markers via `TRANSIENT_MARKERS`. 8 assertions in `make ci`.
- `scripts/rescore.py` + `make rescore` — recompute scores from stored outputs, no API
  calls. Writes to a separate directory (`OUT=`, default `data/runs-rescored`, gitignored).
  Records `rescored_from`, `rescored_at`, `rescored_with.sha256`,
  `rescore_dropped_metrics`; nulls `fingerprint.hash` with `hash_invalid_because`.
- `scripts/silver_calibrate.py` + `make silver-calibrate` — measures whether a
  model-authored reference ranks arms as the trusted reference does. `--group-by` (default
  `family`) drives the sibling-bias report.
- `scripts/leaderboard.py` — `_significance` (Friedman permutation, Nemenyi CD,
  `P(1st)`/`P(top 5)`/`P(bottom 5)`), `_frontier` (Pareto), `--match` filter, warnings for
  low stored precision / absent `primary_metric` / mixed config versions.
- `scripts/experiment_run.py` — `Result.meta` carried to `_meta` in predictions and
  excluded from aggregation; `providers_seen`; `_portable_id` for adapter paths;
  `_adapter_primary_metric`, `_adapter_transient`; dirty-tree warning.
- `scripts/_fingerprint.py` — `declared` renamed `identity_declared`.
- `scripts/_common.py` — `EVAL_RUNS_DIR` override for `RUNS`; `build.dirty` is `None` when
  the ref is self-declared.
- `scripts/reference_create.py` — repo-relative paths, full `system_under_test` identity
  and params in the manifest.

### Example files

`adapter.py` (`call_system`, `score`, `warmup`, `fingerprint`, `PRIMARY_METRIC`,
`METRIC_KINDS`, `TRANSIENT_MARKERS`), `prompt.txt` (119 bytes, sha256 in every
fingerprint), `configs/arm_*.yaml` (24), `fetch.py`, `model_provenance.json`,
`pyproject.toml` + `uv.lock` + `.python-version`, `reference/`, `README.md`.

## Data on disk

- `data/runs/` — 72 v1 runs (old scorer), 72 v2 runs (24 arms × 3), plus demo runs.
  Gitignored.
- `data/runs-rescored/`, `data/runs-rescored-v1/` — both sweeps rescored with the current
  scorer. Gitignored; regenerate with `make rescore`.
- `data/sources/cnn_dailymail_20/`, `data/references/gold/cnn_dailymail_20/` — 20 articles
  and gold highlights. **Gitignored**: third-party corpus, download recipe only.
- `data/references/silver/cnn_dailymail_20/` — gitignored; manifest carries
  `provenance_incomplete`.

## Reproducing

```bash
cd examples/summarization-cnn-dailymail && uv sync && uv run fetch.py --n 20
cd ../eval-harness && cp .env.example .env         # LITELLM_BASE_URL, LITELLM_API_KEY
make sweep CONFIGS="../summarization-cnn-dailymail/configs/arm_*.yaml" REPEAT=3
make rescore DATASET_ID=cnn_dailymail_20 MATCH=_v2
EVAL_RUNS_DIR=data/runs-rescored make leaderboard DATASET_ID=cnn_dailymail_20
make silver-calibrate DATASET_ID=cnn_dailymail_20 REF_MATCH=_v1 ARM_MATCH=_v2
```

`rescore` is required before the significance numbers: run scores are written to 6
decimals and the leaderboard warns when it reads them.

Full sweep: 1440 calls, ~$1.45, ~80 min. Smoke subset (`qwen_s`, `glm_s`, `gemma_m`,
`mistral_s` at `REPEAT=1` with `EVAL_RUNS_DIR` set): ~$0.005.

## Headline results

Global test on `coverage`, k=24, N=20: p=0.0054, Nemenyi CD 8.13, span 8.57, 1 of 276
pairs separated (`deepseek_s` > `qwen_m`). Pairs separated by metric: `summary_words` 85,
`grounding` 50, `concision` 33, `rougeLsum` 10, `rouge1` 5, `coverage` 1.

Variance in `coverage`: articles 73.5%, arms 2.6%, residual 23.9%.

Determinism at temperature 0: 47/480 outputs identical across repeats (9.8%); 12 of 24
arms zero. `reasoning_tokens` 0 on all 1440 v2 calls.

Pareto frontier (coverage/cost/latency): 10 of 24 arms.

Silver calibration: retest ceiling ρ=+0.924; silver agreement −0.013..+0.697, mean +0.326;
sibling lift +7.4 rank positions, positive for 22 of 24 authors; ρ(author agreement,
sibling lift) = −0.70.

Cross-facet ranking and per-million costs: journal entry 41. Power analysis: entry 40.

## Known gaps

- No local/classical-ML arm. `pyproject.toml` describes the example as "ML vs LLM".
  Constraint recorded earlier: x86_64 macOS caps torch at 2.2.2 and `transformers` ≥4.56
  refuses `torch.load` below torch 2.6, so a pickle-only checkpoint cannot load here.
- No classification example.
- No judge wired into this example. Existing judge machinery is in
  `podcast-scraper-eval-data` (journal entry 43); harness `runner.py` / `make judge`
  is unused here.
- `mistral_l`'s three v2 runs carry a different `adapter.sha256` than the other 69
  (rate-limited, re-run after the adapter changed). All 72 v2 runs record
  `harness.dirty: true`.
- v1 runs record no `primary_metric` and no `providers_seen`.
- `providers_seen` is populated only for the 3 `mistral_l` v2 runs; provider capture
  postdates the rest of the sweep.
- `coverage` residual length correlation ρ(words) = +0.28; 205 of 1440 outputs are shorter
  than their reference and are never clipped.
- `_frontier` and `_fingerprint.py` beyond the scoring path are unreviewed.
- Nemenyi q-table spot-checked at k=10, 20, 24 only.

## Environment

- LiteLLM proxy at `127.0.0.1:4001`, 24 `eval-*` aliases; `infra/litellm/config.yaml`
  declares them, and the live registrations were made via `/model/new`.
- `.env` gitignored; `.env.example` tracked.
- `gitleaks` installed; every commit this session scanned clean.
- `examples/summarization-cnn-dailymail/.venv` is the interpreter used for all harness
  scripts in this session.
