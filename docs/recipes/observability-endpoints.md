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

## Create / move the record (operator, Tailscale admin console)

- **DNS → Custom records** → add `obs` → the observability host's tailnet IP
  (currently the DGX `100.69.49.126`). Resolves tailnet-wide.
- **On the Mac-mini move:** edit that record → the mini's IP. That's the whole
  cutover for senders.
- If custom records aren't available on your plan, the fallback is a single
  `OBS_HOST` env var per sender (one line each to change on a move).

## Notes

- **Server side is unaffected** — each stack still binds to its *own* host IP
  (`*_LISTEN` in the compose `.env`, set by `bootstrap.sh`). `obs` is only for
  *senders* resolving where to send.
- The Tailscale **ACL still gates ports** — `obs` resolving doesn't bypass it;
  the host's tag still needs `3000/8428/9428/10428/8090/4000` granted.
- **Until `obs` exists**, substitute the host IP (`100.69.49.126`) wherever a
  handover shows `obs`.
