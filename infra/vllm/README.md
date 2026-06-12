# vLLM stacks

Everything in this repo related to vLLM serving lives under here, grouped
so the relationships are obvious from the tree.

```
infra/vllm/
├── template/    canonical "start here" — hardened coder-next compose,
│                .env.example, README. Copy this when standing up a
│                new vLLM stack.
├── coder-next/  operator's daily-driver deploy: Qwen3-Coder-Next-FP8
│                serving on port 9000. Includes the .26.05-py3
│                image-bump sibling per the documented dance.
└── openwebui/   alt path: Qwen 2.5-7B served via vLLM behind Open WebUI
                 on port 3000. Mutex with coder-next at runtime (same GPU).
```

## When to use which

- **Starting fresh on a new host?** Copy `template/` → fill `.env` →
  boot. See [`template/README.md`](template/README.md) for the
  walkthrough (model selection, port/GPU tuning, image-bump dance,
  revision pinning).

- **Deploying on the operator's DGX?** `coder-next/` is what's running.
  Mode-swap with anything else on the GPU per
  [`docs/recipes/gpu-mode-swap.md`](../../docs/recipes/gpu-mode-swap.md).

- **Demoing / testing an alt model with a web UI?** `openwebui/` is the
  Qwen 2.5-7B + Open WebUI variant. Useful when you want a chat surface
  on the GPU without standing up LibreChat or similar.

## How they relate to one another

- `template/` is the **reusable starting point**. Everyone else in the
  world can `cp -r template/ ~/docker-compose/my-vllm/` and boot.
- `coder-next/` and `openwebui/` are **operator deploys** — concrete
  instances of the template, customized for actual use on the DGX. Their
  composes have stack-specific values (model name, port, gpu-memory-
  utilization budget) baked in; they're not meant to be cp'd.
- **`.env` location differs by intent.**
  - `template/docker-compose.yml` uses `env_file: .env` (sibling) — so
    when someone copies `template/` to a new dir, they drop a `.env`
    alongside and it just works.
  - `coder-next/docker-compose.yml` and `openwebui/docker-compose.yml`
    use `env_file: ../../../.env` — they read the **repo-root master
    `.env`** directly (which already aggregates HF_TOKEN + VLLM_API_KEY
    + everything else). No per-deploy `.env` files; one source of truth.
    Slight leakiness — the vLLM container sees env vars it doesn't use
    (provider API keys, observability creds) — but harmless for a
    personal homelab.

## Rule of the game for this folder

Every operational value that could reasonably change between deploys is
wired via `${VAR:-default}` substitution. The compose works with no `.env`
at all (defaults kick in); setting the var in master `.env` overrides.

Currently substitutable (master sets, compose defaults match operator's
DGX values):

| Var | What it controls | Default |
|---|---|---|
| `HF_TOKEN` | HuggingFace token for gated model downloads | (none — required for gated models) |
| `VLLM_API_KEY` | vLLM `--api-key` + open-webui's `OPENAI_API_KEY` | `buddy-is-the-king` |
| `HF_HOME` | Host path for HF cache (volume mount source) | `/opt/llm-models/huggingface` |
| `VLLM_CACHE_PATH` | Host path for vLLM CUDA-graph cache | `/opt/llm-models/vllm-cache` |
| `VLLM_PORT` | vLLM listening port (host + container side) | `9000` |
| `OPENWEBUI_PORT` | Open WebUI port (openwebui deploy only) | `3000` |

Rotation procedure for any of these: edit master `.env` → `docker compose
up -d` from the deploy dir. No compose edits required.

> For substitution to actually pick up master values when running compose
> from a deploy dir, use `docker compose --env-file ../../../.env up -d`.
> Without the flag, compose falls back to the in-file defaults (which are
> wired to match the operator's DGX values, so the result is the same
> today — but rotation only takes effect via the flag).

## Booting any stack

The same pattern works for all three. Substitute `<stack>` with `template`,
`coder-next`, or `openwebui`.

```bash
cd ~/agentic-ai-homelab/infra/vllm/<stack>

# Bring it up (the --env-file flag points compose at the repo-root master
# .env so ${VAR:-default} substitution picks up your real values).
sudo docker compose --env-file ../../../.env up -d

# Watch the warm-up — vLLM cold start (first revision pull + CUDA-graph
# compile) takes 5-10 min; healthcheck won't restart-loop it because
# start_period: 10m is baked into the compose.
sudo docker compose logs -f vllm

# Verify it's listening (use the port you configured; default 9000):
curl -fsS http://localhost:9000/v1/models \
  -H "Authorization: Bearer $(grep '^VLLM_API_KEY=' ~/agentic-ai-homelab/.env | cut -d= -f2)"

# Restart, stop, status:
sudo docker compose --env-file ../../../.env up -d --force-recreate  # restart
sudo docker compose down                                              # stop
sudo docker compose ps                                                # status
```

### Why the `--env-file ../../../.env` flag

Compose has two distinct env mechanisms and they don't share input by
default:

| Mechanism | Reads from | What it does |
|---|---|---|
| `env_file:` in compose YAML | `../../../.env` (already wired) | Injects vars into the **container** at runtime |
| `${VAR}` substitution in YAML | Compose's *project* `.env` (sibling to compose.yml) OR `--env-file` flag | Resolves variables at **parse time**, before the container exists |

We use both — `env_file:` for what the container needs at runtime (e.g.,
`HF_TOKEN`), and `${VAR:-default}` substitution for what shapes the
compose itself (paths, ports, the API key inserted into the command line).
The flag is what tells compose's substitution mechanism to look at master
instead of a sibling `.env`.

Without the flag → substitution falls back to defaults baked into the
compose. The defaults match operator's DGX values so today nothing
breaks; but if you ever rotate `VLLM_API_KEY` in master, the substitution
won't pick up the new value unless you use the flag.

## Makefile idea (not built yet — future work)

The `--env-file ../../../.env` flag is the only friction in the workflow
above. A small per-deploy `Makefile` would hide it behind muscle-memory
targets:

```makefile
# infra/vllm/coder-next/Makefile (sketch — not committed yet)
ENV := ../../../.env
.DEFAULT_GOAL := help

up:       ## Bring the stack up
	sudo docker compose --env-file $(ENV) up -d

down:     ## Stop and remove
	sudo docker compose down

restart:  ## Force-recreate (picks up rotated env values)
	sudo docker compose --env-file $(ENV) up -d --force-recreate

logs:     ## Tail logs
	sudo docker compose logs -f

status:   ## Show running state
	sudo docker compose ps
```

Then the rhythm becomes `make up` / `make logs` / `make restart`,
identical across all three stacks. Operator wouldn't have to remember the
flag or the long compose subcommands.

Two ways to wire it later:
- **Per-deploy `Makefile`** (the sketch above) — 5 lines, duplicated 3
  times. Pros: each deploy is self-contained. Cons: edit-3-files when
  the pattern changes.
- **Single `infra/vllm/Makefile`** with a `STACK` variable: `make up
  STACK=coder-next`. Pros: DRY. Cons: extra arg every invocation.

Either is doable; not built today because the explicit flag is fine for
the current usage rhythm. Add when typing the same long command for the
fourth or fifth time starts to feel silly.

## Image-bump pattern

`coder-next/docker-compose.yml.26.05-py3` is a sibling-file stage of an
NVIDIA vLLM image upgrade. See `template/README.md` → "Image-bump dance".
