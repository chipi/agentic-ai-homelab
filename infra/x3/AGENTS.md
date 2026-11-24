# AGENTS.md — infra/x3 (the X3 workstation as a deployment surface)

The X3 (`omarchy`, 100.92.54.65) is the operator's workstation and the third deployment surface,
next to the mini and the DGX (RFC-0008). It runs the local assistant model; the eval harness uses
the same box for its own runs.

- **Deploy from `~/deploy/agentic-ai-homelab`, a checkout on `main`, never from `/work/...`.**
  `/work/agentic-ai-homelab` is the dev tree (branches, uncommitted edits). Every unit here and the
  X3 collector are linked from the deploy checkout: `git -C ~/deploy/agentic-ai-homelab pull
  --ff-only` + a restart deploys a change. Recipe: `docs/recipes/x3-deploy.md`.
- **User units only** (`systemctl --user`, linger is on). No root on this box for our services;
  the operator runs the few `sudo` steps (ufw, `tailscale serve`) by hand. **The one exception:
  robotics-lab's staging engine** (ADR-0013): `containerd-staging` and `docker-staging` system units, the
  `robotics-staging-deploy` script and its sudoers rule, installed by the operator with
  `x3-staging-engine-setup.sh`. Agents reach staging only through `sudo -n robotics-staging-deploy`, and
  `up`/`rollback` only with the operator's go (`docs/recipes/x3-staging-engine.md`).
- **One Ollama on this box: the `ollama` unit** (operator, 2026-11-19; it was `ollama-assistant`). The eval harness's ad-hoc
  `ollama serve` on `127.0.0.1:11434` (a long-job since 2026-10-30, no model call after 11-03) was
  stopped and its long-job files deleted that day. Don't start a second `ollama serve`: anything that
  needs a local model uses it (`100.92.54.65:11435`, or LiteLLM's `assistant` alias). The assistant's model holds
  ~25 GB of the 62 GiB of GPU memory (GTT) and keeps one model loaded (`OLLAMA_MAX_LOADED_MODELS=1`), so a
  request for another model swaps the assistant's model out until the next call reloads it. Phase 1
  measured gpt-oss:120b beside the assistant: 37% CPU offload and swap 16 → 41 GB. A test of a model over
  ~35 GB is the operator's call.
- **Ollama upgrades are the operator's call.** The unit runs `~/.local/opt/ollama-<version>` and names
  the version; the eval harness's results were measured on it, so ask first.
- **Port 11435 is the only one open to the tailnet** for our services, and only `tag:homelab-host`
  may reach it (chipi/infra `tailscale/policy.hujson`). Don't publish another port without the
  ACL and ufw change being agreed.
- `assistant-ui-eval/` is the throwaway UI comparison (RFC-0008 phase 3); it runs from the dev
  tree and is removed after the decision.
