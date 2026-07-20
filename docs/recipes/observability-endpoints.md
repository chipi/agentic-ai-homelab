# Observability endpoints — the `homelab` name convention

All senders reference the **`homelab`** tailnet name, never a host IP. On free
Tailscale `homelab` is a **MagicDNS device name** — the machine *named* `homelab`
(the Mac mini once it's up). The DGX → mini move is a one-time sender cutover
(details below); after that it's stable, and future host swaps are free (rename
the new box `homelab`).

## The mapping (infra owns this)

`homelab` → the observability host. One host, one name, services by port:

| Port | Service | Sender path |
|---|---|---|
| `8428` | VictoriaMetrics (metrics ingest) | `http://homelab:8428/api/v1/write` |
| `9428` | VictoriaLogs (logs ingest) | `http://homelab:9428/insert/loki/api/v1/push` |
| `10428` | VictoriaTraces (OTLP traces) | `http://homelab:10428/insert/opentelemetry/v1/traces` |
| `3000` | Grafana (UI) | `http://homelab:3000` |
| `8090` | GlitchTip (errors) | DSN host `homelab:8090` |
| `4000` | Langfuse (LLM tracing) | `http://homelab:4000` |

## How `homelab` works on FREE Tailscale (device name, not a custom record)

Free Tailscale has **no custom DNS records** — so `homelab` is a **device hostname**
via MagicDNS: whichever machine is *named* `homelab` resolves as `homelab.<tailnet>.ts.net`
(and short `homelab`) tailnet-wide.

- **Permanent (Mac mini):** name the mini's device **`homelab`** (admin console →
  **Machines → the mini → ⋯ → Edit machine name**, or set its OS hostname).
  Senders then use `homelab` forever; future host swaps = give the new box the `homelab`
  name (rename the old one off first) → zero sender changes.
- **Now (DGX stopgap):** the DGX **can't** be renamed `homelab` — it's the GPU box and
  other config (SSH `dgx-llm-1`, gpu-mode) references it. So during the stopgap,
  senders target the DGX directly: `dgx-llm-1.<tailnet>.ts.net` or the IP
  `100.69.49.126`.
- **The DGX → mini move is a ONE-TIME sender cutover** (flip the endpoint from the
  DGX to `homelab`). After that it's stable.

To keep that one-time cutover trivial, senders read the endpoint from **env vars**
(`REMOTE_WRITE_URL`, `LOGS_WRITE_URL`, `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`,
`GLITCHTIP_DSN`) — you edit a couple of values, not code.

## Notes

- **Server side is unaffected** — each stack still binds to its *own* host IP
  (`*_LISTEN` in the compose `.env`, set by `bootstrap.sh`). `homelab` is only for
  *senders* resolving where to send.
- The Tailscale **ACL still gates ports** — `homelab` resolving doesn't bypass it;
  the host's tag still needs `3000/8428/9428/10428/8090/4000` granted.
- **Until `homelab` exists**, substitute the host IP (`100.69.49.126`) wherever a
  handover shows `homelab`.
