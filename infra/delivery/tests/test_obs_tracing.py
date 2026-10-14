"""init_tracing names the service from OTEL_SERVICE_NAME (one name per worker), not a constant."""

from __future__ import annotations

import sys
import types

import pytest

from delivery import obs


@pytest.fixture
def fake_otel(monkeypatch):
    """Minimal stand-ins for the OTel SDK modules init_tracing imports; records the resource."""
    seen: dict = {}
    # init_tracing sets the module-level tracer; restore it so later tests' spans stay no-ops.
    monkeypatch.setattr(obs, "_TRACER", obs._TRACER)

    class Resource:
        @staticmethod
        def create(attrs):
            seen["attrs"] = dict(attrs)
            return attrs

    class TracerProvider:
        def __init__(self, resource):
            self.resource = resource

        def add_span_processor(self, _):
            pass

    mods = {
        "opentelemetry": types.SimpleNamespace(
            trace=types.SimpleNamespace(set_tracer_provider=lambda p: None, get_tracer=lambda n: n)
        ),
        "opentelemetry.exporter.otlp.proto.http.trace_exporter": types.SimpleNamespace(
            OTLPSpanExporter=lambda: None
        ),
        "opentelemetry.sdk.resources": types.SimpleNamespace(Resource=Resource),
        "opentelemetry.sdk.trace": types.SimpleNamespace(TracerProvider=TracerProvider),
        "opentelemetry.sdk.trace.export": types.SimpleNamespace(BatchSpanProcessor=lambda e: None),
    }
    for name, mod in mods.items():
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://vt:10428")
    return seen


def test_service_name_comes_from_env(monkeypatch, fake_otel):
    monkeypatch.setenv("OTEL_SERVICE_NAME", "delivery-push")
    assert obs.init_tracing() is True
    assert fake_otel["attrs"]["service.name"] == "delivery-push"


def test_default_name_without_env(monkeypatch, fake_otel):
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)
    assert obs.init_tracing() is True
    assert fake_otel["attrs"]["service.name"] == "delivery-worker"


def test_no_endpoint_no_tracing(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    assert obs.init_tracing() is False


def test_trace_headers_empty_when_tracing_off(monkeypatch):
    monkeypatch.setattr(obs, "_TRACER", None)
    assert obs.trace_headers() == {}


def test_trace_headers_carry_the_active_context(monkeypatch):
    def _inject(carrier):
        carrier["traceparent"] = "00-" + "a" * 32 + "-" + "b" * 16 + "-01"

    monkeypatch.setattr(obs, "_TRACER", object())
    monkeypatch.setitem(
        sys.modules, "opentelemetry.propagate", types.SimpleNamespace(inject=_inject)
    )
    assert obs.trace_headers() == {"traceparent": "00-" + "a" * 32 + "-" + "b" * 16 + "-01"}


def test_outbox_calls_continue_the_trace(monkeypatch):
    # delivery.send and the app's /internal/outbox span were two traces (2026-10-14: the same
    # envelope sat in trace d4c25b2f... on delivery and 9ce89186... on player-api).
    import httpx

    from delivery import outbox_client
    from delivery.envelope import TerminalStatus

    seen = []

    def _handler(request):
        seen.append(
            (
                request.method,
                request.headers.get("traceparent"),
                request.headers.get("x-internal-token"),
            )
        )
        if request.method == "GET":
            return httpx.Response(200, json={"envelopes": []})
        return httpx.Response(200, json={})

    tp = "00-" + "c" * 32 + "-" + "d" * 16 + "-01"
    monkeypatch.setattr(outbox_client, "trace_headers", lambda: {"traceparent": tp})
    client = httpx.Client(
        base_url="http://app",
        headers={"X-Internal-Token": "t"},
        transport=httpx.MockTransport(_handler),
    )
    oc = outbox_client.OutboxClient("http://app", "t", client=client)
    oc.fetch_pending("email", 5)
    oc.report_status("env-1", TerminalStatus.DELIVERED)
    assert seen == [("GET", tp, "t"), ("POST", tp, "t")]


def test_real_span_context_reaches_the_outbox(monkeypatch):
    # With the real SDK: the traceparent the app receives names the worker's active span, so the
    # app's span becomes its child (one trace from delivery.drain to /internal/outbox).
    import httpx
    from opentelemetry.sdk.trace import TracerProvider

    from delivery import outbox_client

    tracer = TracerProvider().get_tracer("test")
    monkeypatch.setattr(obs, "_TRACER", tracer)
    seen = []

    def _handler(request):
        seen.append(request.headers.get("traceparent"))
        return httpx.Response(200, json={"envelopes": []})

    client = httpx.Client(base_url="http://app", transport=httpx.MockTransport(_handler))
    oc = outbox_client.OutboxClient("http://app", "t", client=client)
    with tracer.start_as_current_span("delivery.drain") as sp:
        oc.fetch_pending("email", 1)
        ctx = sp.get_span_context()
    version, trace_id, parent_id, flags = seen[0].split("-")
    assert (version, trace_id, parent_id) == ("00", f"{ctx.trace_id:032x}", f"{ctx.span_id:016x}")
    assert int(flags, 16) & 0x01  # sampled; other bits (e.g. W3C level-2 random-id) may be set
