"""Per-channel transports: render + send + classify the outcome. The worker owns retry,
the idempotency ledger, and status write-back; a transport only renders + hands to the
wire and says what happened."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional, Protocol

from .envelope import DeliveryEnvelope, TerminalStatus
from .render import Renderer
from .resend_client import ResendClient, ResendPermanentError, ResendTransientError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeliveryOutcome:
    status: TerminalStatus
    detail: Optional[str] = None
    message_id: Optional[str] = None


class TransientDeliveryError(RuntimeError):
    """Retry with backoff; dead-letter after the attempt cap."""


class PermanentDeliveryError(RuntimeError):
    """No retry — carries the terminal status to report (usually bounced)."""

    def __init__(self, status: TerminalStatus, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


class Transport(Protocol):
    def deliver(self, env: DeliveryEnvelope) -> DeliveryOutcome: ...


class EmailTransport:
    def __init__(self, renderer: Renderer, resend: ResendClient, mail_from: str) -> None:
        self._renderer = renderer
        self._resend = resend
        self._mail_from = mail_from

    def deliver(self, env: DeliveryEnvelope) -> DeliveryOutcome:
        to = env.recipient.email
        if not to:
            raise PermanentDeliveryError(TerminalStatus.FAILED, "email channel with no address")
        rendered = self._renderer.render_email(env)
        # RFC 8058 one-click unsubscribe uses the same ref-based endpoint. The correlation
        # header (= envelope id) makes the message traceable in Resend too, end-to-end.
        unsub = self._renderer.unsubscribe_url(env)
        headers = {
            "List-Unsubscribe": f"<{unsub}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            "X-Correlation-Id": env.id,
        }
        try:
            result = self._resend.send_email(
                sender=self._mail_from,
                to=to,
                subject=rendered.subject,
                html=rendered.html,
                idempotency_key=env.id,
                headers=headers,
            )
        except ResendTransientError as exc:
            raise TransientDeliveryError(str(exc)) from exc
        except ResendPermanentError as exc:
            raise PermanentDeliveryError(TerminalStatus.BOUNCED, str(exc)) from exc
        return DeliveryOutcome(status=TerminalStatus.DELIVERED, message_id=result.message_id)


class PushSender(Protocol):
    def send(self, subscription: dict, payload: bytes) -> None: ...


class PushTransport:
    """A 410/404 from the push endpoint = dead subscription → bounced (app suppresses it)."""

    def __init__(self, renderer: Renderer, sender: PushSender) -> None:
        self._renderer = renderer
        self._sender = sender

    def deliver(self, env: DeliveryEnvelope) -> DeliveryOutcome:
        sub = env.recipient.push_subscription
        if not sub:
            raise PermanentDeliveryError(TerminalStatus.FAILED, "push channel with no subscription")
        rendered = self._renderer.render_push(env)
        payload = json.dumps(
            {
                "title": rendered.title,
                "body": rendered.body,
                "url": rendered.url,
                "tag": rendered.tag,
            }
        ).encode("utf-8")
        self._sender.send(sub, payload)
        return DeliveryOutcome(status=TerminalStatus.DELIVERED)
