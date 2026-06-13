# AGENTS.md — DGX-host work (scoped rules)

Loaded by opencode / Claude Code when working in `infra/dgx/` and below.
Layers on top of the repo-root rules.

## GPU contention is real — coordinate via `gpu-mode-swap.sh`

A single DGX-class GPU can't host the coder-next vLLM and the autoresearch
vLLM simultaneously. Both want ~90% of VRAM. Running them together OOMs
at startup.

**Before invoking any local vLLM endpoint** (e.g. `http://<dgx>:9000/v1`,
`http://<dgx>:8003/v1`), verify the right mode is active:

```bash
~/bin/gpu-mode-swap.sh --mode-only        # → "code" | "research" | "idle" | "BROKEN-BOTH"
```

If the mode is wrong, switch it (idempotent, safe to call defensively):

```bash
~/bin/gpu-mode-swap.sh code --json        # bring coder-next up
~/bin/gpu-mode-swap.sh research --json    # bring autoresearch up
~/bin/gpu-mode-swap.sh idle --json        # both down
```

**Always call by absolute path** — the `gpu-mode` zsh alias does not load
in non-interactive shells.

Full contract (output modes, exit codes, env-var config, sudo requirement,
failure modes): [`bin/README.md`](bin/README.md).

## What lives here

- `bin/` — DGX-host operator scripts (`gpu-mode-swap.sh`)
- `bin/README.md` — install + agent-invocation contract for the scripts

## Not a place for

- Dev-machine scripts (those belong in your shell rc, not this repo)
- Code that doesn't depend on running on the DGX (those belong in
  `examples/`, `templates/`, or a project repo)
