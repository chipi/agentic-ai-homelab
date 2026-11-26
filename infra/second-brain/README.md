# second-brain: the paper library's read server on the mini

[second-brain](https://github.com/chipi/second-brain) (`sb`) is a paper library: manifests in the private
chipi/second-brain-content, texts fetched from arXiv, NASA NTRS and open-access DOIs, and a SQLite FTS5
index. `sb serve` is its read-only MCP server (tools `search`, `read`, `paper`). Here it runs on the
mini as `sb-mcp` for flotilla's reads worker, which declares it as the read server `library` (flotilla
case 1). The index is rebuilt every Sunday.

| Piece | What it does |
|---|---|
| `second-brain.env` | `SB_REF`, the chipi/second-brain commit both images are built from; the content repository and branch |
| `local/second-brain:{serve,build}-<SB_REF>` | built by `update.sh` from GitHub at that commit (the repo's `Dockerfile`, targets `serve` and `build`) |
| `sync` (`sync.sh`, `alpine/git`, bridge) | brings the content volume to `origin/main` with a read-only deploy key passed on stdin; GitHub's host keys pinned in `github_known_hosts` |
| `batch` (`build` image, bridge) | `sb fetch`, `sb fulltext`, `sb build --version <content sha7>` into the data volume; each writes a Prometheus text file into the metrics volume |
| `push` (`curl`, `backend_default`) | sends those files to VictoriaMetrics (`job="second-brain"`, `instance="homelab"`) |
| `mcp` → `sb-mcp` (`serve` image) | `sb serve` on :8790 in the internal `mcp` network, data mounted read-only, `/mcp` behind a bearer token |
| `update.sh` | all of the above; one line at the end, `OK` or `FAIL` |
| `com.homelab.second-brain.plist` | runs `update.sh` Sundays 05:30; log `/tmp/second-brain.log` |

**The `mcp` network** is owned here: internal, `192.168.160.0/20`. Its other members join it as an
external network: flotilla's `egress-reads` (the reads worker's only way to MCP servers; its
`allow_ranges` takes this subnet, its ACL `sb-mcp`), n8n's MCP workflows, and `alloy-homelab`, which
scrapes `sb-mcp:8790/metrics`. Nothing on it reaches the internet, and nothing is published on the
mini. Bring this stack up before those.

**The server** re-reads `DATA/current` per request, so a new index is served without a restart; a
failed weekly step leaves the previous index serving. `update.sh` keeps the current index and the one
before it. `/healthz` and `/metrics` are unauthenticated (counts, a version, a build time; no library
content); `/mcp` needs the token.

**Observability.** Logs: Alloy ships `sb-mcp`'s JSON lines (`_msg`, `level`, `tool`, `status`,
`trace_id` when a `traceparent` came in) as `service=sb-mcp`. Metrics and the dashboard *second-brain*
(Grafana → Homelab). Alerts (group `second-brain`): `second-brain-build-stale` (no completed build in 8
days), `second-brain-mcp-errors` (more than 2 failed requests in 30 min); `infra-target-down` covers
sb-mcp down. No GlitchTip project: sb is stdlib-only and has no error SDK, so errors are its `error`
log lines and `sb_requests_total{status="error"}`. No traces exported.

## Install (once, on the mini, as the operator)

```bash
mkdir -p ~/.config/second-brain && chmod 700 ~/.config/second-brain
# 1. the read-only deploy key on the content repository
ssh-keygen -q -t ed25519 -N "" -C "second-brain on homelab (read-only)" -f ~/.config/second-brain/content_deploy_key
gh api repos/chipi/second-brain-content/keys -f title="second-brain on homelab (read-only)" \
  -f key="$(cat ~/.config/second-brain/content_deploy_key.pub)" -F read_only=true
# 2. the bearer token for /mcp; flotilla's reads worker reads the same value (MCP_LIBRARY_TOKEN_FILE)
(umask 077; openssl rand -hex 32 > ~/.config/second-brain/sb-token)
# 3. images, token, the mcp network and sb-mcp; then the first build (fetches every paper: long)
~/agentic-ai-homelab/infra/second-brain/update.sh up
~/agentic-ai-homelab/infra/second-brain/update.sh
# 4. Alloy joins the mcp network and scrapes sb-mcp (infra/observability/hosts/homelab)
cd ~/agentic-ai-homelab/infra/observability/hosts/homelab && docker compose up -d
# 5. the weekly timer
sudo cp ~/agentic-ai-homelab/infra/second-brain/com.homelab.second-brain.plist /Library/LaunchDaemons/
sudo chown root:wheel /Library/LaunchDaemons/com.homelab.second-brain.plist
sudo chmod 644 /Library/LaunchDaemons/com.homelab.second-brain.plist
sudo launchctl bootstrap system /Library/LaunchDaemons/com.homelab.second-brain.plist
```

The alerts and the dashboard arrive with the checkout (Grafana provisioning; alerts after a reload).

## Operate

- By hand, any time: `update.sh` (the weekly run) or `update.sh up` (only the server).
- An sb upgrade: move `SB_REF` in `second-brain.env`, then `update.sh up`; the old images stay until pruned.
- Check: `tail /tmp/second-brain.log`; `docker exec sb-mcp python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8790/healthz').read())"`.

## Not covered

- No GlitchTip project and no traces (above).
- Old `local/second-brain:*` images are not removed after an upgrade.
- The batch steps reach the internet without an allowlist (bridge network, like evh-serve's `sync`).
- An index build during a `search` swaps `current` atomically; a request already reading the old
  index finishes on it.
