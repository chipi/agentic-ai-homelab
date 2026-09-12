"""Payload → HTML email / push notification. Pure, deterministic Jinja (D6: no LLM).

Aligned to the committed contract:
- digest payload = ``{sections: [{kind, items: [digestItem]}]}``
- nudge payload  = ``{highlight_count, lead: digestItem}``
- ``digestItem`` = ``{quote?, episode_slug, episode_title?, t_ms?, graph_refs[],
  deep_link, source?}``
- unsubscribe link uses ``consent_snapshot.unsubscribe_ref``
- ``deep_link`` is RELATIVE (``/player/...``); the email absolutises it against the app origin.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from jinja2.exceptions import TemplateNotFound

from .envelope import DeliveryEnvelope
from .tenant import TenantConfig


def _period_label(env, *, now: datetime | None = None) -> str:
    """Human label for the digest's period, derived from the envelope date (the worker has
    no period field in the contract). Daily → the single day ('Sep 11'); monthly → the month
    ('September 2026'); weekly (default) → the 7-day window ending at not_before/created_at."""
    basis = env.not_before or env.created_at or (now or datetime.now(timezone.utc))
    if basis.tzinfo is None:
        basis = basis.replace(tzinfo=timezone.utc)
    cadence = getattr(env.consent_snapshot, "cadence", "weekly")
    if cadence == "daily":
        return f"{basis.strftime('%b')} {basis.day}"
    if cadence == "monthly":
        return basis.strftime("%B %Y")
    start = basis - timedelta(days=6)
    return f"{start.strftime('%b')} {start.day} – {basis.strftime('%b')} {basis.day}"


class RenderError(RuntimeError):
    """Missing template or required payload field."""


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    html: str


@dataclass(frozen=True)
class RenderedPush:
    title: str
    body: str
    url: str
    tag: str


# Human labels for the digest section kinds.
_SECTION_LABELS = {
    "revisit": "Worth revisiting",
    "new_in_follows": "New from who you follow",
    "new_in_interests": "New in what you follow",
    "trending_in_your_corpus": "Trending in your corpus",
}


class Renderer:
    """Per-tenant renderer: its own template dir, app origin, and unsubscribe path."""

    def __init__(
        self,
        template_dir: Path | str,
        *,
        app_origin: str,
        unsubscribe_path: str = "/api/app/comms/unsubscribe",
    ) -> None:
        self._app_origin = app_origin.rstrip("/")
        self._unsubscribe_path = unsubscribe_path
        self._env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            # Autoescape ONLY the HTML bodies (extension is ".j2" for all, so an explicit
            # predicate — select_autoescape keys on extension and would leave escaping off).
            autoescape=lambda name: name is not None and name.endswith(".html.j2"),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._env.filters["abslink"] = self._abslink
        self._env.filters["section_label"] = lambda k: _SECTION_LABELS.get(k, k)

    @classmethod
    def for_tenant(cls, tenant: TenantConfig) -> "Renderer":
        return cls(
            tenant.template_dir,
            app_origin=tenant.app_origin,
            unsubscribe_path=tenant.unsubscribe_path,
        )

    def _abslink(self, deep_link: str) -> str:
        """Absolutise a relative in-app deep_link for an email context."""
        if deep_link.startswith("http://") or deep_link.startswith("https://"):
            return deep_link
        return f"{self._app_origin}{deep_link}"

    def unsubscribe_url(self, env: DeliveryEnvelope) -> str:
        """Public one-click unsubscribe link (app-owned endpoint, ref-based).

        Carries the envelope's ``type`` so the app disables the RIGHT list — e.g. unsubscribing
        from a ``daily_recap`` email must not silence the weekly ``digest``. Defaults to ``digest``
        (the app's own default), so existing digest emails are unchanged.
        """
        ref = env.consent_snapshot.unsubscribe_ref
        return f"{self._app_origin}{self._unsubscribe_path}?ref={ref}&type={env.type}"

    def _context(self, env: DeliveryEnvelope) -> dict[str, Any]:
        return {
            "payload": env.payload,
            "cadence": env.consent_snapshot.cadence,
            "period_label": _period_label(env),
            "unsubscribe_url": self.unsubscribe_url(env),
            "app_origin": self._app_origin,
        }

    def render_email(self, env: DeliveryEnvelope) -> RenderedEmail:
        ctx = self._context(env)
        try:
            subject = self._env.get_template(f"email/{env.template}.subject.j2").render(ctx)
            html = self._env.get_template(f"email/{env.template}.html.j2").render(ctx)
        except TemplateNotFound as exc:
            raise RenderError(f"no email template for {env.template!r}: {exc}") from exc
        return RenderedEmail(subject=subject.strip(), html=html)

    def render_push(self, env: DeliveryEnvelope) -> RenderedPush:
        try:
            raw = self._env.get_template(f"push/{env.template}.json.j2").render(self._context(env))
        except TemplateNotFound as exc:
            raise RenderError(f"no push template for {env.template!r}: {exc}") from exc
        data = json.loads(raw)
        return RenderedPush(
            title=data["title"],
            body=data["body"],
            url=self._abslink(data.get("url", "/")),
            tag=data.get("tag", env.template),
        )
