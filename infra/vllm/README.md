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
- Per-stack `.env` files sit next to each `docker-compose.yml` and are
  gitignored. Operator-master sheet (cross-stack secrets reference) lives
  at the repo root `.env` on the operator's deploy.

## Image-bump pattern

`coder-next/docker-compose.yml.26.05-py3` is a sibling-file stage of an
NVIDIA vLLM image upgrade. See `template/README.md` → "Image-bump dance".
