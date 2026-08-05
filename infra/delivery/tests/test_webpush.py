"""Web Push: RFC 8291 Appendix A vector (byte-exact) + VAPID header + 410→bounced."""

from __future__ import annotations

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from delivery.envelope import TerminalStatus
from delivery.transports import PermanentDeliveryError, TransientDeliveryError
from delivery.webpush import (
    WebPushSender,
    b64url_decode,
    b64url_encode,
    build_vapid_header,
    encrypt_payload,
    generate_vapid_keys,
)


def test_rfc8291_appendix_a_vector():
    ua_priv = ec.derive_private_key(
        int.from_bytes(b64url_decode("q1dXpw3UpT5VOmu_cf_v6ih07Aems3njxI-JWgLcM94"), "big"),
        ec.SECP256R1(),
    )
    ua_public = ua_priv.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    server_priv = ec.derive_private_key(
        int.from_bytes(b64url_decode("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"), "big"),
        ec.SECP256R1(),
    )
    body = encrypt_payload(
        b"When I grow up, I want to be a watermelon",
        ua_public=ua_public,
        auth_secret=b64url_decode("BTBZMqHH6r4Tts7J_aSIgg"),
        salt=b64url_decode("DGv6ra1nlYgDCS1FRnbzlw"),
        server_private=server_priv,
    )
    expected = (
        "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27ml"
        "mlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_yl95bQpu6cVPT"
        "pK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN"
    )
    assert b64url_encode(body) == expected


def test_vapid_keys_and_header():
    keys = generate_vapid_keys()
    assert len(b64url_decode(keys.private_key)) == 32 and len(b64url_decode(keys.public_key)) == 65
    hdr = build_vapid_header(
        keys.private_key,
        audience="https://fcm.googleapis.com",
        subject="mailto:x@y.com",
        exp=2000000000,
    )
    assert hdr["Authorization"].startswith("vapid t=") and ", k=" in hdr["Authorization"]


def _subscription():
    ua = ec.generate_private_key(ec.SECP256R1())
    p256dh = ua.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    return {
        "endpoint": "https://push.example/abc",
        "keys": {"p256dh": b64url_encode(p256dh), "auth": b64url_encode(b"0123456789abcdef")},
    }


def _sender(status_code: int):
    keys = generate_vapid_keys()
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status_code)))
    return WebPushSender(keys.private_key, "mailto:x@y.com", client=client, clock=lambda: 1_000_000)


def test_410_and_404_bounce():
    for code in (410, 404):
        with pytest.raises(PermanentDeliveryError) as ei:
            _sender(code).send(_subscription(), b'{"t":1}')
        assert ei.value.status is TerminalStatus.BOUNCED


def test_5xx_transient():
    with pytest.raises(TransientDeliveryError):
        _sender(503).send(_subscription(), b'{"t":1}')


def test_success_201():
    _sender(201).send(_subscription(), b'{"t":1}')
