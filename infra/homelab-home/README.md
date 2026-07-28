# homelab-home — tailnet start page

A single-page overview of the homelab machines, served on the mini at
`http://homelab:8888` (tailnet-only, basic-auth). Two symmetric columns —
**Mac mini** and **DGX** — each showing: host stat row, CPU/GPU charts,
service health traffic-lights, a Docker line, and a services table. Every
chart/badge deep-links to the matching Grafana dashboard or service.

## Pieces
- `gen.sh` — regenerates `www/index.html`. Reads service creds from the stack
  `.env` files (`observability/backend`, `glitchtip`, `langfuse`, `umami`) at
  generation time; **contains no secrets itself**. Run it to refresh the static
  shell (the live numbers are fetched client-side).
- `docker-compose.yml` — `nginx:alpine` serving `www/`, bound to the **tailnet
  IP** (`100.87.33.61:8888`), joined to `backend_default` so it can proxy VM.
- `default.conf` — nginx: basic-auth (`.htpasswd`) over everything + a `/vm/`
  reverse-proxy to `victoriametrics:8428` (same-origin, so the page's JS queries
  VM without CORS).

## Not in git (mini-local, gitignored)
`www/index.html` (generated), `.htpasswd`, `.basic-auth-cred`, `.env`.

## Deploy / refresh (run-in-place from the repo — no copy-out)
Runs from this repo checkout; `gen.sh` writes `www/index.html` next to itself
and the compose mounts it. `www/`, `.htpasswd`, `.basic-auth-cred` are gitignored
(generated / secret, staged here on the mini).
```sh
# on the mini, in this dir (…/agentic-ai-homelab/infra/homelab-home)
./gen.sh                       # rebuild www/index.html
docker compose up -d           # (re)start nginx
```
Reachable at `homelab:8888` (direct) and `homelab.<tailnet>/home` (HTTPS via
`tailscale serve`, see [`../homelab-serve/`](../homelab-serve/README.md)) — the
tailnet ACL grants `tag:homelab-host:8888` + `:443`.

## Related

- Systems index: [`infra/README.md`](../README.md)
- Global docs: [Pillar 2 — Local AI infra](https://github.com/chipi/agentic-ai-homelab/blob/main/docs/local-ai-infra.md)
