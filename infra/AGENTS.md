# AGENTS.md — infra/ (scoped rules)

Loaded when working under `infra/` and below. Layers on top of the
repo-root [`AGENTS.md`](../AGENTS.md); never duplicates or contradicts it.

`infra/` holds the deployable stacks — docker composes, the observability
pipeline, and the local vLLM configs, plus the DGX operator scripts. The
rules here are about *how those stacks are run and kept up to date in
place*.

## Run docker composes from the repo in place

No copy-out to `~/docker-compose/...` — run each stack where it lives so its
`.env` and relative paths resolve (the run-from-repo migration, commit
`fa24a27`). Recipes that still tell you to copy out are stale — fix the doc when
you hit it, don't leave a TODO.

`.env` location is **per-stack**, not uniform:

- **`coder-next`, `openwebui`** read the **repo-root `.env`** (`../../../.env`) —
  the shared serving-vLLM secrets (`HF_TOKEN`, `VLLM_API_KEY`; see the root
  `.env.example`).
- **`autoresearch`, `observability`, `template`** keep a **stack-local `.env`**
  (their own secrets / tuning — autoresearch KV-cache params, observability's
  Grafana Cloud creds). Each ships a co-located `.env.example`.

## Run operator scripts from the repo too — symlink, don't copy

`~/bin/foo` is a symlink into `infra/dgx/bin/foo.sh`, so `git pull` ships
updates without re-installing. Co-located README next to each script
carries the agent-invocation contract.

## DGX work has deeper scoped rules

Working in `infra/dgx/` or invoking a local vLLM? Read
[`dgx/AGENTS.md`](dgx/AGENTS.md) first. Short version: GPU contention
between the coder-next and autoresearch vLLMs is real — running both
OOMs — so verify the right mode is active before pointing a tool at a
local endpoint (`http://<dgx>:9000/v1`, `:8003/v1`):

```bash
~/bin/gpu-mode-swap.sh --mode-only
```

## What lives here

- `dgx/` — DGX-host operator scripts + GPU mode coordination (own AGENTS.md)
- `observability/` — Grafana Cloud stack (Alloy, DCGM, cAdvisor)
- `vllm/` — local vLLM compose stacks (coder-next, autoresearch)
