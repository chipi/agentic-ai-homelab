# provider-bakeoff

Compare 10 LLM providers from 4 countries on the same tasks, with real
cost numbers, in one command.

```
US      🇺🇸  Claude    GPT       Gemini    Grok
EU      🇫🇷  Mistral   Hugging Face → open-weight models
CN      🇨🇳  DeepSeek  Qwen      Kimi
Local   🏠  vLLM (your own self-hosted)
Demo    🤖  Fake (no API needed)
```

Two tasks ship:
- **`json-extraction`** — structured data extraction from prose; gold
  JSON exists, scored by exact-field match
- **`commit-message`** — write a conventional-commit message from a
  diff; scored by an LLM judge against a per-item rubric

Both tasks are 10 items; full sweep across all 10 providers costs **~$2-5**.
You don't need every key — providers without env vars are skipped
gracefully.

---

## Quick start

```bash
make setup                       # creates .venv, installs SDKs
cp .env.example .env             # fill in any keys you have
make providers                   # shows which providers your env enables
make bakeoff                     # default: json-extraction task
```

Output lands in `out/<task>_<timestamp>/report.md` — that's the file
to read.

### Just want to see the runner work, no keys?

```bash
make bakeoff-fake                # uses FakeProvider only — zero cost
```

### Run both tasks back-to-back?

```bash
make bakeoff-all-tasks
```

### Run a specific subset of providers?

```bash
make bakeoff PROVIDERS=claude-sonnet-4-6,deepseek-chat,kimi-k2-0905-preview
```

---

## What the report looks like

```markdown
# Provider bake-off — `json-extraction`

## Summary (ranked by mean score)

| Provider              | Org              | Score | Cost     | Mean latency | Errors |
|-----------------------|------------------|-------|----------|--------------|--------|
| `claude-sonnet-4-6`   | Anthropic 🇺🇸    | 0.92  | $0.0421  | 1.8s         | 0      |
| `gpt-5-mini`          | OpenAI 🇺🇸       | 0.88  | $0.0156  | 2.1s         | 0      |
| `gemini-2.5-flash`    | Google 🇺🇸       | 0.85  | $0.0089  | 1.2s         | 0      |
| `deepseek-chat`       | DeepSeek 🇨🇳     | 0.83  | $0.0034  | 2.8s         | 0      |
| `qwen-plus`           | Alibaba 🇨🇳      | 0.82  | $0.0062  | 1.9s         | 0      |
| `kimi-k2-0905-preview`| Moonshot 🇨🇳     | 0.80  | $0.0091  | 2.4s         | 0      |
| `mistral-small-latest`| Mistral 🇫🇷      | 0.77  | $0.0023  | 1.4s         | 0      |
| `Llama-3.3-70B`       | Hugging Face 🇫🇷 | 0.73  | $0.0114  | 3.6s         | 1      |

## Per-item breakdown

| Item   | claude | gpt-5 | gemini | deepseek | qwen | kimi | mistral | hf-llama |
|--------|--------|-------|--------|----------|------|------|---------|----------|
| je-01  | 1.00   | 1.00  | 1.00   | 0.83     | 0.83 | 1.00 | 0.67    | 0.67     |
...
```

The numbers above are illustrative — your sweep will produce its own.

---

## Picking a provider from the report

Three honest questions to ask:

1. **Score ≥ 0.85 on your task type?** Anything below that is
   producing wrong outputs often enough that downstream code has to
   handle it.
2. **Cost: is the difference meaningful at your volume?** $0.03 vs
   $0.01 per sweep is irrelevant at 100/day. At 100k/day it's $7k/year.
3. **Latency: does your UX care?** Real-time chat needs < 2s. Batch
   eval doesn't.

Then read the per-item breakdown to find systematic failures —
providers that nail 9/10 but miss one specific type of item are
sometimes a better fit than providers with uniformly mediocre scores.

---

## Adding a provider

New OpenAI-compatible API:

1. In `providers.py`, subclass `_OpenAICompatProvider`:
   ```python
   class NewProvider(_OpenAICompatProvider):
       base_url = "https://api.<provider>.com/v1"
       env_var = "NEW_PROVIDER_KEY"
       default_model = "<their default>"
       flag = "🇽🇽"
       org = "<Org Name> 🇽🇽"
       INPUT_PRICE = 0.0   # USD / 1M tokens
       OUTPUT_PRICE = 0.0
   ```
2. Add it to `PROVIDER_CLASSES` at the bottom.
3. Add the env var to `.env.example` with a signup link.

Provider with its own SDK shape (like Anthropic / Gemini):
Write a class with the `Provider` protocol — see `ClaudeProvider` /
`GeminiProvider` for the shape.

---

## Adding a task

1. Add a `*.jsonl` file under `data/` — one JSON object per line.
2. Add a loader in `tasks.py` (model after `load_json_extraction` or
   `load_commit_message`).
3. Add a `TaskSpec` to `tasks.TASKS`.
4. If the scoring shape is new, add a scorer in `score.py` and route
   it in `score_item()`.

---

## Layout

```
provider-bakeoff/
├── README.md              this file
├── AGENTS.md              agent-facing rules for this project
├── Makefile               setup / bakeoff / bakeoff-fake / providers / tasks
├── .env.example           every API key + signup link
├── .gitignore             .env, .venv, out/, caches
├── requirements.txt       3 SDKs (anthropic + openai + google-genai)
├── providers.py           10 providers + FakeProvider + discover()
├── tasks.py               task specs + dataset loaders
├── score.py               exact-field match + LLM judge rubric
├── bakeoff.py             runner
└── data/
    ├── json_extraction.jsonl    10 items
    └── commit_message.jsonl     10 items
```

---

## Limits + honesty

- **Pricing is illustrative.** Confirmed pricing lives at each
  provider's official page. Verify before quoting.
- **Latency reflects network round-trip from your laptop.** A China-
  hosted provider will look slow from a US laptop and vice versa.
- **The LLM judge has its own bias.** Claude judges commit messages by
  default — that may favor Anthropic-shaped outputs. Swap the judge
  in `_build_judge()` in `bakeoff.py` if it matters for your decision.
- **10 items isn't statistical significance.** It's a vibe check.
  Use it to narrow to a top 3, then test the top 3 on your real data.

---

## Lifting into a separate repo

This dir is designed to lift cleanly. See `AGENTS.md` → "Lifting this
into its own repo" for the `git subtree split` recipe.
