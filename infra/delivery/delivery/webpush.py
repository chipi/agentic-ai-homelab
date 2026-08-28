"""Self-hosted Web Push — VAPID (RFC 8292) + aes128gcm (RFC 8291/8188) on `cryptography`
alone. No third-party push service, no pywebpush.

Two EC P-256 keypairs: the stable VAPID identity (server auth JWT) and an ephemeral
per-message keypair (ECDH → content key). ``encrypt_payload`` accepts salt + server key
overrides purely so the RFC 8291 Appendix A vector is reproducible in tests."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import struct
from dataclasses import dataclass
from typing import Optional

import httpx
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from .envelope import TerminalStatus
from .transports import PermanentDeliveryError, TransientDeliveryError

logger = logging.getLogger(__name__)
_CURVE = ec.SECP256R1()


def b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


@dataclass(frozen=True)
class VapidKeys:
    private_key: str
    public_key: str


def generate_vapid_keys() -> VapidKeys:
    priv = ec.generate_private_key(_CURVE)
    scalar = priv.private_numbers().private_value.to_bytes(32, "big")
    pub = priv.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    return VapidKeys(private_key=b64url_encode(scalar), public_key=b64url_encode(pub))


def _load_vapid_private(private_key_b64: str) -> ec.EllipticCurvePrivateKey:
    return ec.derive_private_key(int.from_bytes(b64url_decode(private_key_b64), "big"), _CURVE)


def _vapid_public_b64(priv: ec.EllipticCurvePrivateKey) -> str:
    return b64url_encode(
        priv.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    )


def build_vapid_header(
    private_key_b64: str, *, audience: str, subject: str, exp: int
) -> dict[str, str]:
    priv = _load_vapid_private(private_key_b64)
    header = b64url_encode(json.dumps({"typ": "JWT", "alg": "ES256"}).encode())
    claims = b64url_encode(json.dumps({"aud": audience, "exp": exp, "sub": subject}).encode())
    signing_input = f"{header}.{claims}".encode("ascii")
    r, s = decode_dss_signature(priv.sign(signing_input, ec.ECDSA(SHA256())))
    raw_sig = r.to_bytes(32, "big") + s.to_bytes(32, "big")  # JWS wants raw r||s, not DER
    jwt = f"{header}.{claims}.{b64url_encode(raw_sig)}"
    return {"Authorization": f"vapid t={jwt}, k={_vapid_public_b64(priv)}"}


def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    return hmac.new(prk, info + b"\x01", hashlib.sha256).digest()[:length]


def encrypt_payload(
    payload: bytes,
    *,
    ua_public: bytes,
    auth_secret: bytes,
    salt: Optional[bytes] = None,
    server_private: Optional[ec.EllipticCurvePrivateKey] = None,
) -> bytes:
    if salt is None:
        salt = os.urandom(16)
    if server_private is None:
        server_private = ec.generate_private_key(_CURVE)
    as_public = server_private.public_key().public_bytes(
        Encoding.X962, PublicFormat.UncompressedPoint
    )
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(_CURVE, ua_public)
    ecdh_secret = server_private.exchange(ec.ECDH(), ua_key)
    ikm = _hkdf(auth_secret, ecdh_secret, b"WebPush: info\x00" + ua_public + as_public, 32)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    ciphertext = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)
    # RFC 8188 §2.1: `rs` is the size of an encrypted RECORD (the ciphertext, incl.
    # the 16-byte AEAD tag + padding delimiter) — NOT the whole message. The header
    # bytes (salt/rs/keyid-len/as_public) must not be counted, or rs is inflated by
    # ~90 bytes and a payload in the ~3994–4096-byte band gets a wrong record size.
    # A single record shorter than rs is valid (it's the last record), so the 4096
    # floor stays.
    record_size = len(ciphertext)
    header = (
        salt
        + struct.pack(">I", max(record_size, 4096))
        + struct.pack("B", len(as_public))
        + as_public
    )
    return header + ciphertext


class WebPushSender:
    def __init__(
        self,
        vapid_private_key: str,
        vapid_subject: str,
        *,
        ttl_sec: int = 86400,
        timeout_sec: float = 15.0,
        clock: Optional[object] = None,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self._vapid_private = vapid_private_key
        self._subject = vapid_subject
        self._ttl = ttl_sec
        self._client = client or httpx.Client(timeout=timeout_sec)
        self._clock = clock

    def _now(self) -> int:
        import time

        return int(self._clock() if self._clock else time.time())  # type: ignore[operator]

    def send(self, subscription: dict, payload: bytes) -> None:
        endpoint = subscription["endpoint"]
        keys = subscription["keys"]
        body = encrypt_payload(
            payload,
            ua_public=b64url_decode(keys["p256dh"]),
            auth_secret=b64url_decode(keys["auth"]),
        )
        from urllib.parse import urlsplit

        parts = urlsplit(endpoint)
        headers = build_vapid_header(
            self._vapid_private,
            audience=f"{parts.scheme}://{parts.netloc}",
            subject=self._subject,
            exp=self._now() + 12 * 3600,
        )
        headers.update(
            {
                "Content-Encoding": "aes128gcm",
                "Content-Type": "application/octet-stream",
                "TTL": str(self._ttl),
            }
        )
        try:
            resp = self._client.post(endpoint, content=body, headers=headers)
        except httpx.HTTPError as exc:
            raise TransientDeliveryError(str(exc)) from exc
        if resp.status_code in (404, 410):
            raise PermanentDeliveryError(
                TerminalStatus.BOUNCED, f"dead subscription ({resp.status_code})"
            )
        if resp.status_code == 429 or resp.status_code >= 500:
            raise TransientDeliveryError(f"push {resp.status_code}: {resp.text[:120]}")
        if resp.status_code >= 400:
            raise PermanentDeliveryError(
                TerminalStatus.FAILED, f"push {resp.status_code}: {resp.text[:120]}"
            )

    def close(self) -> None:
        self._client.close()
