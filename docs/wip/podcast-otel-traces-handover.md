# Handover — instrument the podcast app with OpenTelemetry → VictoriaTraces

**For:** the VPS/podcast agent. **Goal:** the podcast app emits **OTLP traces**
(request/span waterfalls) to the self-hosted VictoriaTraces, tagged **dev** on
the Mac and **prod** on the VPS — viewable in Grafana next to metrics/logs.

This is *request/distributed* tracing (HTTP handler → DB → external call spans).
It's a different signal from the others the app sends — keep them straight:

| Signal | Where it goes | How |
|---|---|---|
| metrics + logs | VictoriaMetrics / VictoriaLogs | Alloy collector (`hosts/prod-podcast/`) |
| **traces (spans)** | **VictoriaTraces** | **OTEL SDK → OTLP (this doc)** |
| errors/exceptions | GlitchTip | Sentry SDK (`glitchtip-…-handover.md`) |
| LLM prompt/cost | Langfuse | capture layer (RFC-0001, later) |

> **`homelab`** is the Tailscale name of the observability host (a MagicDNS device name →
> the DGX now, the Mac mini later). See [`../recipes/observability-endpoints.md`](../recipes/observability-endpoints.md).
> Backend is on `dgx-llm-1` now (stopgap); flip to `homelab` after migration.

## Status (2026-07-20)

- **VictoriaTraces is LIVE** on the DGX. OTLP HTTP ingest (verified end-to-end):
  `http://homelab:10428/insert/opentelemetry/v1/traces`
- Grafana reads it via the **VictoriaTraces (Tempo)** and **(Jaeger)** datasources
  + the **Explore Traces** app.
- **ACL:** grant port **`10428`** to `tag:dgx-llm-host` in the Tailscale console
  (per-port allowlist, like `8428`/`9428`/`8090`/`4000`). Verify from the app host:
  `curl -m5 -o /dev/null -w "%{http_code}\n" http://homelab:10428/health` → `200`.

## Instrument (Python — env-var driven, zero app code if you can auto-instrument)

Install:
```sh
pip install opentelemetry-distro opentelemetry-exporter-otlp-proto-http
opentelemetry-bootstrap -a install     # pulls instrumentations for your libs (fastapi, requests, psycopg, …)
```

Set env (per host):
```sh
export OTEL_TRACES_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=http/protobuf
# NOTE: use the TRACES-specific var with the FULL path — VictoriaTraces' path is
# non-standard (/insert/opentelemetry/v1/traces), so the base-endpoint var (which
# auto-appends /v1/traces) will NOT work here.
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT="http://homelab:10428/insert/opentelemetry/v1/traces"
export OTEL_SERVICE_NAME="podcast-api"          # or -pipeline / -viewer per component
export OTEL_RESOURCE_ATTRIBUTES="deployment.environment=${APP_ENV:-dev}"   # prod on VPS
export OTEL_METRICS_EXPORTER=none               # metrics already via Alloy; traces only here
export OTEL_LOGS_EXPORTER=none                  # logs already via Alloy
```

Run under the auto-instrumentor:
```sh
opentelemetry-instrument python -m your_app        # wraps the process, no code change
```

Or programmatic (if you want manual spans):
```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
import os

provider = TracerProvider(resource=Resource.create({
    "service.name": "podcast-api",
    "deployment.environment": os.environ.get("APP_ENV", "dev"),
}))
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(
    endpoint="http://homelab:10428/insert/opentelemetry/v1/traces")))
trace.set_tracer_provider(provider)
```

## dev vs prod

Same as GlitchTip — `deployment.environment` from `APP_ENV` (`dev` on Mac, `prod`
on VPS). Filter by it in Grafana. Keep `service.name` per component
(`podcast-api`, `podcast-pipeline`, …) so the service graph is meaningful.

## Verify

Generate a request, then either:
- Grafana → **Explore** → *VictoriaTraces (Tempo)* → search by service, or the
  **Explore Traces** app, or
- `curl "http://homelab:10428/select/jaeger/api/services"` → your
  `service.name` should be listed.

## Notes / gotchas

- Reach VictoriaTraces at the **tailnet IP** `:10428`, never loopback/public.
- OTLP **HTTP** here (`http/protobuf`) at the `/insert/opentelemetry/v1/traces`
  path — not the OTLP gRPC `:4317`. If you prefer a local OTLP collector, the
  `hosts/prod-podcast/` Alloy can add an `otelcol.receiver.otlp` → forward to
  VictoriaTraces, but direct SDK export is simpler and is what's verified.
- Sampling: start at 100% (low volume). Add `OTEL_TRACES_SAMPLER=parentbased_traceidratio`
  + `OTEL_TRACES_SAMPLER_ARG=0.1` if it gets noisy.
- Background: `infra/observability/backend/README.md`; decision: `docs/adr/ADR-0005`.
