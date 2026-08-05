"""GLOBAL (tenant-independent) config from the environment. Per-tenant identity lives in
the tenant registry (:mod:`delivery.tenant`). The Resend API key is shared — one account
verifies every tenant's sending domain."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Sequence

DEFAULT_BACKOFF_SCHEDULE_SEC: tuple[float, ...] = (2.0, 5.0, 15.0, 60.0)
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_POLL_INTERVAL_SEC = 30.0
DEFAULT_BATCH_LIMIT = 50


@dataclass(frozen=True)
class DeliveryConfig:
    # shared last-mile (one Resend account, many verified sender domains)
    resend_api_key: str = ""
    resend_base_url: str = "https://api.resend.com"
    # drain behaviour
    poll_interval_sec: float = DEFAULT_POLL_INTERVAL_SEC
    batch_limit: int = DEFAULT_BATCH_LIMIT
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    backoff_schedule_sec: Sequence[float] = field(
        default_factory=lambda: DEFAULT_BACKOFF_SCHEDULE_SEC
    )
    http_timeout_sec: float = 15.0
    # state + o11y
    state_dir: str = "/var/lib/delivery"
    metrics_port: int = 0
    tenants_file: str = ""  # empty → default tenants.yaml next to the package

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "DeliveryConfig":
        e = env if env is not None else dict(os.environ)

        def _f(k: str, d: float) -> float:
            v = e.get(k)
            return float(v) if v not in (None, "") else d

        def _i(k: str, d: int) -> int:
            v = e.get(k)
            return int(v) if v not in (None, "") else d

        return cls(
            resend_api_key=e.get("RESEND_API_KEY", ""),
            resend_base_url=e.get("RESEND_BASE_URL", cls.resend_base_url),
            poll_interval_sec=_f("DELIVERY_POLL_INTERVAL_SEC", DEFAULT_POLL_INTERVAL_SEC),
            batch_limit=_i("DELIVERY_BATCH_LIMIT", DEFAULT_BATCH_LIMIT),
            max_attempts=_i("DELIVERY_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS),
            http_timeout_sec=_f("DELIVERY_HTTP_TIMEOUT_SEC", 15.0),
            state_dir=e.get("DELIVERY_STATE_DIR", cls.state_dir),
            metrics_port=_i("DELIVERY_METRICS_PORT", 0),
            tenants_file=e.get("DELIVERY_TENANTS_FILE", ""),
        )

    def missing_shared_secrets(self) -> list[str]:
        return [] if self.resend_api_key else ["RESEND_API_KEY"]
