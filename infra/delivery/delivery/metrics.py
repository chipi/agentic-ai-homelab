"""Prometheus metrics, guarded so the package runs without prometheus_client. Scraped by
the homelab Alloy (job=delivery); the Grafana "Delivery worker" board reads these."""

from __future__ import annotations

import logging
from typing import Any

try:
    from prometheus_client import Counter, Gauge, Histogram

    _ENABLED = True
except Exception:  # noqa: BLE001 — o11y optional; no-op stubs
    _ENABLED = False

    class _Noop:
        def labels(self, *_a: Any, **_k: Any) -> "_Noop":
            return self

        def inc(self, *_a: Any, **_k: Any) -> None:
            pass

        def observe(self, *_a: Any, **_k: Any) -> None:
            pass

        def set(self, *_a: Any, **_k: Any) -> None:
            pass

    def _noop_metric(*_a: Any, **_k: Any) -> _Noop:
        return _Noop()

    Counter = Gauge = Histogram = _noop_metric  # type: ignore[misc,assignment]


# Every series carries `tenant` so the platform is observable per-product.
SENT_TOTAL = Counter(
    "delivery_sent_total",
    "Terminal outcomes reported to the outbox.",
    ["tenant", "channel", "template", "status"],
)
ATTEMPTS_TOTAL = Counter(
    "delivery_attempts_total", "Individual send attempts.", ["tenant", "channel", "result"]
)
PENDING = Gauge(
    "delivery_batch_pending", "Envelopes returned by the last /pending poll.", ["tenant", "channel"]
)
SEND_SECONDS = Histogram(
    "delivery_send_seconds", "Wall-clock per successful send.", ["tenant", "channel"]
)
POLL_CURSOR_LAG = Gauge(
    "delivery_events_cursor_age_seconds",
    "Seconds since the events poller last advanced its cursor.",
    ["tenant"],
)


def enabled() -> bool:
    return _ENABLED


def start_metrics_server(port: int) -> bool:
    """Expose the registry on 0.0.0.0:port/metrics. No-op if port<=0 or SDK absent."""
    if port <= 0 or not _ENABLED:
        return False
    try:
        from prometheus_client import start_http_server

        start_http_server(port)
        return True
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).warning("metrics server failed on :%d", port, exc_info=True)
        return False
