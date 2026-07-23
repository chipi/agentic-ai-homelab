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

## Deploy / refresh
```sh
# on the mini, in ~/homelab-home
./gen.sh                       # rebuild index.html
docker compose up -d           # (re)start nginx
```
Reachable over the tailnet once `tag:homelab-host:8888` is granted in the ACL.
