# Observability endpoints — the `homelab` name convention

All senders reference the **`homelab`** tailnet name, never a host IP. On free
Tailscale `homelab` is a **MagicDNS device name** — the machine *named* `homelab`,
which is the **Mac mini** (verified live 2026-07-25). The one-time DGX → mini
sender cutover is **done**; it's stable now, and future host swaps are free
(rename the new box `homelab`).

## The mapping (infra owns this)

`homelab` → the observability host. One host, one name, services by port:

| Port | Service | Sender path |
|---|---|---|
| `8428` | VictoriaMetrics (metrics ingest) | `http://homelab:8428/api/v1/write` |
| `9428` | VictoriaLogs (logs ingest) | `http://homelab:9428/insert/loki/api/v1/push` |
| `10428` | VictoriaTraces (OTLP traces) | `http://homelab:10428/insert/opentelemetry/v1/traces` |
| `3000` | Grafana (UI) | `http://homelab:3000` |
| `8090` | GlitchTip (errors) | DSN host `homelab:8090` |
| `4000` | Langfuse (LLM tracing) | ingest `http://homelab:4000/api/public/ingestion` |

The rows above are **sender / ingest** paths (how apps push telemetry). The
human-facing **web UIs** are served separately over HTTPS via `tailscale serve`
(tailnet-only), on dedicated TLS ports because several frontends can't run under
a stripped `/path` subpath. Base FQDN `https://homelab.tail6d0ed4.ts.net`:

| UI | URL |
|---|---|
| Grafana | `…/grafana` |
| Langfuse | `…:8443` |
| Umami | `…:8444` |
| GlitchTip | `…:8445` |
| LiteLLM (admin) | `…:10000/ui/` |
| VictoriaMetrics / Logs / Traces | `…/vm/vmui` · `…/vlogs` · `…/vtraces` |

See [`infra/homelab-serve/`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/homelab-serve/README.md) for the serve map + ACL.

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
