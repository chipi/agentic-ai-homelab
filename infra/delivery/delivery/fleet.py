"""Fleet builders — turn the tenant registry into runnable workers.

One registry-driven deployment. A channel service (email/push) builds one
:class:`DeliveryWorker` per tenant and runs them on threads; the events service builds a
single cross-tenant :class:`EventsPoller`. Shared Resend account; per-tenant identity."""

from __future__ import annotations

import logging
import threading
from typing import Callable

from .config import DeliveryConfig
from .envelope import Channel
from .events_poller import EventsPoller
from .outbox_client import OutboxClient
from .render import Renderer
from .resend_client import ResendClient
from .sent_index import SentIndex
from .tenant import TenantConfig
from .transports import EmailTransport, PushTransport, Transport
from .webpush import WebPushSender
from .worker import DeliveryWorker

logger = logging.getLogger(__name__)


def _sent_index_path(cfg: DeliveryConfig) -> str:
    # ONE shared sent-index across tenants — the cross-tenant events poller reads it.
    return f"{cfg.state_dir}/sent-index.jsonl"


def build_channel_workers(
    cfg: DeliveryConfig, tenants: dict[str, TenantConfig], channel: Channel
) -> list[DeliveryWorker]:
    """One worker per tenant for a channel. Tenants missing that channel's secrets are
    skipped with a warning (so a half-configured tenant never blocks the others)."""
    workers: list[DeliveryWorker] = []
    for name, t in tenants.items():
        missing = (
            t.missing_email_secrets() if channel is Channel.EMAIL else t.missing_push_secrets()
        )
        if missing:
            logger.warning(
                "skipping tenant %s on %s — missing: %s", name, channel.value, ", ".join(missing)
            )
            continue
        outbox = OutboxClient(t.outbox_base_url, t.internal_token, timeout_sec=cfg.http_timeout_sec)
        renderer = Renderer.for_tenant(t)
        transport: Transport
        if channel is Channel.EMAIL:
            resend = ResendClient(
                cfg.resend_api_key, base_url=cfg.resend_base_url, timeout_sec=cfg.http_timeout_sec
            )
            transport = EmailTransport(renderer, resend, t.mail_from)
            sent_index = SentIndex(_sent_index_path(cfg))
        else:
            sender = WebPushSender(
                t.vapid_private_key, t.vapid_subject, timeout_sec=cfg.http_timeout_sec
            )
            transport = PushTransport(renderer, sender)
            sent_index = None  # push bounces (410/404) come back inline, not via the events poll
        workers.append(
            DeliveryWorker(
                cfg,
                outbox,
                transport,
                channel,
                tenant=name,
                sent_index=sent_index,
                liveness_path=f"{cfg.state_dir}/live-{name}-{channel.value}",
            )
        )
    return workers


def build_events_poller(cfg: DeliveryConfig, tenants: dict[str, TenantConfig]) -> EventsPoller:
    """The single cross-tenant poller: one Resend account, routes suppression per tenant."""
    resend = ResendClient(
        cfg.resend_api_key, base_url=cfg.resend_base_url, timeout_sec=cfg.http_timeout_sec
    )
    outboxes = {
        name: OutboxClient(t.outbox_base_url, t.internal_token, timeout_sec=cfg.http_timeout_sec)
        for name, t in tenants.items()
    }
    return EventsPoller(cfg, resend, outboxes, SentIndex(_sent_index_path(cfg)))


def run_workers_forever(
    workers: list[DeliveryWorker], *, spawn: Callable[..., threading.Thread] = threading.Thread
) -> list:
    """Run each worker's loop on its own daemon thread; return the threads."""
    threads = []
    for w in workers:
        th = spawn(target=w.run_forever, daemon=True)
        th.start()
        threads.append(th)
    return threads
