"""Firebase Cloud Messaging (FCM) sender — OAuth2 service account over the HTTP v1 API.

The Android Capacitor app can't do Web Push any more than the iOS one can, so it registers with
FCM and stores its device token as an ``fcm`` subscription. This is the push transport for those,
sitting beside :class:`delivery.apns.ApnsSender` and :class:`delivery.webpush.WebPushSender` behind
the same ``PushSender`` seam; :class:`delivery.apns.DispatchingPushSender` routes by
``subscription["kind"]`` and already has the slot — this fills it (podcast_scraper #2157).

Auth is OAuth2, not a self-signed provider token like APNs: a service-account JWT
(``{alg: RS256, kid: <private_key_id>}`` / ``{iss: <client_email>, scope: firebase.messaging,
aud: <token_uri>, iat, exp}``) is *exchanged* at Google's token endpoint for a short-lived access
token, which is what the send actually carries. Google issues those for an hour; we cache and
refresh inside that window, the same way the APNs sender caches its JWT.

Why the v1 API and not the old `fcm.googleapis.com/fcm/send` legacy endpoint: the legacy server
key was retired, and v1 is per-project with a scoped credential rather than one omnipotent key.

**Privacy, recorded because it was a decision and not an accident** (podcast_scraper #2157,
operator 2026-09-29): every Android notification transits Google's infrastructure, and Google sees
the delivery metadata — device token, app identity, timing — even though the payload rides inside.
FCM is the only supported Android push transport for `@capacitor/push-notifications`; the
alternative was shipping Android with no push at all. The operator accepted this explicitly.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

import httpx
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from .envelope import TerminalStatus
from .transports import PermanentDeliveryError, TransientDeliveryError
from .webpush import b64url_encode

logger = logging.getLogger(__name__)

FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token"
FCM_ENDPOINT = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"

# Google's access tokens last an hour. Refresh well inside it, as the APNs sender does with its JWT.
_TOKEN_REFRESH_SEC = 3000
# The assertion JWT itself is short-lived and single-use; an hour is the documented maximum.
_ASSERTION_TTL_SEC = 3600

# Errors that mean the token is dead and will never work again, so the envelope should BOUNCE and
# the app suppress the subscription — the same treatment APNs gives 410/BadDeviceToken. Everything
# else that is a 4xx is a permanent FAILURE (our bug or our config), and 429/5xx is transient.
_DEAD_TOKEN_STATUSES = {"UNREGISTERED", "NOT_FOUND", "INVALID_ARGUMENT"}


def _jwt_segment(obj: dict) -> str:
    return b64url_encode(json.dumps(obj, separators=(",", ":")).encode("utf-8"))


class FcmSender:
    """Send to one tenant's Android device tokens via FCM HTTP v1."""

    def __init__(
        self,
        service_account_json: str,
        *,
        timeout_sec: float = 15.0,
        clock: Optional[object] = None,
        client: Optional[httpx.Client] = None,
    ) -> None:
        try:
            sa = json.loads(service_account_json)
        except json.JSONDecodeError as exc:
            raise ValueError("FCM service account must be valid JSON") from exc

        missing = [k for k in ("client_email", "private_key", "project_id") if not sa.get(k)]
        if missing:
            raise ValueError(f"FCM service account missing: {', '.join(missing)}")

        # Same one-line-with-escapes problem the APNs key has: Docker Compose `env_file` cannot
        # carry a multi-line value, and a service-account private key is a multi-line PEM. Restoring
        # the newlines here is a no-op when the JSON already holds real ones.
        pem = str(sa["private_key"]).replace("\\n", "\n")
        priv = load_pem_private_key(pem.encode("utf-8"), password=None)
        if not isinstance(priv, rsa.RSAPrivateKey):
            # Caught here rather than at the first send, because an APNs .p8 (EC P-256) pasted into
            # this slot by mistake is a very easy error to make — the two credentials look alike.
            raise ValueError("FCM service account private_key must be an RSA key")

        self._priv = priv
        self._client_email = str(sa["client_email"])
        self._project_id = str(sa["project_id"])
        self._key_id = str(sa.get("private_key_id") or "")
        self._token_uri = str(sa.get("token_uri") or DEFAULT_TOKEN_URI)
        self._client = client or httpx.Client(timeout=timeout_sec)
        self._clock = clock
        self._cached_token: Optional[str] = None
        self._cached_at = 0

    def _now(self) -> int:
        return int(self._clock() if self._clock else time.time())  # type: ignore[operator]

    def _assertion(self, now: int) -> str:
        header = {"alg": "RS256", "typ": "JWT"}
        if self._key_id:
            header["kid"] = self._key_id
        claims = {
            "iss": self._client_email,
            "scope": FCM_SCOPE,
            "aud": self._token_uri,
            "iat": now,
            "exp": now + _ASSERTION_TTL_SEC,
        }
        signing_input = f"{_jwt_segment(header)}.{_jwt_segment(claims)}".encode("ascii")
        sig = self._priv.sign(signing_input, padding.PKCS1v15(), SHA256())
        return f"{signing_input.decode('ascii')}.{b64url_encode(sig)}"

    def _bearer(self) -> str:
        """The OAuth2 access token, minted from a fresh assertion and cached."""
        now = self._now()
        if self._cached_token and now - self._cached_at < _TOKEN_REFRESH_SEC:
            return self._cached_token
        try:
            resp = self._client.post(
                self._token_uri,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": self._assertion(now),
                },
            )
        except httpx.HTTPError as exc:
            # Reaching Google's token endpoint is a network operation like any other: a failure
            # here says nothing about the device token, so it must not burn the envelope.
            raise TransientDeliveryError(f"fcm token endpoint: {exc}") from exc

        if resp.status_code != 200:
            detail = resp.text[:160]
            if resp.status_code == 429 or resp.status_code >= 500:
                raise TransientDeliveryError(f"fcm token {resp.status_code}: {detail}")
            # A 400/401 here is a BAD CREDENTIAL — the service account is wrong, revoked, or not
            # entitled. Permanent, and worth saying plainly: this is the failure mode that had APNs
            # returning InvalidProviderToken for ten days without anyone noticing (#2068).
            raise PermanentDeliveryError(
                TerminalStatus.FAILED,
                f"fcm service account rejected ({resp.status_code}): {detail}",
            )

        token = str(resp.json().get("access_token") or "")
        if not token:
            raise TransientDeliveryError("fcm token endpoint returned no access_token")
        self._cached_token = token
        self._cached_at = now
        return token

    def send(self, subscription: dict, payload: bytes) -> None:
        # The app stores the device token directly; fall back to parsing the `fcm://<token>`
        # endpoint, mirroring how the APNs sender reads `apns://`.
        token = subscription.get("token") or str(subscription.get("endpoint", "")).removeprefix(
            "fcm://"
        )
        if not token:
            raise PermanentDeliveryError(TerminalStatus.FAILED, "fcm subscription with no token")

        # The generic push payload ({title, body, url, tag}) becomes an FCM message. `url`/`tag`
        # ride in `data`, which the app reads on tap — the same contract the APNs custom keys use.
        #
        # FCM requires every `data` value to be a STRING; a null or a number is a 400. So the two
        # optional fields are only included when present, rather than sent as None.
        p = json.loads(payload.decode("utf-8"))
        data = {k: str(p[k]) for k in ("url", "tag") if p.get(k) is not None}
        message: dict = {
            "message": {
                "token": token,
                "notification": {"title": p.get("title", ""), "body": p.get("body", "")},
                # High priority so a nudge is delivered while the device is dozing, matching the
                # APNs sender's `apns-priority: 10`.
                "android": {"priority": "high"},
            }
        }
        if data:
            message["message"]["data"] = data

        url = FCM_ENDPOINT.format(project_id=self._project_id)
        headers = {
            "authorization": f"Bearer {self._bearer()}",
            "content-type": "application/json",
        }
        try:
            resp = self._client.post(
                url, content=json.dumps(message).encode("utf-8"), headers=headers
            )
        except httpx.HTTPError as exc:
            raise TransientDeliveryError(str(exc)) from exc

        if resp.status_code == 200:
            return

        status, detail = self._error_of(resp)
        if status in _DEAD_TOKEN_STATUSES or resp.status_code == 404:
            raise PermanentDeliveryError(
                TerminalStatus.BOUNCED, f"dead fcm token ({resp.status_code} {status})"
            )
        if resp.status_code == 429 or resp.status_code >= 500:
            raise TransientDeliveryError(f"fcm {resp.status_code}: {detail}")
        raise PermanentDeliveryError(TerminalStatus.FAILED, f"fcm {resp.status_code}: {detail}")

    @staticmethod
    def _error_of(resp: httpx.Response) -> tuple[str, str]:
        """Pull FCM's symbolic error status out of the error body, tolerating any shape."""
        try:
            err = resp.json().get("error", {}) or {}
        except Exception:  # noqa: BLE001 — a non-JSON error body is just opaque
            return "", resp.text[:160]
        status = str(err.get("status") or "")
        detail = str(err.get("message") or "")[:160]
        # The precise reason lives in a typed detail; `status` alone can be a generic
        # INVALID_ARGUMENT for both a dead token and a malformed message.
        for d in err.get("details", []) or []:
            code = str(d.get("errorCode") or "")
            if code:
                status = code
                break
        return status, detail or resp.text[:160]

    def close(self) -> None:
        self._client.close()
