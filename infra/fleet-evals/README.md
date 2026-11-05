# fleet-evals — the triage fleet's eval catalog on the tailnet

`https://fleet-evals.tail6d0ed4.ts.net`: the static catalog of
[chipi/fleet-eval-data](https://github.com/chipi/fleet-eval-data) (private), on the mini, tailnet only.
The pages hold production-derived content (issue titles, alert names), so the tailnet is the access
control: no Funnel, no published port, no `--public`.

| Piece | What it does |
|---|---|
| `~/fleet-eval-data` on the mini | the checkout; pulled over HTTPS with the mini's `gh` login (repo-local credential helper, Contents read on this repo) |
| `update.sh` | the deploy, run on demand: when GitHub's main differs from the deployed commit, fast-forward, build the pages, (re)start `web`; otherwise says UP TO DATE. No timer (operator, 2026-11-05): a new version goes up when we deploy it |
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
```

## Deploy a new version

After pushing to fleet-eval-data's main, from any agent's machine (the X3 or the laptop). The key and
user are spelled out because the X3 has no ssh alias for the mini; a bare `ssh homelab` is refused there:

```bash
ssh -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes markodragoljevic@homelab '~/agentic-ai-homelab/infra/fleet-evals/update.sh'          # pull main, build, swap in
ssh -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes markodragoljevic@homelab '~/agentic-ai-homelab/infra/fleet-evals/update.sh --force'  # rebuild the same commit
```

The last line is `OK <old> -> <new> deployed`, `UP TO DATE <sha> is deployed`, `BUSY` (another deploy
is running) or `FAIL …` (the previous site keeps serving). Exit 0 for OK and UP TO DATE.

- **Safe to re-run, always.** It compares GitHub's main with the commit the live site was built from
  (`/site/live/.deployed`), not with the checkout.
- **A dropped connection does not stop it.** The deploy runs detached on the mini (`nohup`, log
  `/tmp/fleet-evals.log`) and the command only follows it; if your session ends, run it again later:
  it says BUSY while the build runs, then UP TO DATE.
- A build takes about 15 minutes on the mini (the container reads the checkout through colima's
  mount): run it with a 20-minute timeout or in the background.

## Operate

- A harness upgrade is a one-line pin change in fleet-eval-data's `pyproject.toml`; the next update
  builds a new `local/fleet-evals:<ref>` image.
- Check: `docker exec caddy wget -qO- http://fleet-evals-web/ | grep -o '<title>[^<]*' | head -1` →
  `Overview · agentic fleet evals`.

## Not covered

- No alert when a deploy fails: the command's last line says FAIL.
- The image installs only the pinned harness, not the rest of fleet-eval-data's `pyproject.toml`. A new
  dependency the catalog build needs means a change to this Dockerfile.
- The failure path (a broken build leaves the previous site serving) is written, not yet tested.
