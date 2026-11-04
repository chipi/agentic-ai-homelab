# X3 assistant: what to evaluate, with the eval harness

**Status:** to do, with the operator, as a later session using
[eval-harness](https://github.com/chipi/eval-harness). **Written:** 2026-11-04, at the end of RFC-0008's
step 1 and most of step 2 ([plan](x3-assistant-v1-plan.md)).

This note lists what we want to evaluate across the RFC-0008 work, and for each goal: the dataset, how
items get labelled, how answers are scored, and what we already have. It is a starting point to discuss,
not a design: the harness's own concepts (datasets from sources, `adapter.py` with `call_system` and
`score`, gold/silver references, `--repeat`, the leaderboard, judges validated against people) decide the
final shape.

## What we have learned so far (the reasons for these goals)

- **Grounding works only when code computes the answer.** "List 25 GlitchTip issues and filter by date"
  failed in both chat UIs (3–6 of 13 named, or "none"); once the hub computed the list
  (`status.json` `errors`), 6/6 runs were complete. The same rule made the H4/H5 questions pass.
- **Tool use is the weakest link of the 30B model:** invented arguments (`sort=newest`, made-up filters),
  retry loops (15 identical failing calls in 3.5 minutes), preferring Grafana over the status tool until
  the prompt said otherwise, and answering "no errors" after a failed call.
- **The UI changes the score with the same model and prompt:** before the prompt fixes, LibreChat 12/13 vs
  Open WebUI 3/13 on H4/H5; after, 39/39 vs 32/39 over three runs. Open WebUI misread
  `podcast.state` as amber in 3 of 3 runs. Not explained yet (how each UI passes tool results is the
  first suspect; Langfuse has the exact requests).
- **One run is not a result:** the same UI scored 8/13 and 3/13 on consecutive runs.
- **The Langfuse judge is useful and inconsistent:** it named both wrong claims in a briefing opening
  (0.78), then gave 1.0 to an opening with the same kind of wrong claim.
- **Context and serving matter:** 32k overflowed with 22 tools plus a tool result (`LITELLM-1C/1D`); a
  hung X3 costs ~31 s on every call; Home Assistant and the gateway reloaded the model when their context
  sizes differed.

## Goals

| # | Goal | Question it answers |
|---|---|---|
| G1 | **Grounded answers** in the chat | Does the assistant answer the operator's questions with the right facts? |
| G2 | **Tool use** | Does it pick the right tool and call it with valid arguments, without loops? |
| G3 | **Briefing faithfulness** | Does the morning briefing's opening say only what its facts support? |
| G4 | **Panel descriptions** (Grafana LLM app) | Are generated panel descriptions correct and useful? |
| G5 | **Judge reliability** | Can we trust the Langfuse LLM-as-a-judge scores (G3) and any other judge? |
| G6 | **Home answers** (Home Assistant) | Does Assist answer from the right entity, with no action attempted? |
| G7 | **System comparisons** | Which UI, prompt, context size and serving path give the best results, at what latency and cost? |
| G8 | **Model comparison** | Which model should run on the X3 (and as the failover) for these jobs? |

G1–G6 measure the work. G7 and G8 reuse the same datasets with different arms.

## Datasets, labels and scoring per goal

### G1 — grounded answers (chat: H4, H5, H2-errors; later H6, H7)

- **Items:** questions in the operator's words, per use case. Existing: `infra/x3/assistant-ui-eval/evalsets/`
  — `h4-h5.json` (13: prod health, sites, alerts, hosts, credit, spend, disk, memory) and `errors.json`
  (new GlitchTip errors). To add: H6 (fleet queue, needs the GitHub token), H7 (incident write-up), X1
  (open chat, see below), paraphrases of each question (the model should not depend on wording).
- **Labels:** derived, not hand-written. The truth changes every 5 minutes, so each item carries a *rule*
  that turns a snapshot into expected facts (`run-evalset.mjs` `RULES`: e.g. credit → `$4.12`, lowest site
  → host + %). The snapshot is `status.json` (and GlitchTip) fetched just before and after the question.
- **Reproducibility choice (to decide):** live runs (today: the answer depends on the moment) vs
  **frozen snapshots**: record each tool's response once, replay it to every arm through the adapter, so
  all arms see the same world. Frozen is what a model comparison needs; live is what the operator
  experiences. Probably both: a frozen set for G8, a live smoke for regressions.
- **Score:** every expected fact present (numbers with a rounding tolerance, number words, negations
  like "not green" fail); plus "nothing invented" (numbers in the answer not in the snapshot) — not
  scored yet. Report pass rate, tool-use rate, latency, and the spread over `--repeat`.
- **X1 (open chat)** has no ground truth from a snapshot: a small human-labelled set (preferences, or a
  rubric) or skip.

### G2 — tool use

- **Items:** the G1 questions, scored on the *calls* instead of the answer.
- **Labels:** the expected tool per question (H4/H5 → `getHomelabStatus`; new errors → status `errors`;
  older errors → `listGlitchtipIssues`; metric history → Grafana), and the tools' OpenAPI specs as the
  definition of a valid argument.
- **Source:** Langfuse already records every model call with its `tool_calls` (that is how the invented
  arguments were found). A Langfuse export of the assistant's traces is a ready-made production dataset
  (the harness's "datasets from production").
- **Score:** right tool first, valid arguments (schema check), number of calls, retries of the same failing
  call, and "reported a failed call as an empty result".

### G3 — briefing faithfulness

- **Items:** each morning briefing: its facts (the model's input) and its opening (the output). Langfuse
  has them as traces tagged `hub-briefing` from 2026-11-04; `www/briefing/*.json` on the mini has the
  facts and openings since 2026-11-03. Dry runs make more items on demand.
- **Labels:** per claim of the opening: supported / unsupported / contradicted by the facts, plus
  "resolved alert stated as current" and "a needs-you item left out". Human-labelled (gold) for a first
  set of ~30 openings; the judge (G5) for the rest once it agrees with people.
- **Score:** share of supported claims; any contradiction is a fail; coverage of the needs-you items.

### G4 — Grafana panel descriptions

- **Items:** the 316 panels of the 20 dashboards in the repo (title, type, unit, queries).
- **Labels:** the **185 panels that already have a human description are the reference** (gold); the 131
  without one are the production set. Plus a rubric: right metric, right unit, right reading (what high or
  low means), nothing invented (the 2026-11-04 demo: 12/13 correct, one ratio called a percentage).
- **Score:** rubric per description (judge, validated against people on a sample); agreement with the
  human description on the 185.

### G5 — judge reliability

- **Items:** the G3 openings (and later G4 descriptions) that people labelled.
- **Score:** the judge's per-claim verdicts against the human labels (precision and recall for
  "unsupported"), and its consistency: the same item judged several times. The harness refuses judges not
  validated against people; this goal is that validation.

### G6 — Home Assistant

- **Owned by the home-automation session** (chipi/home-automation `scripts/assist_eval.py`,
  `assist/eval_questions.json`, `docs/wip/ASSIST_EVAL.md`): 8 questions, scored against entity states read
  at the same moment, with switch states diffed to prove no action. First results: 6–7/8, 0 actions in
  40 questions; "power now" flaky (4 of 6 runs wrong although the value reached the model). Its runner
  prints JSON for the harness. To add: Dutch questions, voice, more items.

### G7 — system comparisons (arms over the G1–G3 datasets)

- LibreChat vs Open WebUI (same model, prompt and tools): the UI decision, with the H4/H5 numbers above
  as the starting point.
- Prompt versions (`system-prompt.txt` is versioned; each change is an arm).
- Context size (32k vs 64k), local vs failover (OpenRouter serves the same model), the hung/stopped X3
  (latency and correctness under failover).
- Tool design: model-filters-the-list vs code-computes-the-answer (the errors case is a clean A/B).
- Cost and latency per answer (LiteLLM spend and Langfuse timings).

### G8 — model comparison

- The same frozen datasets (G1 frozen snapshots, G3, G4) run against other models: the X3's other
  Ollama models, the DGX's production Qwen (FP4), and hosted models through LiteLLM (a frontier model as
  the silver reference, as the harness tutorials do).
- The question to answer: is `qwen3:30b-a3b-instruct-2507` the right always-on model for the X3, and
  which model should the failover be.

## What exists already

| What | Where |
|---|---|
| Question sets, runner, scorer (browser, both UIs), saved results with snapshots, `--rescore` | `infra/x3/assistant-ui-eval/` (`evalsets/`, `run-evalset.mjs`, `run-evalset-repeat.sh`, `results/`) |
| The assistant's prompt and tools as files | `infra/x3/assistant-ui-eval/system-prompt.txt`, `infra/homelab-home/openapi.json`, `glitchtip-openapi.json`, `apply-ui-config.py` |
| Every model call, with inputs, outputs and tool calls | Langfuse, project `agents` (keys `assistant-ui-eval`, `hub-briefing`, `grafana-llm`, `langfuse-judge`) |
| The briefing faithfulness judge | Langfuse evaluator `briefing-faithfulness` (built-in Faithfulness v2, model `assistant`) |
| Status snapshots | `www/status.json` on the mini every 5 minutes; logged to VictoriaLogs (`job:hub-status`) |
| Home Assistant eval | chipi/home-automation (above) |

## Open questions for the evaluation session

1. Frozen snapshots vs live: how to record tool responses once and replay them to every arm (an adapter
   that serves recorded tool results, or the harness's production-dataset path).
2. How the chat UIs fit an `adapter.py`: through the browser (what the operator sees, slow) or through
   the gateway with the same prompt and tools (fast, but skips the UI, which G7 shows matters).
3. Who labels the gold sets (G3 openings, G4 sample), and how many items each goal needs before a
   ranking stops moving (`evh rank-stability`).
4. Whether G6 runs in the harness or stays in home-automation with its JSON imported.

## Not covered by this note

- No dataset has been built in the harness yet; no labels exist except the derived G1 rules and the
  185 human panel descriptions.
- The H6 (fleet queue) and H7 (incident write-up) use cases are not built.
- Paraphrase robustness, Dutch, voice and the phone are not measured anywhere yet.
- Cost per answer is not measured; failover counts are visible (headers, Langfuse) but not aggregated.
- The reason for the LibreChat / Open WebUI gap is not found.
