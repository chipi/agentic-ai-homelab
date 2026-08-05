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
        app_origin: https://closelistening.app
        unsubscribe_path: /api/app/comms/unsubscribe
        vapid_subject: mailto:info@closelistening.app

Onboarding a new tenant = a new entry + its templates/schema dir + its secrets. No code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

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

    def missing_email_secrets(self) -> list[str]:
        return [] if self.internal_token else [f"{self.name}:internal_token"]

    def missing_push_secrets(self) -> list[str]:
        m = []
        if not self.internal_token:
            m.append(f"{self.name}:internal_token")
        if not self.vapid_private_key:
            m.append(f"{self.name}:vapid_private_key")
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
        out[name] = TenantConfig(
            name=name,
            outbox_base_url=t["outbox_base_url"],
            internal_token=e.get(t.get("internal_token_env", ""), ""),
            mail_from=t["mail_from"],
            app_origin=t["app_origin"].rstrip("/"),
            unsubscribe_path=t.get("unsubscribe_path", "/api/app/comms/unsubscribe"),
            vapid_private_key=e.get(t.get("vapid_private_key_env", ""), ""),
            vapid_subject=t.get("vapid_subject", "mailto:info@" + t["app_origin"].split("//")[-1]),
            template_dir=base / "delivery" / "templates" / name,
            schema_dir=base / "schema" / name,
        )
    return out
