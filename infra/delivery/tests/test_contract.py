"""Contract test — the worker validated against the VENDORED seam schema + golden fixtures
(schema/, synced from the app repo). Mirrors the app-side test_delivery_envelope_contract
so the two tracks cannot drift. If a golden fixture fails to render, the contract moved —
align the worker, don't edit the vendored copy."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from delivery.envelope import Channel, DeliveryEnvelope
from delivery.render import Renderer
from delivery.tenant import load_registry

_ROOT = Path(__file__).resolve().parent.parent
_SCHEMA_DIR = _ROOT / "schema" / "podcast"
_FIXTURES = _SCHEMA_DIR / "fixtures"
_TENANTS = load_registry(str(_ROOT / "tenants.yaml"), env={}, root=_ROOT)


def _schema() -> dict:
    return json.loads((_SCHEMA_DIR / "delivery-envelope.schema.json").read_text())


def _fixture(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text())


def _renderer() -> Renderer:
    return Renderer.for_tenant(_TENANTS["podcast"])


ALL_FIXTURES = ["your-week-digest.v1.golden.json", "resurface-nudge.v1.golden.json"]


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_fixture_matches_vendored_schema(name):
    Draft202012Validator(_schema()).validate(_fixture(name))  # raises if the fixture drifts


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_worker_parses_fixture(name):
    env = DeliveryEnvelope.from_dict(_fixture(name))
    assert env.id
    assert env.consent_snapshot.unsubscribe_ref  # the ref (not token) the worker embeds


def test_digest_fixture_renders_email():
    env = DeliveryEnvelope.from_dict(_fixture("your-week-digest.v1.golden.json"))
    assert env.channel is Channel.EMAIL
    html = _renderer().render_email(env).html
    # graph_refs carried as chips (moat rule); relative deep_links absolutised; ref unsubscribe.
    assert "Jensen Huang" in html and "AI Safety" in html
    assert "https://closelistening.app/player/" in html
    assert "ref=example-unsubscribe-ref" in html
    assert "&lt;" not in html.split("<body")[0]  # sanity: head not double-escaped


def test_nudge_fixture_renders_push():
    env = DeliveryEnvelope.from_dict(_fixture("resurface-nudge.v1.golden.json"))
    assert env.channel is Channel.PUSH
    push = _renderer().render_push(env)
    assert push.title
    assert push.url.startswith("https://closelistening.app/")  # relative → absolutised
    assert push.tag == "resurface-nudge"


def test_nudge_fixture_also_renders_email():
    # A nudge can go by email too; ensure the email template handles payload.lead.
    env = DeliveryEnvelope.from_dict(_fixture("resurface-nudge.v1.golden.json"))
    html = _renderer().render_email(env).html
    assert "Jensen Huang" in html
    assert "ref=example-unsubscribe-ref" in html
