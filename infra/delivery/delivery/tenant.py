"""Tenant registry — the multi-tenant heart of the comms platform.

Each product (podcast player, orrery, an operator surface, …) is one tenant. The transport
ENGINE is shared; everything product-specific lives in a tenant entry: its outbox source,
sending identity (from-domain, app origin, unsubscribe path), VAPID keypair, and its own
template + schema directory. One Resend account (shared API key) verifies each tenant's
sending domain, so email needs no per-tenant key — only a per-tenant ``mail_from``.

Registry file (``tenants.yaml``) references secrets by ENV NAME, never inline, e.g.::

    tenants:
      podcast:
        outbox_base_url: http://127.0.0.1:8092
        internal_token_env: PODCAST_INTERNAL_OUTBOX_TOKEN
        vapid_private_key_env: PODCAST_VAPID_PRIVATE_KEY
        mail_from: "Close Listening <digest@mail.closelistening.app>"
        mail_from_by_template:              # optional: a different sender per email template
          magic-link.v1: "Close Listening <signin@mail.closelistening.app>"
        app_origin: https://closelistening.app
        unsubscribe_path: /api/app/comms/unsubscribe
        vapid_subject: mailto:info@closelistening.app

Onboarding a new tenant = a new entry + its templates/schema dir + its secrets. No code.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

log = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent  # infra/delivery/


@dataclass(frozen=True)
class TenantConfig:
    name: str
    outbox_base_url: str
    internal_token: str
    mail_from: str
    app_origin: str
    unsubscribe_path: str
    vapid_private_key: str
    vapid_subject: str
    template_dir: Path
    schema_dir: Path
    # APNs (native iOS push) — OPTIONAL (defaults keep existing constructors working). All four are
    # needed to send to `apns` subscriptions; absent = the tenant does Web Push only. `apns_sandbox`
    # targets Apple's sandbox host for development-signed device tokens; TestFlight/App Store = False.
    apns_key: str = ""
    apns_key_id: str = ""
    apns_team_id: str = ""
    apns_bundle_id: str = ""
    apns_sandbox: bool = False
    # FCM (native Android push) — OPTIONAL, same contract as APNs above. ONE value, because a
    # Google service-account JSON already carries the project id, the signing key and the token
    # endpoint; splitting it into fields would only create ways for them to disagree.
    fcm_service_account: str = ""
    # Sender per email TEMPLATE — OPTIONAL; `mail_from` is the default. A sign-in link from
    # `digest@` reads as a newsletter and gets filtered like one, so transactional mail can carry
    # its own address. Every address must be on a domain verified in Resend (and, for Sign in with
    # Apple relay addresses, registered with Apple's Private Email Relay).
    mail_from_by_template: dict[str, str] = field(default_factory=dict)

    def sender_for(self, template: str) -> str:
        """The From address for one email template: its override, else the tenant default."""
        return self.mail_from_by_template.get(template, self.mail_from)

    @property
    def has_webpush(self) -> bool:
        return bool(self.vapid_private_key)

    @property
    def has_apns(self) -> bool:
        return bool(
            self.apns_key and self.apns_key_id and self.apns_team_id and self.apns_bundle_id
        )

    @property
    def has_fcm(self) -> bool:
        return bool(self.fcm_service_account)

    def missing_email_secrets(self) -> list[str]:
        return [] if self.internal_token else [f"{self.name}:internal_token"]

    def missing_push_secrets(self) -> list[str]:
        m = []
        if not self.internal_token:
            m.append(f"{self.name}:internal_token")
        # The push worker serves web AND native subs, so at least ONE transport must be configured.
        if not self.has_webpush and not self.has_apns and not self.has_fcm:
            m.append(f"{self.name}:vapid_private_key|apns_key|fcm_service_account")
        return m


def load_registry(
    path: Optional[str] = None, env: Optional[dict[str, str]] = None, root: Optional[Path] = None
) -> dict[str, TenantConfig]:
    """Parse the tenant registry, resolving secret env-refs. Returns {name: TenantConfig}."""
    e = env if env is not None else dict(os.environ)
    base = root or _ROOT
    reg_path = Path(path or e.get("DELIVERY_TENANTS_FILE", str(base / "tenants.yaml")))
    data = yaml.safe_load(reg_path.read_text(encoding="utf-8")) or {}
    out: dict[str, TenantConfig] = {}
    for name, t in (data.get("tenants") or {}).items():
        # outbox_base_url is env-overridable (same *_env convention as secrets) so a
        # dev tenant can follow the outbox across hosts without editing the baked
        # registry: set `outbox_base_url_env` and the literal becomes the fallback
        # default. Used by podcast-dev so the mini worker can point at whichever
        # machine (mini host / laptop tailnet) is currently running the dev outbox.
        outbox_url = e.get(t.get("outbox_base_url_env", ""), "") or t.get("outbox_base_url", "")
        # A tenant with no resolvable outbox is SKIPPED, not loaded with a dead address.
        # podcast-dev used to carry a literal `http://host.docker.internal:8000` fallback — a
        # developer-laptop address. On the always-on homelab worker nothing listens there, so
        # every poll cycle produced one success for `podcast` and one ConnectError traceback for
        # `podcast-dev`: ~480/hour across the workers, ~11k/day, burying real errors in the log
        # anyone greps first during a delivery incident.
        #
        # The dev tenant now activates ONLY when its *_env var is exported (PODCAST_DEV_OUTBOX_URL),
        # which is exactly what a developer does locally and nobody does in prod. Fail silent and
        # absent beats fail loud and useless.
        if not outbox_url:
            continue
        # app_origin is env-overridable the same way (operator 2026-10-05): it is where every
        # email link points, so it decides which app a click lands in — and so which analytics
        # site counts it (each build carries its environment's Umami website id). The dev tenant
        # sends for real, so with the prod origin a test email's click opened PRODUCTION and was
        # counted there. podcast-dev now names no literal origin at all: it points at the dev web
        # app wherever it runs (today the developer's laptop over Tailscale), and a dev tenant with
        # an outbox but no origin is SKIPPED, never handed the prod address by default.
        app_origin = e.get(t.get("app_origin_env", ""), "") or t.get("app_origin", "")
        if not app_origin:
            log.warning(
                "tenant %s skipped: no app origin (set %s)", name, t.get("app_origin_env", "app_origin")
            )
            continue
        out[name] = TenantConfig(
            name=name,
            outbox_base_url=outbox_url,
            internal_token=e.get(t.get("internal_token_env", ""), ""),
            mail_from=t["mail_from"],
            mail_from_by_template={
                str(k): str(v) for k, v in (t.get("mail_from_by_template") or {}).items()
            },
            app_origin=app_origin.rstrip("/"),
            unsubscribe_path=t.get("unsubscribe_path", "/api/app/comms/unsubscribe"),
            vapid_private_key=e.get(t.get("vapid_private_key_env", ""), ""),
            vapid_subject=t.get("vapid_subject", "mailto:info@" + app_origin.split("//")[-1]),
            apns_key=e.get(t.get("apns_key_env", ""), ""),
            apns_key_id=t.get("apns_key_id", ""),
            apns_team_id=t.get("apns_team_id", ""),
            apns_bundle_id=t.get("apns_bundle_id", ""),
            apns_sandbox=bool(t.get("apns_sandbox", False)),
            fcm_service_account=e.get(t.get("fcm_service_account_env", ""), ""),
            template_dir=base / "delivery" / "templates" / name,
            schema_dir=base / "schema" / name,
        )
    return out
