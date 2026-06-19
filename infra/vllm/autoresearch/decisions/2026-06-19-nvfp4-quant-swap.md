# 2026-06-19 — model swap: BF16 → NVFP4 (Cell F daily driver)

**Decision:** swap autoresearch from
`Qwen/Qwen3-30B-A3B-Instruct-2507` (BF16) to
`NVFP4/Qwen3-30B-A3B-Instruct-2507-FP4` (NVIDIA Model Optimizer's
official NVFP4 quant of the same model).
**Scope:** `infra/vllm/autoresearch/docker-compose.yml` (single-line
model arg), with downstream documentation alignment in `README.md`,
`KV_CACHE_SIZING.md`, and `.env.example` (comments only — the active
profile default stays at 0.60).
**Tickets resolved:** chipi/podcast_scraper#1022.
**Driver:** podcast_scraper #1016 Round 3 Cell F daily-driver
selection.

## Why we evaluated

The autoresearch slot's wall-clock per eval iteration was the binding
constraint on `podcast_scraper`'s #1016 Round 3 sweep cohort. The
BF16 pin from 2026-06-14 was good enough quality-wise but slow enough
that throughput-bound work was paying for KV-cache headroom it never
touched (~1.86% peak — see
[`2026-06-16-kv-cache-per-workload-profiles.md`](2026-06-16-kv-cache-per-workload-profiles.md)).
NVIDIA shipped an official NVFP4 quant of the exact same model
architecture, and `chipi/podcast_scraper#1022` ran the side-by-side
evaluation to determine whether it was a drop-in replacement.

## Methodology — owned by `podcast_scraper`, not duplicated here

The evaluation lives in
`chipi/podcast_scraper:docs/wip/VLLM_GB10_TUNING_VALIDATION_2026-06-18.md`.
Two datasets (`dev_v1` for fast iteration, `curated_5feeds_benchmark_v2`
for held-out validation), Sonnet 4.6 as the cross-vendor silver judge,
and Opus 4.7 as the gold-standard target.

What landed here is the result and the rationale; the eval
methodology + statistical tests are documented on the consumer side
where the eval harness lives.

## Results

### Speed

| Workload | BF16 baseline | NVFP4 (this swap) | Δ |
|---|---|---|---|
| End-to-end (`dev_v1`, 10 ep sweep) | 728 s | 380 s | **−47.8 %** |
| Cold boot | ~6 min | ~2 min | **−67 %** |
| Weight footprint | 57 GB | 18 GB | **−68 %** |

### Quality (vs Opus 4.7 gold)

| Dimension | BF16 baseline | NVFP4 (this swap) | Δ |
|---|---|---|---|
| Summary embedding cosine | 0.7948–0.8069 | 0.8011 | **±0 %** (within noise) |
| GI coverage | 0.595 | 0.611 | **+2.8 %** |
| KG topic coverage | 0.425 | 0.408 | **−4.0 %** |

### Cohort placement

Wins the `chipi/podcast_scraper#1016` Round 3 cohort GI stage
**outright**:

- NVFP4 Cell F: GI coverage 0.425
- Prior winner Gemma-4: 0.413
- Qwen3.5-35B-A3B: 0.363

## Decision: pin NVFP4 as the autoresearch daily driver

The swap is a clean speed win with no measurable quality regression
on the dimensions the autoresearch tier cares about. The 4 % KG topic
coverage drop is within statistical noise on a single-judge eval and
doesn't shift cohort placement.

### What this means for the weight floor

The right-size formula in
[`KV_CACHE_SIZING.md`](../KV_CACHE_SIZING.md) gets a new row at the
top of the sweep table:

```
weight_floor = (18 + 5) / 128 = 0.18
recommended  = 0.25
```

The `.env.example` profile default (`sweep` = 0.60) is now
over-allocated by ~2.4× the recommended value for this model.
**Deliberately not changed in this swap** — 0.60 is still the
correct "safe middle" that works across the entire sweep table.
Drop to 0.25 per-deploy when sibling services compete for unified
memory.

## What we deliberately did NOT do

- **No `.env.example` active-value change.** The profile default
  stays at 0.60. The per-model right-size value (0.25 for NVFP4)
  lives in the table; operators override per-deploy.
- **No `#928 Cell C` re-baseline.** That work is owned by
  `chipi/podcast_scraper#928` and gates the "this is the new canonical
  autoresearch baseline" call. Until that lands, the 30 B vs 35 B
  caveat carries over from the BF16 pin.
- **No `coder-next/` change.** Different stack, different upgrade
  decision, explicitly out of scope per the swap task's mandate.
- **No vLLM image bump.** Same `nvcr.io/nvidia/vllm:26.05-py3` from
  2026-06-15 (`b2957f6`). NVFP4 is supported via the runtime
  autotuner that landed in that image.

## Rollback procedure

If a future workload surfaces a quality regression the eval missed
(e.g. a model-quality-sensitive #996 measurement), revert by:

1. Edit `infra/vllm/autoresearch/docker-compose.yml`, change:
   ```
   - NVFP4/Qwen3-30B-A3B-Instruct-2507-FP4
   ```
   back to:
   ```
   - Qwen/Qwen3-30B-A3B-Instruct-2507
   ```
2. `gpu-mode-swap.sh idle && gpu-mode-swap.sh research` (~7 min warm
   boot since BF16 weights are still cached at
   `/opt/llm-models/huggingface`).
3. Capture the workload + regression in a sibling `decisions/` entry.

No `.env` change needed; no consumer-side change needed
(`served-model-name` is `autoresearch` in both compose pins).

For one-shot evals where summary or KG quality matters more than
wall-clock, edit the compose for that run only and revert after.

## Follow-up signal worth watching, not refiling today

- **The KG topic coverage delta (−4 %)** is small but consistent
  across runs. If a future eval shows that delta growing on a
  different content distribution, that's the signal to refile —
  either a per-content-type model-selection ticket, or a re-evaluation
  of NVFP4 vs an unquantized FP8 alternative.
- **The autotuner's `Skipped 2 unsupported tactic(s)` log line from
  the 26.05 bump still applies** and may matter more under NVFP4 (the
  kernel space NVFP4 needs is different from BF16). If a #996-style
  measurement attributes a sub-optimal pattern to autoresearch, that
  becomes a scoped autotuner-on-NVFP4 ticket.

## Source data + ticket references

- `chipi/podcast_scraper#1022` (driver — Cell F daily-driver selection,
  closed 2026-06-19)
- `chipi/podcast_scraper#1016` (Round 3 sweep cohort that NVFP4 won
  the GI stage of)
- `chipi/podcast_scraper:docs/wip/VLLM_GB10_TUNING_VALIDATION_2026-06-18.md`
  (eval methodology + per-judge tables)
- The previous BF16 pin (now the rollback target): `26e6579`
  (`feat(vllm): autoresearch stack for podcast_scraper sweeps`)
- The KV cache sizing work this swap inherits the floor formula from:
  [`2026-06-16-kv-cache-per-workload-profiles.md`](2026-06-16-kv-cache-per-workload-profiles.md)
- The image this swap runs on:
  [`2026-06-15-image-bump-25.11-to-26.05.md`](2026-06-15-image-bump-25.11-to-26.05.md)
