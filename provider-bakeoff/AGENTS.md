# AGENTS.md — provider-bakeoff

This file layers on top of the global `~/.config/opencode/AGENTS.md`
(or the parent repo's root `AGENTS.md` if running here from
`agentic-ai-homelab/provider-bakeoff/`).

Only project-specific rules go here.

---

## Project overview

A self-contained mini-project that runs the same task across 10 LLM
providers (4 countries + local + fake) and produces a comparison
report. Designed so anyone — including agents — can:

1. `cp .env.example .env` and fill in whichever keys they have
2. `make bakeoff` and get a Markdown report
3. Read the report to pick a provider for their workload

This dir can be lifted into its own repo with no surgery — that's the
design goal.

---

## Stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | Universal SDK availability across all 10 providers |
| Provider SDKs | `anthropic`, `openai`, `google-genai` | 3 SDKs cover 10 providers (most are OpenAI-compatible) |
| Env loading | shell `source .env` in the Makefile | No `python-dotenv` dep |
| Output | JSON Lines + JSON + Markdown | machine-readable + human-readable |
| Test framework | none yet | This is a small example; smoke-test by running |

---

## Project-specific rules

1. **Never modify `data/*.jsonl` to make a provider look better.** The
   datasets are the contract; provider scores have to be honest.

2. **Pricing constants in `providers.py` are illustrative.** When you
   actually pick a provider based on a report, verify current pricing
   at the provider's official page. Don't quote the bake-off cost
   numbers as final without re-checking.

3. **Latency is not directly comparable across regions.** A Chinese
   provider hit from a US laptop will look slow even if it's fast from
   Shanghai. Note this in any conclusions drawn.

4. **Adding a provider:** new class in `providers.py` (subclass
   `_OpenAICompatProvider` if it speaks OpenAI Chat Completions) +
   add to `PROVIDER_CLASSES` + add env var to `.env.example` + add
   the org's signup URL. Stop there — no need to touch the runner or
   scorer.

5. **Adding a task:** new entry in `tasks.TASKS` + corresponding loader
   + a `data/<task>.jsonl` file + (if needed) a scorer in `score.py`.
   Two task types already model the two scoring shapes you're likely
   to need.

---

## Where to look

- Datasets: `data/` (10 items per task).
- Provider definitions: `providers.py`.
- Task definitions (prompts, system messages): `tasks.py`.
- Scoring (exact match / LLM judge rubric): `score.py`.
- Runner: `bakeoff.py`.
- Operator entrypoints: `Makefile`.
- Output: `out/<task>_<timestamp>/` — gitignored.

---

## How an agent should run this cold

```bash
make setup                    # install deps in .venv (no API needed)
make providers                # show which providers your env enables
make bakeoff-fake             # offline smoke-test the runner
cp .env.example .env          # then edit to add at least one real key
make bakeoff                  # default task: json-extraction
make bakeoff TASK=commit-message
```

If only the `ANTHROPIC_API_KEY` is set, the bake-off runs with just
Claude (and the commit-message judge has real signal). All other
providers gracefully skip.

---

## Common mistakes to avoid

- **Running without `.env`** — providers fall back to fake, the
  report is uninformative. Run `make providers` first to confirm what's
  available.
- **Comparing a US-region call against a China-region call as
  "latency"** — see project rule #3.
- **Adding a provider without an org URL in `.env.example`** — the
  next agent / contributor doesn't know where to get a key. Always
  include the signup link.

---

## Lifting this into its own repo

If you decide to spin this out:

1. `git subtree split --prefix provider-bakeoff -b bakeoff-extract`
2. New empty GitHub repo
3. `git push <new-remote> bakeoff-extract:main`
4. Update the lifted `AGENTS.md` to remove the
   "layered on parent repo" line at the top.
5. Drop a top-level `LICENSE`.

Everything else (Makefile, data, runner) works standalone — that's the
design point.
