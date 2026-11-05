# fleet-evals — the triage fleet's eval catalog on the tailnet

`https://fleet-evals.tail6d0ed4.ts.net`: the static catalog of
[chipi/fleet-eval-data](https://github.com/chipi/fleet-eval-data) (private), on the mini, tailnet only.
The pages hold production-derived content (issue titles, alert names), so the tailnet is the access
control: no Funnel, no published port, no `--public`.

| Piece | What it does |
|---|---|
| `~/fleet-eval-data` on the mini | the checkout; pulled over HTTPS with the mini's `gh` login (repo-local credential helper, Contents read on this repo) |
| `update.sh` | every 10 min (launchd `com.homelab.fleet-evals`): when `origin/main` moved, fast-forward, build the pages, (re)start `web`; quiet otherwise. Log: `/tmp/fleet-evals.log` |
| `build` (compose profile) | one-shot: `python:3.12-slim` + the harness at the commit `pyproject.toml` pins; the checkout mounted read-only; builds into the `site` volume and swaps the new build in only when it passed |
| `web` | stock `nginx:alpine`, the site mounted read-only (no image of ours holds research data) |
| Caddy | `infra/reverse-proxy`: node `fleet-evals`, reaches `fleet-evals-web:80` over `fleet-evals_default` |

**Static only (operator, 2026-11-05).** evh's run inspector listens on 127.0.0.1 unless it runs in
`--public` mode, which serves numbers only; its page here is a shell whose API calls fail. A private
behind-a-proxy mode is asked of eval-harness.

## Install (once, on the mini)

```bash
git clone -c credential.helper= -c 'credential.helper=!/usr/local/bin/gh auth git-credential' \
  https://github.com/chipi/fleet-eval-data.git ~/fleet-eval-data
git -C ~/fleet-eval-data config credential.helper '!/usr/local/bin/gh auth git-credential'   # this repo only
~/agentic-ai-homelab/infra/fleet-evals/update.sh --force   # compose creates fleet-evals_default
docker network connect fleet-evals_default caddy   # live; the reverse-proxy compose lists it for restarts
sudo cp com.homelab.fleet-evals.plist /Library/LaunchDaemons/ && sudo launchctl bootstrap system /Library/LaunchDaemons/com.homelab.fleet-evals.plist
```

## Operate

- Rebuild now: `update.sh --force`.
- A harness upgrade is a one-line pin change in fleet-eval-data's `pyproject.toml`; the next update
  builds a new `local/fleet-evals:<ref>` image.
- Check: `docker exec caddy wget -qO- http://fleet-evals-web/ | grep -o '<title>[^<]*' | head -1` →
  `Overview · agentic fleet evals`.

## Not covered

- No alert when updates fail: read `/tmp/fleet-evals.log` (`FAIL …` lines).
- The failure path (a broken build leaves the previous site serving) is written, not yet tested.
