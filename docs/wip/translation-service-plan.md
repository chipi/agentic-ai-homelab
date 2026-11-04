# Translation as a tool: service, MCP, and a model bakeoff

**Status:** proposal, 2026-11-04, from the operator's idea in the homelab session. For an agent to pick up.
Nothing is built yet. Write it up as an RFC (next free number, likely RFC-0009) before building, with the
alternatives and costs below.

**The operator's goal:** make the translation model a tool that other AIs and harnesses can call, and
compare it with other models in a bakeoff. The callers named: **the X3 assistant, the podcast pipeline,
and Claude Code sessions**.

## What exists today (checked 2026-11-04)

| Fact | Source |
|---|---|
| The model is **TranslateGemma 12B** (`google/translategemma-12b-it`), vLLM on the DGX at `:8005`, ~29 GiB | `infra/dgx/bin/README.md` (`GPU_MODE_TRANSLATE_MODEL`) |
| Its stack lives in **chipi/infra** `infra/ai/vllm/translate/` (moved there 2026-10-30), image `nvcr.io/nvidia/vllm:26.05-py3`, **`--max-model-len=4096`** (sized for concurrency, not long requests; re-sized 2026-09-30, agentic-ai-homelab #81) | `/work/infra/main/infra/ai/vllm/translate/docker-compose.yml` |
| It runs **only in GPU modes `prod` and `ollama`**; stopped in `research-vllm`, `research-ollama`, `code`, `judging`, `free` | `infra/dgx/bin/README.md`, mode table |
| The podcast pipeline uses it (podcast_scraper#2342) through **three raw pass-through routes** in the mini's LiteLLM, not a model alias: `/v1/translate/v1/completions`, `/v1/translate/v1/models`, `/v1/translate/tokenize` → the DGX's `:8005`, `auth: false` (LiteLLM 1.96 only exempts exact paths). Callers must know TranslateGemma's own prompt format | `infra/litellm/config.yaml` ~line 265 |
| The X3 assistant plan already listed a `translate` alias for a later wave, with "verify chat completions and its prompt format first" | `docs/wip/x3-assistant-v1-plan.md` |
| **eval-harness already designed a machine-translation experiment** (not built): WMT24++ (`google/wmt24pp`, Apache-2.0, 55 en→X pairs, 998 rows each, post-edited references), en→de plus en→hr / en→sr; metrics **chrF** (sacreBLEU signature) and **COMET** (`Unbabel/wmt22-comet-da`, Apache-2.0, ~2.3 GB, CPU, must be pinned); free local baselines opus-mt, m2m100, madlad400-3b (avoid NLLB: non-commercial); calibration row opus-mt-tc-big-en-fr on FLORES (chrF 0.725 / BLEU 52.2); about **$5.4 per language pair for 24 arms**; known risk: COMET favours LLM-style output | `/work/eval-harness/main/research/internal/NEXT_EXPERIMENTS.md` §6 |
| Patterns to copy for tool access: the Grafana MCP and the hub's OpenAPI tools in both chat UIs (`infra/x3/assistant-ui-eval/apply-ui-config.py`); the Close Listening MCP | this repo; the podcast repos |

**Not checked:** which language pairs podcast_scraper#2342 translates; whether TranslateGemma serves chat
completions or only completions with its template; its current request volume and latency.

## The proposal

### 1. One translation service (the only new code)

A small HTTP service on the mini, next to LiteLLM (always on; the DGX and the X3 are not the place for a
dependency of prod).

- **One operation:** `translate(text, target, source?, glossary?)`, plus `detect_language(text)` and
  `languages()`.
- **Code does the parts models get wrong** (the lesson of the X3 assistant work, `docs/wip/x3-assistant-evals.md`:
  selection and formatting in code, the model only translates):
  - TranslateGemma's prompt format, so no caller needs to know it;
  - splitting long text into segments that fit 4096 tokens (sentence or paragraph boundaries) and joining
    the result;
  - calling the model **through the gateway**, so every call gets Langfuse traces, a key and a budget;
  - **availability, answered at once:** check the DGX's mode / `:8005/v1/models`; if the model is not up,
    use the fallback (see open question 3) and say so in the response, never wait for a timeout (a hung
    backend cost the X3 assistant ~31 s per call: `docs/wip/NEXT_STEPS.md`, X3 known gaps).
- **The model behind it is a config line**, so the bakeoff's winner can replace TranslateGemma without any
  caller changing.

### 2. The same service, three faces (one per caller)

| Caller | Face | Copy from |
|---|---|---|
| Claude Code sessions | **MCP server** (streamable HTTP over the tailnet; `claude mcp add`), a typed `translate` tool | the Close Listening MCP |
| X3 assistant (LibreChat, Open WebUI) | **MCP** for LibreChat, **OpenAPI** for Open WebUI, applied by `apply-ui-config.py` like the hub's tools | `infra/x3/assistant-ui-eval/`, `infra/homelab-home/openapi.json` |
| Podcast pipeline | plain **HTTP** to the service, replacing the three raw routes | its current call path |

The podcast pipeline moves **last**: it works in prod today, and moving it is the podcast session's change.

### 3. The bakeoff, in eval-harness (experiment §6, extended)

- **Arms:** TranslateGemma 12B (DGX), Qwen3-30B-A3B (the X3 assistant's model), one or two cloud models
  through the gateway, and §6's free baselines (opus-mt, madlad400-3b).
- **Two datasets:**
  - **WMT24++**, for comparability with published numbers;
  - **a small domain set** from the operator's own material (podcast transcript snippets in the pairs that
    matter), because a public benchmark does not show how a model handles that text. Labels: reference
    translations (post-edited) or a judge, decided with the eval-harness session.
- **Scores:** chrF and COMET for quality; **latency and throughput** at the concurrency the pipeline uses
  (the reason for the 4096 limit); cost per 1k segments.
- **Owner:** the `eval harness` session (it owns §6). The service gives it a stable endpoint to call.

### Order

1. Read the decisions below; work out the fallback (decision 3) in the RFC.
2. Build the service with its MCP and OpenAPI faces, on TranslateGemma; wire Claude Code and the X3 UIs.
3. In parallel: the bakeoff (eval-harness).
4. Pick the model from the bakeoff; swap it behind the service.
5. Move the podcast pipeline to the service (podcast session).

## Decisions (the operator, 2026-11-04)

1. **Languages: English into every language Orrery uses.** Orrery's `project.inlang/settings.json`
   (`/work/orrery/main`): base `en-US`, **13 targets: es, fr, de, pt-BR, it, nl, sr-Cyrl, zh-CN, ja, ko, hi,
   ar, ru**. The bakeoff covers all 13 pairs (en→X), not only §6's en→de / en→hr / en→sr.
   - **A domain set exists:** Orrery's texts in all 13 languages, `static/data/i18n/<locale>.{core,essays,
     fleet,glossary,missions,programs,science}.json`, with `en-US` as the source. **Not known:** who made
     those translations (people or a model). Find out before using them as references; a model-made
     reference favours that model.
   - **A glossary exists:** `<locale>.glossary.json` per language: a natural first use of the service's
     `glossary` parameter (consistent terms).
   - **Not checked:** that WMT24++ covers all 13 (it has 55 en→X pairs; check the exact codes, e.g. which
     Serbian script, and which Arabic and Chinese variants, against sr-Cyrl, ar, zh-CN).
   - English stays the language of the eval itself (questions, notes): the operator does not read Dutch
     (`docs/wip/x3-assistant-evals.md`).
2. **Where the code lives:** default **a folder in this repo** (e.g. `translate/`, next to the hub; it runs on
   the mini like the hub), the bakeoff in eval-harness. The picking-up agent may propose a separate repo
   with a reason.
3. **The fallback when the DGX is in another mode** (a paid cloud model, always there, or "unavailable",
   free, sometimes down): **the picking-up agent works it out** and puts the choice and its cost in the RFC.

## Rules that apply (from this repo and the operator)

- **Shared state:**
  - the mini's LiteLLM, the DGX's GPU modes and the prod pipeline are shared;
  - DGX changes and GPU mode switches need the operator's explicit go (`infra/dgx/AGENTS.md`, the
    `gpu-mode` skill);
  - Docker work on the mini follows `docs/recipes/dev-docker-engine.md`.
- **New dependencies, ports or tailnet nodes:** the operator agrees first. The X3 has a no-new-ports rule
  (`infra/x3/AGENTS.md`).
- **Keys:** a new LiteLLM key for the service is minted with the `mint-credential` skill and recorded in
  `docs/recipes/agent-access.md`.
- **Prompt and routing changes:** a change to how calls are routed or prompted gets a replay or an eval
  before it ships (the `replay-proven-fix` skill).
- **Pushing:** two checkouts push to `main` here (`/work/agentic-ai-homelab` and
  `/work/agentic-ai-homelab-fleet-evals`), so fetch and rebase before every push.
