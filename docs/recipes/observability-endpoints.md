# Observability endpoints — the `homelab` name convention

All senders reference the **`homelab`** tailnet name, never a host IP. On free
Tailscale `homelab` is a **MagicDNS device name** — the machine *named* `homelab`,
which is the **Mac mini** (verified live 2026-07-25). The one-time DGX → mini
sender cutover is **done**; it's stable now, and future host swaps are free
(rename the new box `homelab`).

## The mapping (infra owns this)

`homelab` → the observability host (Mac mini). One host, one name, services by port and tailnet node:

**Sender paths (internal ingest):**

| Port | Service | Sender path |
|---|---|---|
| `8428` | VictoriaMetrics (metrics ingest) | `http://homelab:8428/api/v1/write` or `http://100.87.33.61:8428/api/v1/write` |
| `9428` | VictoriaLogs (logs ingest) | `http://homelab:9428/insert/loki/api/v1/push` or `http://100.87.33.61:9428/insert/loki/api/v1/push` |
| `10428` | VictoriaTraces (OTLP traces) | `http://homelab:10428/insert/opentelemetry/v1/traces` or `http://100.87.33.61:10428/insert/opentelemetry/v1/traces` |
| `3000` | Grafana (UI, internal) | `http://homelab:3000` |
| `8090` | GlitchTip (ingest, loopback-only) | DSN host `homelab:8090` (loopback; use node URL for tailnet ingest, see below) |
| `4000` | Langfuse (ingest backend, internal) | `http://homelab:4000/api/public/ingestion` |

**Web UIs via per-service Tailscale nodes** (HTTPS, tailnet-only):

The human-facing **web UIs** are served via dedicated **Tailscale certificate nodes** —
each service is a real Tailscale host (no `tailscale serve`). Access by node FQDN:

| Service | Node URL |
|---|---|
| Grafana | `https://grafana.tail6d0ed4.ts.net` |
| Langfuse (web UI) | `https://langfuse.tail6d0ed4.ts.net` |
| Umami (admin UI) | `https://umami.tail6d0ed4.ts.net` |
| GlitchTip (admin UI) | `https://glitchtip.tail6d0ed4.ts.net` |
| LiteLLM (admin UI) | `https://litellm.tail6d0ed4.ts.net/ui/` |
| VictoriaMetrics | `https://vm.tail6d0ed4.ts.net` |
| VictoriaLogs | `https://vlogs.tail6d0ed4.ts.net` |
| VictoriaTraces | `https://vtraces.tail6d0ed4.ts.net` |
| Homelab hub (start page) | `https://hub.tail6d0ed4.ts.net` |

See [`infra/reverse-proxy/`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/reverse-proxy/) for the Caddyfile + [`docs/observability-dependency-map.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/docs/observability-dependency-map.md) for the architecture.

## How `homelab` works on FREE Tailscale (device name, not a custom record)

Free Tailscale has **no custom DNS records** — so `homelab` is a **device hostname**
via MagicDNS: whichever machine is *named* `homelab` resolves as `homelab.<tailnet>.ts.net`
(and short `homelab`) tailnet-wide.

- **Current (Mac mini):** the mini's device is named **`homelab`** (admin console →
  **Machines → the mini → ⋯ → Edit machine name**, or its OS hostname), so senders
  use `homelab` and resolve to the mini. Future host swaps = give the new box the
  `homelab` name (rename the old one off first) → zero sender changes.
- **Historical (DGX stopgap, retired):** during setup the backend ran briefly on
  the DGX, which **couldn't** be renamed `homelab` (it's the GPU box; SSH
  `dgx-llm-1`, gpu-mode reference it), so senders targeted `dgx-llm-1` directly.
  That stopgap is over.
- **The DGX → mini cutover was a ONE-TIME sender flip** (endpoint `dgx-llm-1` →
  `homelab`), now complete and stable.

To keep that one-time cutover trivial, senders read the endpoint from **env vars**
(`REMOTE_WRITE_URL`, `LOGS_WRITE_URL`, `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`,
`GLITCHTIP_DSN`) — you edit a couple of values, not code.

## Notes

- **Server side is unaffected** — each stack still binds to its *own* host IP
  (`*_LISTEN` in the compose `.env`, set by `bootstrap.sh`). `homelab` is only for
  *senders* resolving where to send.
- The Tailscale **ACL still gates ports** — `homelab` resolving doesn't bypass it;
  the host's tag still needs `3000/8428/9428/10428/8090/4000` granted.
- **The backend now runs on the mini**, which is named `homelab`, so senders point
  at `homelab` and no IPs are needed. (Historically, during the DGX stopgap,
  senders pointed at `dgx-llm-1`; that flip is done.)
