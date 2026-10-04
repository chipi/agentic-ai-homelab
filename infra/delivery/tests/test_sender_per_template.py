"""A sender per email template: sign-in links from signin@, digests from digest@ (2026-10-04)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from delivery.envelope import Channel, DeliveryEnvelope, Recipient
from delivery.tenant import load_registry
from delivery.transports import EmailTransport

_REGISTRY = """
tenants:
  podcast:
    outbox_base_url: http://podcast:8092
    mail_from: "Close Listening <digest@mail.closelistening.app>"
    mail_from_by_template:
      magic-link.v1: "Close Listening <signin@mail.closelistening.app>"
    app_origin: https://closelistening.app
  orrery:
    outbox_base_url: http://orrery:9200
    mail_from: "Orrery <updates@mail.orrerylearn.com>"
    app_origin: https://orrerylearn.com
"""


def _registry(tmp_path: Path):
    for t in ("podcast", "orrery"):
        (tmp_path / "delivery" / "templates" / t / "email").mkdir(parents=True)
    reg = tmp_path / "tenants.yaml"
    reg.write_text(_REGISTRY)
    return load_registry(str(reg), env={}, root=tmp_path)


def test_the_override_applies_to_its_template_only(tmp_path: Path) -> None:
    podcast = _registry(tmp_path)["podcast"]
    assert podcast.sender_for("magic-link.v1") == "Close Listening <signin@mail.closelistening.app>"
    assert podcast.sender_for("new-episodes.v1") == "Close Listening <digest@mail.closelistening.app>"


def test_a_tenant_without_overrides_keeps_its_one_sender(tmp_path: Path) -> None:
    orrery = _registry(tmp_path)["orrery"]
    assert orrery.mail_from_by_template == {}
    assert orrery.sender_for("magic-link.v1") == "Orrery <updates@mail.orrerylearn.com>"


class _Resend:
    def __init__(self) -> None:
        self.senders: list[str] = []

    def send_email(self, *, sender: str, **_: object) -> SimpleNamespace:
        self.senders.append(sender)
        return SimpleNamespace(message_id="m1")


class _Renderer:
    def render_email(self, _env: object) -> SimpleNamespace:
        return SimpleNamespace(subject="s", html="<p>h</p>")

    def unsubscribe_url(self, _env: object) -> str:
        return "https://x/unsub"


def _envelope(template: str) -> DeliveryEnvelope:
    return DeliveryEnvelope(
        id=f"e-{template}",
        user_id="u1",
        channel=Channel.EMAIL,
        template=template,
        recipient=Recipient(email="a@example.com"),
        consent_snapshot=None,
    )


def test_the_transport_sends_each_template_from_its_own_address(tmp_path: Path) -> None:
    podcast = _registry(tmp_path)["podcast"]
    resend = _Resend()
    transport = EmailTransport(_Renderer(), resend, podcast.mail_from, podcast.mail_from_by_template)  # type: ignore[arg-type]
    transport.deliver(_envelope("magic-link.v1"))
    transport.deliver(_envelope("new-episodes.v1"))
    assert resend.senders == [
        "Close Listening <signin@mail.closelistening.app>",
        "Close Listening <digest@mail.closelistening.app>",
    ]


def test_the_shipped_registry_sends_sign_in_links_from_signin(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parent.parent
    shipped = load_registry(
        str(root / "tenants.yaml"), env={"PODCAST_DEV_OUTBOX_URL": "http://dev:8000"}, root=root
    )
    for name in ("podcast", "podcast-dev"):
        if name in shipped:
            assert shipped[name].sender_for("magic-link.v1").endswith("<signin@mail.closelistening.app>")
            assert shipped[name].sender_for("new-episodes.v1").endswith("<digest@mail.closelistening.app>")
