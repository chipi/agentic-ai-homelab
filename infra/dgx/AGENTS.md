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

## The DGX repo checkout is DEPLOY-ONLY — never commit on it

The `~/agentic-ai-homelab` checkout on the DGX exists to **run** things, not to
author them. Treat it as a read-only mirror of `origin/main`:

- **Never `git commit` on the DGX.** Author + commit on your workstation (or a
  branch), `git push` to origin, then on the DGX `git pull` (fast-forward).
- **Deploy = `git pull`.** Don't `git checkout origin/main -- <path>` to sneak
  files in — that leaves staged changes and masks divergence. Pull the whole
  branch so `git status` stays clean and `HEAD == origin/main`.
- **Keep it at 0/0 with origin.** Check `git rev-list --left-right --count
  HEAD...origin/main` — anything but `0 0` means it drifted; reconcile before it
  compounds.
- If something genuinely must be changed *on* the DGX first (rare), make it a
  branch and **push it the same session** — don't leave an unpushed local commit
  on the production checkout.

**Why (2026-07-20 incident):** an agent committed `gpu-mode-swap.sh` changes
directly on the DGX. It sat unpushed while `origin` evolved the same file
independently → the checkout drifted 3-ahead / ~57-behind, and reconciling meant
a hand-resolved merge conflict on the live GPU-control script + a `git reset
--hard` on production. All avoidable: commit on the workstation, pull on the DGX.
`.env` files are gitignored, so a clean `git pull`/`reset --hard origin/main`
never touches secrets.

## What lives here

- `bin/` — DGX-host operator scripts (`gpu-mode-swap.sh`)
- `bin/README.md` — install + agent-invocation contract for the scripts

## Not a place for

- Dev-machine scripts (those belong in your shell rc, not this repo)
- Code that doesn't depend on running on the DGX (those belong in
  `examples/`, `templates/`, or a project repo)
