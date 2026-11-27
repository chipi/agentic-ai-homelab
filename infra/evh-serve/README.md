# evh-serve: the eval projects' catalogs and MCP servers on the tailnet

Each eval project gets a live catalog with the run inspector, and an MCP server agents can use to
explore its runs and plan the next evals. Both run on the mini, are reachable on the tailnet only, and
read the project's default branch, which is pulled every 5 minutes (operator, 2026-11-24; this replaces
the static, deploy-on-demand `infra/fleet-evals` of 2026-11-05).

| Instance | Project (private) | Catalog | MCP |
|---|---|---|---|
| `fleet-evals` | chipi/fleet-eval-data | https://fleet-evals.tail6d0ed4.ts.net | `…/mcp` |
| `podcast-evals` | chipi/podcast-scraper-eval-data | https://podcast-evals.tail6d0ed4.ts.net | `…/mcp` |
| `bakeoff-evals` | chipi/harness-bakeoff | https://bakeoff-evals.tail6d0ed4.ts.net | `…/mcp` |
| `robotics-evals` | chipi/robotics-evals | https://robotics-evals.tail6d0ed4.ts.net | `…/mcp` |

An agent adds a project's MCP server once, on any tailnet machine:

```bash
claude mcp add --scope user --transport http evh-fleet   https://fleet-evals.tail6d0ed4.ts.net/mcp
claude mcp add --scope user --transport http evh-podcast https://podcast-evals.tail6d0ed4.ts.net/mcp
claude mcp add --scope user --transport http evh-bakeoff https://bakeoff-evals.tail6d0ed4.ts.net/mcp
claude mcp add --scope user --transport http evh-robotics https://robotics-evals.tail6d0ed4.ts.net/mcp
```

The **Workbench** is not served here: evh keeps it and the write API on the machine that runs it,
never behind a proxy. Run it in a checkout (`evh catalog-serve` on the X3), where its writes can be
committed.

## How it works

| Piece | What it does |
|---|---|
| `instances/<name>.env` | one per project: tailnet host, repository, branch, catalog options; `HARNESS_REF` only for a project with no pin in its `pyproject.toml` |
| `sync` (`sync.sh`, `alpine/git`) | brings the checkout volume to `origin/<branch>` with the instance's read-only deploy key, passed on stdin (colima's engine cannot read the owner-only key folder); GitHub's host keys are pinned in `github_known_hosts` (from `gh api meta`) |
| `local/evh-serve:<ref>` | `python:3.12-slim` plus the harness at the pinned commit; built when a pin is new |
| `catalog-build` | builds the catalog pages into the build volume when the commit moved, and swaps them in only when the build passed (no network) |
| `catalog` | `evh catalog-serve --behind-proxy <host>`: the pages and the run inspector, which reads the data live |
| `mcp` | `evh mcp --http --allowed-host <host> --path /mcp` |
| `update.sh` | all of the above, per instance; one line each: `OK`, `UP TO DATE` or `FAIL` |
| `com.homelab.evh-serve.plist` | runs `update.sh` every 5 minutes; log `/tmp/evh-serve.log` |
| Caddy (`infra/reverse-proxy`) | one tailnet node per instance; `/mcp` to the MCP server, the rest to the catalog |

**The checkout is a Docker volume, not a folder on the mini.** Through colima's mount a full read of
fleet-eval-data took 25 s, against 0.9 s from a volume (2026-11-24); the inspector and MCP read it on
every request.

**The guard.** evh 0.8.0 offers `study-ask` and `study-tell` to every non-public MCP server; they write,
and `study-tell` can run a trial. `--public` would drop them, but also the item text and outputs this is
for. Until eval-harness 0.8.2 adds a flag that drops only those two, the containers are the guard:

- the checkout is mounted read-only in `catalog` and `mcp`;
- no model key is in any environment, and `EVAL_MAX_COST_USD=0`;
- the instance's network is `internal`, with Caddy its only other member: nothing reaches LiteLLM, the
  DGX or the internet.

The licensed QMSum text under podcast's `records/materialized/` is gitignored, so a clone never has it.

## Install (once, on the mini)

```bash
# 1. a read-only deploy key per instance (done 2026-11-24 for the first three, 2026-11-27 for robotics-evals)
ssh-keygen -q -t ed25519 -N "" -C "evh-serve <name> on homelab (read-only)" -f ~/.config/evh-serve/<name>_deploy_key
gh api repos/chipi/<repo>/keys -f title="evh-serve on homelab (read-only)" -f key="$(cat ~/.config/evh-serve/<name>_deploy_key.pub)" -F read_only=true
# 2. the first run creates each instance's volumes and internal network
~/agentic-ai-homelab/infra/evh-serve/update.sh
# 3. Caddy joins the networks (live; the reverse-proxy compose lists them for restarts), then reload
for n in fleet-evals podcast-evals bakeoff-evals robotics-evals; do docker network connect ${n}_internal caddy; done
docker exec caddy caddy reload --config /etc/caddy/Caddyfile
# 4. the timer
sudo cp com.homelab.evh-serve.plist /Library/LaunchDaemons/
sudo chown root:wheel /Library/LaunchDaemons/com.homelab.evh-serve.plist
sudo chmod 644 /Library/LaunchDaemons/com.homelab.evh-serve.plist
sudo launchctl bootstrap system /Library/LaunchDaemons/com.homelab.evh-serve.plist
```

A new project: an `instances/<name>.env`, step 1 for its key, the three steps' lines for its name, and a
Caddy site and network as for the others.

## Operate

- By hand, any time: `update.sh [<instance> [--force]]`. `--force` rebuilds the catalog at the same
  commit.
- A harness upgrade is the project's own pin change; the next run builds the image for it.
- Check: `tail /tmp/evh-serve.log`, or `docker exec caddy wget -qO- --header "Host: fleet-evals.tail6d0ed4.ts.net" http://fleet-evals-catalog:8080/ | head -1`.

## Not covered

- No alert on a `FAIL` line: it is only in `/tmp/evh-serve.log`.
- The image holds only the harness. A project whose catalog adapter imports more needs a Dockerfile change.
- A `reset --hard` while a page is read can show that page half old, half new, for one request.
- Old images (`local/evh-serve:<old ref>`) are not removed after an upgrade.
