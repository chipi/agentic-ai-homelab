"""APNs sender + push dispatch (native iOS push)."""

import base64
import json

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    load_pem_private_key,
)

from delivery.apns import ApnsSender, DispatchingPushSender
from delivery.transports import PermanentDeliveryError, TransientDeliveryError
from delivery.envelope import TerminalStatus


def _p8() -> str:
    """A throwaway EC P-256 key in PEM — the shape of an APNs .p8 auth key."""
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()


def _sub() -> dict:
    return {"endpoint": "apns://devtoken123", "kind": "apns", "token": "devtoken123", "platform": "ios"}


def _sender(handler, *, sandbox=False) -> ApnsSender:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return ApnsSender(
        _p8(), "KEY123", "TEAM456", "app.closelistening.player",
        use_sandbox=sandbox, client=client, clock=lambda: 1_000_000,
    )


def test_success_posts_alert_to_device_with_bearer_and_topic():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["auth"] = req.headers.get("authorization", "")
        seen["topic"] = req.headers.get("apns-topic", "")
        seen["body"] = json.loads(req.content.decode())
        return httpx.Response(200)

    _sender(handler).send(_sub(), json.dumps({"title": "Rising", "body": "New", "url": "/x", "tag": "t"}).encode())

    assert seen["url"] == "https://api.push.apple.com/3/device/devtoken123"
    assert seen["auth"].startswith("bearer ") and seen["auth"].count(".") == 2  # JWT header.claims.sig
    assert seen["topic"] == "app.closelistening.player"
    assert seen["body"]["aps"]["alert"] == {"title": "Rising", "body": "New"}
    assert seen["body"]["url"] == "/x"


def test_sandbox_targets_sandbox_host():
    seen = {}
    _sender(lambda r: (seen.__setitem__("host", r.url.host), httpx.Response(200))[1], sandbox=True).send(
        _sub(), b'{"title":"t","body":"b"}'
    )
    assert seen["host"] == "api.sandbox.push.apple.com"


def test_410_unregistered_bounces():
    with pytest.raises(PermanentDeliveryError) as ei:
        _sender(lambda r: httpx.Response(410, json={"reason": "Unregistered"})).send(_sub(), b'{"title":"t"}')
    assert ei.value.status == TerminalStatus.BOUNCED


def test_400_bad_device_token_bounces():
    with pytest.raises(PermanentDeliveryError) as ei:
        _sender(lambda r: httpx.Response(400, json={"reason": "BadDeviceToken"})).send(_sub(), b'{"title":"t"}')
    assert ei.value.status == TerminalStatus.BOUNCED


def test_5xx_is_transient():
    with pytest.raises(TransientDeliveryError):
        _sender(lambda r: httpx.Response(503, json={"reason": "InternalServerError"})).send(_sub(), b'{"title":"t"}')


def test_other_4xx_is_permanent_failed():
    with pytest.raises(PermanentDeliveryError) as ei:
        _sender(lambda r: httpx.Response(403, json={"reason": "InvalidProviderToken"})).send(_sub(), b'{"title":"t"}')
    assert ei.value.status == TerminalStatus.FAILED


def test_single_line_escaped_pem_is_accepted():
    # Docker Compose env_file can't hold multi-line values, so the .p8 ships as one line with literal
    # `\n`; ApnsSender must un-escape it (this is the actual deploy format).
    escaped = _p8().replace("\n", "\\n")
    s = ApnsSender(escaped, "K", "T", "b", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200))))
    s.send(_sub(), b'{"title":"t","body":"b"}')  # constructs + signs without error


def test_non_ec_key_rejected():
    with pytest.raises(ValueError):
        ApnsSender("-----BEGIN PRIVATE KEY-----\nnot a key\n-----END PRIVATE KEY-----", "k", "t", "b")


def test_jwt_is_reused_within_the_hour():
    # A valid EC key; sign twice and confirm the bearer is cached (Apple rate-limits minting).
    s = _sender(lambda r: httpx.Response(200))
    b1 = s._bearer()
    b2 = s._bearer()
    assert b1 == b2
    # Parse the header segment to confirm the key id / alg.
    header = json.loads(base64.urlsafe_b64decode(b1.split(".")[0] + "=="))
    assert header == {"alg": "ES256", "kid": "KEY123"}


class _Rec:
    def __init__(self):
        self.calls = []

    def send(self, sub, payload):
        self.calls.append((sub, payload))


def test_dispatch_routes_by_kind():
    web, apns = _Rec(), _Rec()
    d = DispatchingPushSender({"webpush": web, "apns": apns})
    d.send({"kind": "apns", "token": "x"}, b"{}")
    d.send({"endpoint": "https://push/x", "keys": {}}, b"{}")  # no kind → webpush default
    assert len(apns.calls) == 1 and len(web.calls) == 1


def test_dispatch_unknown_kind_is_permanent():
    d = DispatchingPushSender({"webpush": _Rec()})
    with pytest.raises(PermanentDeliveryError):
        d.send({"kind": "apns", "token": "x"}, b"{}")


def test_pem_roundtrips():
    # Sanity: the throwaway key really is a loadable EC key (guards the test's own fixture).
    assert isinstance(load_pem_private_key(_p8().encode(), password=None), ec.EllipticCurvePrivateKey)
