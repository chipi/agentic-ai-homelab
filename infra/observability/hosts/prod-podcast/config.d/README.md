# MIRROR — do not edit these files by hand

The `.alloy` files in this directory are **copies**. They are kept here so a checkout of
this repo is a complete, runnable definition of the prod-podcast observability stack:
`docker-compose.yml` one level up mounts `./config.d` into the Alloy container, so
deleting them would leave a `docker compose up` starting Alloy with no configuration at
all.

**Editing them here changes nothing on prod.** Nothing in this repo deploys them.

| file | owner / source of truth |
|---|---|
| `base.alloy` | `podcast_scraper:infra/observability/base.alloy` |
| `selfmon.alloy` | `podcast_scraper:infra/observability/selfmon.alloy` |
| `player.alloy`, `operator.alloy`, `litellm.alloy` | `podcast_scraper:infra/observability/` |

They reach the box via `podcast_scraper:.github/workflows/deploy-config.yml`
(scp → stage → atomic rename → `docker kill -s HUP alloy`). No root required: the file
on the box may be `root:root`, but `/opt/vps-observability/config.d` is
`drwxrwxr-x deploy deploy` with no sticky bit, and replacing a file is governed by the
directory's permissions, not the file's.

**To change one: edit it in `podcast_scraper`, deploy, then refresh the copy here in the
same PR.**

## Why this warning exists

`base.alloy` had no deploy path at all until 2026-09-16. It was hand-edited over SSH as
root — twice; the `.bak-<timestamp>` siblings on the box are the fingerprint, and nothing
in either repo creates those. Meanwhile this copy was edited separately and never
shipped.

The two diverged by 41 lines, with **this copy the larger and newer of the pair**. So the
divergence did not read as staleness, it read as fact: anyone here would reasonably
conclude prod extracted W3C/Sentry trace IDs into structured metadata and collected the
widened cadvisor keep-list (PSI pressure, cpu user/system split, scrape errors). Prod did
neither, and never had.

That is what this banner exists to prevent — not a stale copy, but a confident one. A
mirror is useful; a mirror nobody knows is a mirror is a claim nobody checks.

## Pending: the 41 lines

The larger variant is preserved at commit `4407569`:

```bash
git show 4407569:infra/observability/hosts/prod-podcast/config.d/base.alloy
```

It lands deliberately through the `podcast_scraper` deploy loop *after* the
byte-identical adoption of the running config is proven green — adopt with zero
behaviour change first, so a failure identifies the pipeline rather than the content,
then change behaviour through a pipeline already known to work.

Context: `chipi/agentic-ai-homelab#64`.

## Known: the `docker-compose.yml` one level up is also a mirror, and is also drifted

```
live on prod : a3e682623ac7e8dd8a81cdabdb6a9bd0
this repo    : c8ab553f73de9141f93d36e5ef4e287a
```

Same category of problem, **no deploy path owns that file either**, and it is not fixed.
Treat it as documentation, not as truth, until it is adopted the same way.
