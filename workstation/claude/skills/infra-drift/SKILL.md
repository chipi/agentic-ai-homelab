---
name: infra-drift
description: Read-only check that what runs on a homelab host is what the repo says — the host's checkout (commits behind origin/main, hand-copied or untracked files), running containers against the image their compose file names, images that float (:latest, main-stable, no tag), and stray compose files outside the checkout that define a running container. Ends with DRIFT N findings. Use when asked "is the DGX/mini current", "what's running vs what's in compose", "any :latest images", before a maintenance window, or after someone deployed by copying files.
---

# infra-drift

On 2026-10-17 a single look found four kinds of drift nobody had noticed:
- the DGX's `ops` checkout was 171 commits behind, with three files copied in by hand;
- Umami ran `postgresql-latest` under an SRI-pinned tracker;
- a stale duplicate `~/umami/docker-compose.yml` sat next to the real one;
- the mini's LiteLLM ran a floating tag while compose pinned a version.

This skill makes that look one command.

## Run (through host-run)

```bash
D=~/.claude/skills/infra-drift/scripts/drift.py
R=~/.claude/skills/host-run/scripts/run.sh

$R homelab $D --checkout '~/agentic-ai-homelab'
$R dgx     $D --checkout /home/ops/agentic-ai-homelab --as ops --allow-unpinned librechat-api
# --checkout repeats: one run covers every checkout on the host (homelab + chipi/infra)
$R homelab $D --checkout '~/agentic-ai-homelab' --checkout '~/chipi-infra'
$R dgx     $D --checkout /home/ops/agentic-ai-homelab --checkout /home/ops/chipi-infra --as ops --allow-unpinned librechat-api
```

- `--as USER`: git and compose run as the checkout's owner. On the DGX that's `ops`, which owns
  the stacks and their `.env` files.
- `--allow-unpinned a,b`: containers the operator has decided may float. `librechat-api` is
  being evaluated on `:latest` (2026-10-17). Allowed containers are listed, not counted.

It's read-only: `git fetch` plus `docker ps`, `inspect` and `compose config`. It ends with
`DRIFT: N finding(s)`, exit 1 if N > 0.

| Section | Finding means | Usual action |
|---|---|---|
| checkout | behind origin/main, local commits, modified (flagged when identical to origin/main, i.e. copied in) or untracked files | pull as the owner (`git -C <checkout> pull --ff-only`); never copy files in |
| compose | a container runs a different image than its compose file names now | recreate in a window, unless it's cosmetic (see below) |
| unpinned | what a recreate would pull floats (`:latest`, `main`, `main-stable`, no tag, no digest) | pin the running digest or a version tag |
| stray | a compose file outside the checkout defines a container that runs from another file | delete it, after checking nothing references it |

Pinning is judged on the compose file, i.e. what a recreate would pull, not on the running
reference. A digest pin counts as matching when the running image has that digest.

## Verified

2026-10-17:
- **mini, 4 findings:**
  - checkout 11 behind (pulled after);
  - LiteLLM running `main-stable` vs compose `v1.96.2`;
  - Langfuse ClickHouse and MinIO with no tag.
- **DGX, 1 finding:** checkout 6 behind (pulled after); `librechat-api` was allowed.
- The first version reported Umami as drifted although it runs the pinned digest. It compared
  strings; it now compares digests.

## Known limits

- **Cosmetic tag differences:** the mini's LiteLLM is `1.96.2` under the `main-stable` tag,
  and compose pins `v1.96.2` (the pin commit says "what runs today"). It's reported as
  `compose` drift, yet a recreate changes nothing. Before recreating, check the version the
  container reports.
- **Images only:** env, volumes and ports aren't compared.
- **Non-compose containers aren't covered:** systemd units on the DGX (`gpu-*`), the
  LaunchDaemons on the mini, and containers from `/opt/*` stacks (faster-whisper, pyannote,
  moss: the podcast_scraper converge) aren't checked against a repo.
- **Stray-file search depth:** it searches the home directory two levels deep only.
