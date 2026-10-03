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


ALL_FIXTURES = [
    "your-week-digest.v1.golden.json",
    "resurface-nudge.v1.golden.json",
    "daily-recap.v1.golden.json",
    "recommendations-digest.v1.golden.json",
]


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
    assert "https://closelistening.app/episode/" in html
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


def test_daily_recap_fixture_renders_email():
    # RFC-122 #2039 — a single-episode day renders the FULL recap.
    env = DeliveryEnvelope.from_dict(_fixture("daily-recap.v1.golden.json"))
    assert env.channel is Channel.EMAIL
    rendered = _renderer().render_email(env)
    assert rendered.subject == "Your recap · NVIDIA: The Machine That Makes the Machine"
    html = rendered.html
    assert "NVIDIA: The Machine That Makes the Machine" in html
    assert "The bottleneck was never compute" in html  # a key point
    assert "the real product" in html and "Jensen Huang" in html  # signature quote + speaker
    assert "Vertical integration" in html  # a top insight
    assert "Scaling Laws" in html  # topic chip
    assert "semiconductor supply chain" in html  # storyline
    assert "https://closelistening.app/episode/acquired-nvidia" in html  # deep link absolutised
    # The one-click unsubscribe is TYPE-AWARE — it silences the recap, not the weekly digest.
    # (The `&` is HTML-escaped to `&amp;` in the href — correct; the client unescapes it.)
    assert "ref=example-unsubscribe-ref" in html and "type=daily_recap" in html


def test_daily_recap_many_renders_compact_stack():
    # A multi-episode day renders the compact per-episode stack (built inline; the golden is count=1).
    base = _fixture("daily-recap.v1.golden.json")
    ep = base["payload"]["episodes"][0]
    base["payload"] = {
        "day": "2026-09-11",
        "count": 2,
        "episodes": [ep, {**ep, "title": "TSMC (Part II)", "deep_link": "/episode/tsmc-part-ii"}],
    }
    rendered = _renderer().render_email(DeliveryEnvelope.from_dict(base))
    assert rendered.subject == "Your day, recapped · 2 episodes"
    assert "TSMC (Part II)" in rendered.html
    assert "Open in Close Listening" in rendered.html  # the compact-stack per-episode CTA


def test_recommendations_fixture_renders_email():
    # wave-H monthly discovery digest — reuses the sections shape; must now render (was never sent).
    env = DeliveryEnvelope.from_dict(_fixture("recommendations-digest.v1.golden.json"))
    assert env.channel is Channel.EMAIL
    rendered = _renderer().render_email(env)
    assert "New for you" in rendered.html
    assert "New in what you follow" in rendered.html  # the new_in_interests section label
    assert "TSMC (Part II)" in rendered.html
    assert "https://closelistening.app/episode/" in rendered.html
    assert "Semiconductors" in rendered.html  # a graph_ref chip
    assert "September 2026" in rendered.subject  # monthly period label


# --- transactional envelopes (app-side #2272) -------------------------------------------------


def test_auth_link_envelope_parses_without_a_consent_snapshot() -> None:
    """A sign-in link has no account behind it, so it carries no consent snapshot.

    This used to raise KeyError before it could reach a template: `ConsentSnapshot.from_dict` read
    `d["unsubscribe_ref"]` directly while its two siblings used `.get` with defaults, so an absent
    snapshot was a hard parse failure rather than an absent snapshot.
    """
    import json
    from pathlib import Path

    from delivery.envelope import DeliveryEnvelope

    fixture = Path(__file__).resolve().parents[1] / "schema/podcast/fixtures/magic-link.v1.golden.json"
    env = DeliveryEnvelope.from_dict(json.loads(fixture.read_text()))
    assert env.consent_snapshot is None
    assert env.type == "auth_link"
    assert env.user_id == ""  # the schema requires exactly this for auth


def test_magic_link_email_renders_and_carries_no_unsubscribe() -> None:
    """The one template that must NOT offer an unsubscribe link.

    Every notification template ends with one. You cannot unsubscribe from being able to log in, and
    an auth envelope has no `unsubscribe_ref` to build the link from — so a footer here would render
    a dead URL into a real inbox.
    """
    import json
    from pathlib import Path

    from delivery.envelope import DeliveryEnvelope
    from delivery.render import Renderer

    root = Path(__file__).resolve().parents[1]
    env = DeliveryEnvelope.from_dict(
        json.loads((root / "schema/podcast/fixtures/magic-link.v1.golden.json").read_text())
    )
    rendered = Renderer(
        root / "delivery/templates/podcast", app_origin="https://closelistening.app"
    ).render_email(env)

    assert rendered.subject
    assert env.payload["link"] in rendered.html, "the sign-in link must reach the body"
    assert "unsubscribe" not in rendered.html.lower()
    # The one line that tells a person who did NOT request it that ignoring it is safe.
    assert "was not you" in rendered.html
