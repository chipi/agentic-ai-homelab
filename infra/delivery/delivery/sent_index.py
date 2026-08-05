"""Correlation index: Resend message_id → envelope id (+ user), so the events poller can
resolve a bounce/complaint back to the envelope it must suppress."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import NamedTuple, Optional

logger = logging.getLogger(__name__)


class SentRef(NamedTuple):
    tenant: str
    envelope_id: str
    user_id: str


class SentIndex:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._by_message: dict[str, SentRef] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            with self._path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        r = json.loads(line)
                        self._by_message[r["message_id"]] = SentRef(
                            r.get("tenant", ""), r["envelope_id"], r["user_id"]
                        )
        except Exception:  # noqa: BLE001
            logger.warning("sent index %s unreadable; starting empty", self._path, exc_info=True)
            self._by_message = {}

    def record(self, message_id: str, tenant: str, envelope_id: str, user_id: str) -> None:
        if not message_id:
            return
        with self._lock:
            self._by_message[message_id] = SentRef(tenant, envelope_id, user_id)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(
                    json.dumps(
                        {
                            "message_id": message_id,
                            "tenant": tenant,
                            "envelope_id": envelope_id,
                            "user_id": user_id,
                        }
                    )
                    + "\n"
                )

    def resolve(self, message_id: str) -> Optional[SentRef]:
        with self._lock:
            return self._by_message.get(message_id)

    def items(self) -> list[tuple[str, SentRef]]:
        """All (message_id, ref) pairs — the events poller iterates these to poll each
        sent message's Resend status."""
        with self._lock:
            return list(self._by_message.items())
