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
