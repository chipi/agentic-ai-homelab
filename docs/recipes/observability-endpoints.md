# Observability endpoints — the `obs` name convention

All senders reference the **`obs`** tailnet name, never a host IP. `obs` is a
**Tailscale custom DNS record** → the current observability host. Moving the host
(DGX → Mac mini) = repoint that **one record**; no sender changes.

## The mapping (infra owns this)

`obs` → the observability host. One host, one name, services by port:

| Port | Service | Sender path |
|---|---|---|
| `8428` | VictoriaMetrics (metrics ingest) | `http://obs:8428/api/v1/write` |
| `9428` | VictoriaLogs (logs ingest) | `http://obs:9428/insert/loki/api/v1/push` |
| `10428` | VictoriaTraces (OTLP traces) | `http://obs:10428/insert/opentelemetry/v1/traces` |
| `3000` | Grafana (UI) | `http://obs:3000` |
| `8090` | GlitchTip (errors) | DSN host `obs:8090` |
| `4000` | Langfuse (LLM tracing) | `http://obs:4000` |

## How `obs` works on FREE Tailscale (device name, not a custom record)

Free Tailscale has **no custom DNS records** — so `obs` is a **device hostname**
via MagicDNS: whichever machine is *named* `obs` resolves as `obs.<tailnet>.ts.net`
(and short `obs`) tailnet-wide.

- **Permanent (Mac mini):** name the mini's device **`obs`** (admin console →
  **Machines → the mini → ⋯ → Edit machine name**, or set its OS hostname).
  Senders then use `obs` forever; future host swaps = give the new box the `obs`
  name (rename the old one off first) → zero sender changes.
- **Now (DGX stopgap):** the DGX **can't** be renamed `obs` — it's the GPU box and
  other config (SSH `dgx-llm-1`, gpu-mode) references it. So during the stopgap,
  senders target the DGX directly: `dgx-llm-1.<tailnet>.ts.net` or the IP
  `100.69.49.126`.
- **The DGX → mini move is a ONE-TIME sender cutover** (flip the endpoint from the
  DGX to `obs`). After that it's stable.

To keep that one-time cutover trivial, senders read the endpoint from **env vars**
(`REMOTE_WRITE_URL`, `LOGS_WRITE_URL`, `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`,
`GLITCHTIP_DSN`) — you edit a couple of values, not code.

## Notes

- **Server side is unaffected** — each stack still binds to its *own* host IP
  (`*_LISTEN` in the compose `.env`, set by `bootstrap.sh`). `obs` is only for
  *senders* resolving where to send.
- The Tailscale **ACL still gates ports** — `obs` resolving doesn't bypass it;
  the host's tag still needs `3000/8428/9428/10428/8090/4000` granted.
- **Until `obs` exists**, substitute the host IP (`100.69.49.126`) wherever a
  handover shows `obs`.
