"""Apple Push Notification service (APNs) sender — token-based (JWT/ES256) over HTTP/2.

The iOS Capacitor app can't do Web Push (no Service Worker / PushManager in the WKWebView), so it
registers with APNs and stores its device token as an ``apns`` subscription. This is the push
transport for those, sitting beside :class:`delivery.webpush.WebPushSender` behind the same
``PushSender`` seam; :class:`DispatchingPushSender` routes by ``subscription["kind"]``.

Auth is a provider JWT signed with the tenant's APNs auth key (.p8, an EC P-256 key): header
``{alg: ES256, kid: <key id>}``, claims ``{iss: <team id>, iat: <now>}``. Apple lets a token be
reused for up to an hour and rate-limits minting, so we cache it and refresh well inside the hour.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

import httpx
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from .envelope import TerminalStatus
from .transports import PermanentDeliveryError, TransientDeliveryError
from .webpush import b64url_encode

logger = logging.getLogger(__name__)

# Apple's endpoints. Sandbox is for development-signed builds (Xcode/devicectl), production for
# TestFlight/App Store builds — the app's `aps-environment` entitlement decides which the device
# token belongs to, so the worker must target the matching host or Apple returns BadDeviceToken.
PROD_HOST = "https://api.push.apple.com"
SANDBOX_HOST = "https://api.sandbox.push.apple.com"
_JWT_REFRESH_SEC = 3000  # 50 min — inside Apple's 1-hour reuse window.


def _jwt_segment(obj: dict) -> str:
    return b64url_encode(json.dumps(obj, separators=(",", ":")).encode("utf-8"))


class ApnsSender:
    def __init__(
        self,
        auth_key_pem: str,
        key_id: str,
        team_id: str,
        topic: str,
        *,
        use_sandbox: bool = False,
        timeout_sec: float = 15.0,
        clock: Optional[object] = None,
        client: Optional[httpx.Client] = None,
    ) -> None:
        # Docker Compose `env_file` can't carry a multi-line value, so the .p8 is stored on ONE line
        # with literal `\n` escapes; restore real newlines here (a no-op on an already-multi-line PEM).
        pem = auth_key_pem.replace("\\n", "\n")
        self._priv = load_pem_private_key(pem.encode("utf-8"), password=None)
        if not isinstance(self._priv, ec.EllipticCurvePrivateKey):
            raise ValueError("APNs auth key must be an EC (P-256) private key")
        self._key_id = key_id
        self._team_id = team_id
        self._topic = topic
        self._host = SANDBOX_HOST if use_sandbox else PROD_HOST
        # APNs REQUIRES HTTP/2. httpx needs the `h2` extra for this.
        self._client = client or httpx.Client(http2=True, timeout=timeout_sec)
        self._clock = clock
        self._cached_jwt: Optional[str] = None
        self._cached_at = 0

    def _now(self) -> int:
        return int(self._clock() if self._clock else time.time())  # type: ignore[operator]

    def _bearer(self) -> str:
        now = self._now()
        if self._cached_jwt and now - self._cached_at < _JWT_REFRESH_SEC:
            return self._cached_jwt
        header = _jwt_segment({"alg": "ES256", "kid": self._key_id})
        claims = _jwt_segment({"iss": self._team_id, "iat": now})
        signing_input = f"{header}.{claims}".encode("ascii")
        r, s = decode_dss_signature(self._priv.sign(signing_input, ec.ECDSA(SHA256())))
        raw_sig = r.to_bytes(32, "big") + s.to_bytes(32, "big")  # JWS wants raw r||s, not DER
        self._cached_jwt = f"{header}.{claims}.{b64url_encode(raw_sig)}"
        self._cached_at = now
        return self._cached_jwt

    def send(self, subscription: dict, payload: bytes) -> None:
        # The app stores the device token directly; fall back to parsing the `apns://<token>` endpoint.
        token = subscription.get("token") or str(subscription.get("endpoint", "")).removeprefix(
            "apns://"
        )
        if not token:
            raise PermanentDeliveryError(TerminalStatus.FAILED, "apns subscription with no token")

        # The generic push payload ({title, body, url, tag}) becomes an APNs alert. `url`/`tag` ride
        # as custom keys the app reads on tap.
        p = json.loads(payload.decode("utf-8"))
        aps_body = {
            "aps": {"alert": {"title": p.get("title", ""), "body": p.get("body", "")}, "sound": "default"},
            "url": p.get("url"),
            "tag": p.get("tag"),
        }
        headers = {
            "authorization": f"bearer {self._bearer()}",
            "apns-topic": self._topic,
            "apns-push-type": "alert",
            "apns-priority": "10",
        }
        url = f"{self._host}/3/device/{token}"
        try:
            resp = self._client.post(url, content=json.dumps(aps_body).encode("utf-8"), headers=headers)
        except httpx.HTTPError as exc:
            raise TransientDeliveryError(str(exc)) from exc

        if resp.status_code == 200:
            return
        reason = ""
        try:
            reason = str(resp.json().get("reason", ""))
        except Exception:  # noqa: BLE001 — a non-JSON error body is just opaque
            reason = resp.text[:120]
        # 410 (Unregistered) or 400 BadDeviceToken = dead token → bounce so the app suppresses it.
        if resp.status_code == 410 or (resp.status_code == 400 and reason == "BadDeviceToken"):
            raise PermanentDeliveryError(
                TerminalStatus.BOUNCED, f"dead apns token ({resp.status_code} {reason})"
            )
        if resp.status_code == 429 or resp.status_code >= 500:
            raise TransientDeliveryError(f"apns {resp.status_code}: {reason}")
        raise PermanentDeliveryError(TerminalStatus.FAILED, f"apns {resp.status_code}: {reason}")

    def close(self) -> None:
        self._client.close()


class DispatchingPushSender:
    """Route each subscription to the transport its ``kind`` names (``webpush`` default, ``apns``).

    The push worker is one per tenant and handles a user's web AND native subscriptions; a kind with
    no configured sender is a permanent failure for that envelope, not a crash for the batch.
    """

    def __init__(self, senders: dict) -> None:
        self._senders = senders

    def send(self, subscription: dict, payload: bytes) -> None:
        kind = str(subscription.get("kind") or "webpush")
        sender = self._senders.get(kind)
        if sender is None:
            raise PermanentDeliveryError(
                TerminalStatus.FAILED, f"no push sender configured for kind={kind!r}"
            )
        sender.send(subscription, payload)

    def close(self) -> None:
        for s in self._senders.values():
            close = getattr(s, "close", None)
            if callable(close):
                close()
