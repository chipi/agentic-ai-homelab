"""FCM sender + push dispatch (native Android push, podcast_scraper #2157)."""

import json
from urllib.parse import parse_qsl

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

from delivery.apns import DispatchingPushSender
from delivery.envelope import TerminalStatus
from delivery.fcm import FcmSender
from delivery.transports import PermanentDeliveryError, TransientDeliveryError

TOKEN_URI = "https://oauth2.googleapis.com/token"
SEND_URL = "https://fcm.googleapis.com/v1/projects/proj-42/messages:send"


def _rsa_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()


def _service_account(**over) -> str:
    sa = {
        "type": "service_account",
        "project_id": "proj-42",
        "private_key_id": "PKID1",
        "private_key": _rsa_pem(),
        "client_email": "pusher@proj-42.iam.gserviceaccount.com",
        "token_uri": TOKEN_URI,
    }
    sa.update(over)
    return json.dumps(sa)


def _sub() -> dict:
    return {
        "endpoint": "fcm://devtoken123",
        "kind": "fcm",
        "token": "devtoken123",
        "platform": "android",
    }


def _payload(**over) -> bytes:
    p = {"title": "A nudge", "body": "Worth revisiting", "url": "/library", "tag": "nudge"}
    p.update(over)
    return json.dumps(p).encode()


def _sender(handler, sa: str | None = None) -> FcmSender:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return FcmSender(sa or _service_account(), client=client, clock=lambda: 1_000_000)


def _token_ok(req: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"access_token": "ya29.TEST", "expires_in": 3599})


def test_success_exchanges_assertion_then_posts_to_the_project_endpoint():
    seen: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if str(req.url) == TOKEN_URI:
            seen["grant"] = req.content.decode()
            return _token_ok(req)
        seen["url"] = str(req.url)
        seen["auth"] = req.headers.get("authorization", "")
        seen["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"name": "projects/proj-42/messages/1"})

    _sender(handler).send(_sub(), _payload())

    # The access token is what the SEND carries — not the self-signed assertion. That is the whole
    # difference from APNs, and getting it backwards yields a 401 that looks like a bad key.
    # Parsed rather than substring-matched: the body is form-encoded, so the grant type arrives
    # percent-escaped and a naive `in` check fails against a perfectly correct request.
    grant = dict(parse_qsl(seen["grant"]))
    assert grant["grant_type"] == "urn:ietf:params:oauth:grant-type:jwt-bearer"
    assert grant["assertion"].count(".") == 2  # header.claims.signature
    assert seen["auth"] == "Bearer ya29.TEST"
    assert seen["url"] == SEND_URL
    msg = seen["body"]["message"]
    assert msg["token"] == "devtoken123"
    assert msg["notification"] == {"title": "A nudge", "body": "Worth revisiting"}
    assert msg["data"] == {"url": "/library", "tag": "nudge"}
    # High priority, so a nudge is delivered while the device dozes (mirrors apns-priority: 10).
    assert msg["android"]["priority"] == "high"


def test_access_token_is_cached_across_sends():
    calls = {"token": 0, "send": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if str(req.url) == TOKEN_URI:
            calls["token"] += 1
            return _token_ok(req)
        calls["send"] += 1
        return httpx.Response(200, json={})

    s = _sender(handler)
    s.send(_sub(), _payload())
    s.send(_sub(), _payload())
    # Google rate-limits token minting; one exchange must serve both sends.
    assert calls == {"token": 1, "send": 2}


def test_data_omits_absent_fields_rather_than_sending_null():
    seen: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if str(req.url) == TOKEN_URI:
            return _token_ok(req)
        seen["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={})

    _sender(handler).send(_sub(), _payload(url=None, tag=None))
    # FCM rejects a non-string `data` value with a 400, so absent must mean absent.
    assert "data" not in seen["body"]["message"]


def test_token_falls_back_to_the_endpoint_scheme():
    seen: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if str(req.url) == TOKEN_URI:
            return _token_ok(req)
        seen["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={})

    _sender(handler).send({"endpoint": "fcm://fromendpoint", "kind": "fcm"}, _payload())
    assert seen["body"]["message"]["token"] == "fromendpoint"


def test_missing_token_is_permanent():
    s = _sender(lambda req: httpx.Response(200, json={}))
    with pytest.raises(PermanentDeliveryError) as e:
        s.send({"kind": "fcm"}, _payload())
    assert e.value.status is TerminalStatus.FAILED


@pytest.mark.parametrize("code,status", [(404, "NOT_FOUND"), (400, "UNREGISTERED")])
def test_dead_token_bounces_so_the_app_suppresses_it(code, status):
    def handler(req: httpx.Request) -> httpx.Response:
        if str(req.url) == TOKEN_URI:
            return _token_ok(req)
        return httpx.Response(code, json={"error": {"status": status, "message": "gone"}})

    with pytest.raises(PermanentDeliveryError) as e:
        _sender(handler).send(_sub(), _payload())
    assert e.value.status is TerminalStatus.BOUNCED


def test_typed_error_detail_wins_over_the_generic_status():
    # FCM returns a generic INVALID_ARGUMENT for both a dead token and a malformed message; the
    # typed detail is what distinguishes them, so it must be what we route on.
    def handler(req: httpx.Request) -> httpx.Response:
        if str(req.url) == TOKEN_URI:
            return _token_ok(req)
        return httpx.Response(
            400,
            json={
                "error": {
                    "status": "INVALID_ARGUMENT",
                    "message": "bad token",
                    "details": [{"errorCode": "UNREGISTERED"}],
                }
            },
        )

    with pytest.raises(PermanentDeliveryError) as e:
        _sender(handler).send(_sub(), _payload())
    assert e.value.status is TerminalStatus.BOUNCED


@pytest.mark.parametrize("code", [429, 500, 503])
def test_throttling_and_outages_are_transient(code):
    def handler(req: httpx.Request) -> httpx.Response:
        if str(req.url) == TOKEN_URI:
            return _token_ok(req)
        return httpx.Response(code, json={"error": {"status": "UNAVAILABLE"}})

    with pytest.raises(TransientDeliveryError):
        _sender(handler).send(_sub(), _payload())


def test_rejected_service_account_is_permanent_and_says_so():
    # The failure mode that had APNs silently returning InvalidProviderToken for ten days (#2068).
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_grant"})

    with pytest.raises(PermanentDeliveryError) as e:
        _sender(handler).send(_sub(), _payload())
    assert e.value.status is TerminalStatus.FAILED
    assert "service account rejected" in str(e.value)


def test_token_endpoint_outage_is_transient_not_a_burnt_envelope():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    with pytest.raises(TransientDeliveryError):
        _sender(handler).send(_sub(), _payload())


def test_an_apns_p8_in_the_fcm_slot_is_rejected_at_construction():
    # Both credentials are .p8-ish EC/RSA PEMs with 10-ish character ids; pasting the Apple one
    # here is an easy mistake, and it should fail loudly now rather than at 3am on a send.
    ec_pem = (
        ec.generate_private_key(ec.SECP256R1())
        .private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
        .decode()
    )
    with pytest.raises(ValueError, match="RSA"):
        FcmSender(_service_account(private_key=ec_pem))


def test_malformed_service_account_is_rejected_at_construction():
    with pytest.raises(ValueError, match="valid JSON"):
        FcmSender("not json")
    with pytest.raises(ValueError, match="missing"):
        FcmSender(json.dumps({"project_id": "p"}))


def test_dispatcher_routes_fcm_to_the_fcm_sender():
    calls: list[str] = []

    class Spy:
        def __init__(self, name):
            self.name = name

        def send(self, sub, payload):
            calls.append(self.name)

    d = DispatchingPushSender({"webpush": Spy("webpush"), "apns": Spy("apns"), "fcm": Spy("fcm")})
    d.send(_sub(), _payload())
    assert calls == ["fcm"]


def test_dispatcher_fails_one_envelope_when_fcm_is_unconfigured():
    # The state between "the Android app registers tokens" and "FCM is stood up": a clear permanent
    # failure for that envelope, not a crash for the batch.
    d = DispatchingPushSender({"webpush": object()})
    with pytest.raises(PermanentDeliveryError) as e:
        d.send(_sub(), _payload())
    assert "kind='fcm'" in str(e.value)
