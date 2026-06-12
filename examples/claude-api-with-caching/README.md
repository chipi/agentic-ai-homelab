# Claude API with prompt caching

Minimal Python skeleton showing the prompt-caching discipline in action.

What it demonstrates:

1. **Cache structure** — stable preamble first (cached), volatile context
   last (not cached).
2. **Cache hit/miss telemetry** — every response logs `cache_creation_input_tokens`
   and `cache_read_input_tokens` so you can prove the discipline holds.
3. **Model-version migration pattern** — model name comes from an env var
   with a default, so bumping `claude-sonnet-4-6` → `claude-sonnet-4-7`
   is a one-line shell change, not a code edit.

This is intentionally tiny — 100 lines of Python. The discipline is the
point, not the lines of code.

## Run it

```bash
cd examples/claude-api-with-caching
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...           # required
export ANTHROPIC_MODEL=claude-sonnet-4-6      # optional override

python run.py
```

Expected output:

```
[Call 1]  model=claude-sonnet-4-6  cache: created=1342  read=0
[Call 2]  model=claude-sonnet-4-6  cache: created=0     read=1342
[Call 3]  model=claude-sonnet-4-6  cache: created=0     read=1342
```

Call 1 establishes the cache (created > 0, read = 0).
Calls 2 and 3 reuse it (created = 0, read > 0).

If you see `read = 0` on subsequent calls, the prompt structure is wrong
— see "Common mistakes" below.

## What to copy from here

Look at `run.py` — the two patterns worth lifting:

1. The `cache_control` block on the system preamble. Anthropic caches
   prefix-based, so anything *before* the cache marker can be reused;
   anything after it is unique per request.
2. The `log_cache_usage()` helper. Adapt this into whatever observability
   layer your project uses — Grafana metrics, Sentry breadcrumbs, plain
   stdout. The discipline of *measuring* hit rate is more important than
   how you measure it.

## Common mistakes

- **Putting volatile content before the cache marker** — even a single
  changed character invalidates the cache. The marker has to come *after*
  everything stable, *before* everything volatile.
- **Sleeping 5 minutes between calls** — the cache TTL is 5 minutes. At
  exactly 5 minutes you pay the cache miss without amortizing the wait.
  Either stay under (~270s) or commit to a long wait (~1200s+).
- **Caching tiny preambles** — minimum is 1024 tokens for Sonnet,
  2048 for Haiku. Smaller blocks fail silently — the
  `cache_control` block is honored, but no cache is created. The
  telemetry will show `created=0 read=0` and you'll wonder why.
- **Changing the model mid-conversation** — the cache is model-specific.
  Migrating from Sonnet 4.6 to 4.7 wipes the cache; plan for the cost
  spike on first deploy.

## See also

- [`docs/cloud-ai-workflow.md`](../../docs/cloud-ai-workflow.md) —
  prompt-caching as discipline, the pillar narrative.
- [Anthropic prompt caching docs](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)
  — official reference for current TTLs, minimum sizes, and supported
  content blocks.
- [`docs/recipes/token-management-lean-ctx-rtk.md`](../../docs/recipes/token-management-lean-ctx-rtk.md)
  — the token-side complement to API-side caching.
