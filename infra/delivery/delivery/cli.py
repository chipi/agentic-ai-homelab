"""Console entry points (pyproject [project.scripts]). Registry-driven, multi-tenant.

    delivery-worker --channel email [--once]   # one worker per tenant, on threads
    delivery-worker --channel push  [--once]
    delivery-events [--once]                    # single cross-tenant poller
    delivery-gen-vapid                          # one-time VAPID keypair (per tenant)

SIGTERM/SIGINT → graceful stop of every worker (finish current batch, exit). Pause lever."""

from __future__ import annotations

import argparse
import logging
import signal
import sys

from .config import DeliveryConfig
from .envelope import Channel
from .fleet import build_channel_workers, build_events_poller, run_workers_forever
from .metrics import start_metrics_server
from .obs import init_error_reporting, init_tracing
from .tenant import load_registry
from .webpush import generate_vapid_keys

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def _init_obs() -> None:
    if init_error_reporting():
        logger.info("GlitchTip error reporting on")
    if init_tracing():
        logger.info("OTEL tracing on")


def _load(cfg: DeliveryConfig):
    tenants = load_registry(cfg.tenants_file or None)
    logger.info("tenant registry: %s", ", ".join(tenants) or "(none)")
    if cfg.missing_shared_secrets():
        logger.error("missing shared secrets: %s", ", ".join(cfg.missing_shared_secrets()))
    return tenants


def run_worker(argv: list[str] | None = None) -> int:
    _setup_logging()
    _init_obs()
    p = argparse.ArgumentParser(description="Drain every tenant's outbox for one channel.")
    p.add_argument("--channel", choices=["email", "push"], required=True)
    p.add_argument("--once", action="store_true", help="drain a single batch per tenant and exit")
    args = p.parse_args(argv)

    cfg = DeliveryConfig.from_env()
    channel = Channel(args.channel)
    tenants = _load(cfg)
    if channel is Channel.EMAIL and cfg.missing_shared_secrets():
        return 2
    workers = build_channel_workers(cfg, tenants, channel)
    if not workers:
        logger.error("no runnable tenants for channel=%s (check registry + secrets)", channel.value)
        return 2

    if start_metrics_server(cfg.metrics_port):
        logger.info("metrics on :%d/metrics", cfg.metrics_port)

    if args.once:
        for w in workers:
            logger.info(
                "drain %s: %s", w._tenant, w.drain_once()
            )  # noqa: SLF001 — CLI introspection
        return 0

    def _stop(signum, _frame):
        logger.info("signal %s — stopping all workers", signum)
        for w in workers:
            w.stop()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    threads = run_workers_forever(workers)
    for th in threads:
        while th.is_alive():
            th.join(timeout=1.0)
    return 0


def poll_events(argv: list[str] | None = None) -> int:
    _setup_logging()
    _init_obs()
    p = argparse.ArgumentParser(description="Poll Resend events (cross-tenant) for bounces.")
    p.add_argument("--once", action="store_true", help="poll a single page and exit")
    args = p.parse_args(argv)

    cfg = DeliveryConfig.from_env()
    tenants = _load(cfg)
    if cfg.missing_shared_secrets():
        return 2
    poller = build_events_poller(cfg, tenants)
    if start_metrics_server(cfg.metrics_port):
        logger.info("metrics on :%d/metrics", cfg.metrics_port)
    if args.once:
        logger.info("single poll complete: %d suppression(s)", poller.poll_once())
        return 0
    signal.signal(signal.SIGTERM, lambda *_: poller.stop())
    signal.signal(signal.SIGINT, lambda *_: poller.stop())
    poller.run_forever()
    return 0


def gen_vapid(argv: list[str] | None = None) -> int:
    keys = generate_vapid_keys()
    print(f"VAPID_PRIVATE_KEY={keys.private_key}")
    print(f"VAPID_PUBLIC_KEY={keys.public_key}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(run_worker())
