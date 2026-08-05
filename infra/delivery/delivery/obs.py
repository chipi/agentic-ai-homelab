"""Self-contained observability for the delivery worker (no app-repo dependency).

Three signals, all degrade to no-ops when their SDK/endpoint is absent so the send path
never depends on o11y being up:

- **Logs** — :func:`emit_event` writes ONE canonical JSONL line per event to stdout
  (``event_type=delivery`` / ``delivery_suppression`` / ``delivery_deadletter``). The
  homelab Alloy tails container stdout → VictoriaLogs. Stamps OTEL trace/span ids when a
  span is active (log↔trace correlation, ADR-119).
- **Metrics** — Prometheus counters/gauges/histograms in :mod:`delivery.metrics`, exposed
  on ``/metrics`` and scraped by the homelab Alloy.
- **Errors** — :func:`capture_error` sends dead-letters / hard failures to GlitchTip via
  ``sentry_sdk`` when ``DELIVERY_SENTRY_DSN`` is set.
- **Traces** — :func:`init_tracing` + :func:`span` wrap a drain/poll cycle in an OTEL span
  when the ``[obs]`` extra + ``OTEL_EXPORTER_OTLP_ENDPOINT`` are present.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

EVENT_SCHEMA = 1

_event_logger = logging.getLogger("delivery.events")
_fallback = logging.getLogger(__name__)

_TRACER = None  # set by init_tracing()


def _trace_context() -> dict[str, str]:
    try:
        from opentelemetry import trace as _t

        ctx = _t.get_current_span().get_span_context()
        if getattr(ctx, "is_valid", False):
            return {
                "trace_id": format(ctx.trace_id, "032x"),
                "span_id": format(ctx.span_id, "016x"),
            }
    except Exception:  # noqa: BLE001 — no OTEL / no active span
        pass
    return {}


def emit_event(event_type: str, **fields: Any) -> Optional[str]:
    """Emit one canonical JSONL event to stdout. Best-effort — never raises."""
    try:
        record: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "schema": EVENT_SCHEMA,
            "event_type": event_type,
        }
        record.update({k: v for k, v in fields.items() if v is not None})
        record.update(_trace_context())
        line = json.dumps(record, default=str, ensure_ascii=False)
        _event_logger.info("%s", line)
        return line
    except Exception:  # noqa: BLE001 — telemetry must never break the caller
        _fallback.debug("emit_event(%s) failed", event_type, exc_info=True)
        return None


def init_error_reporting() -> bool:
    """Wire GlitchTip via sentry_sdk if DELIVERY_SENTRY_DSN is set + the SDK is present."""
    dsn = os.environ.get("DELIVERY_SENTRY_DSN", "")
    if not dsn:
        return False
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=dsn, traces_sample_rate=0.0, environment=os.environ.get("DELIVERY_ENV", "prod")
        )
        return True
    except Exception:  # noqa: BLE001
        _fallback.warning("sentry_sdk init failed; errors won't reach GlitchTip", exc_info=True)
        return False


def capture_error(message: str, **tags: Any) -> None:
    """Send an error-level event to GlitchTip (no-op if unconfigured). ``tags`` (e.g.
    tenant, correlation_id) become GlitchTip tags so issues are filterable per tenant."""
    try:
        import sentry_sdk

        # new_scope() is the sentry-sdk 2.x API; push_scope() the 1.x fallback.
        scope_cm = getattr(sentry_sdk, "new_scope", None) or sentry_sdk.push_scope
        with scope_cm() as scope:
            for k, v in tags.items():
                if v is not None:
                    scope.set_tag(k, str(v))
            sentry_sdk.capture_message(message, level="error")
    except Exception:  # noqa: BLE001 — alerting must never break the drain
        _fallback.debug("capture_error dropped (sentry unavailable): %s", message)


def init_tracing(service_name: str = "delivery-worker") -> bool:
    """Set up an OTLP tracer if the OTEL extra + endpoint are present. Returns success."""
    global _TRACER
    if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)
        _TRACER = trace.get_tracer(service_name)
        return True
    except Exception:  # noqa: BLE001
        _fallback.warning("OTEL init failed; traces disabled", exc_info=True)
        return False


@contextlib.contextmanager
def span(name: str, **attrs: Any) -> Iterator[None]:
    """Wrap a block in an OTEL span when tracing is on; a plain no-op otherwise."""
    if _TRACER is None:
        yield
        return
    with _TRACER.start_as_current_span(name) as sp:  # type: ignore[union-attr]
        for k, v in attrs.items():
            with contextlib.suppress(Exception):
                sp.set_attribute(k, v)
        yield
