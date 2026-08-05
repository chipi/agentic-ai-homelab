"""File-based idempotency ledger — defense-in-depth against a double-send after a crash
between send and status write-back. Records last-known state per envelope id."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SENDING = "sending"


class IdempotencyLedger:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._state: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            with self._path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        rec = json.loads(line)
                        self._state[rec["id"]] = rec["status"]
        except Exception:  # noqa: BLE001 — a corrupt ledger must not wedge the worker
            logger.warning("ledger %s unreadable; starting empty", self._path, exc_info=True)
            self._state = {}

    def status_of(self, envelope_id: str) -> Optional[str]:
        with self._lock:
            return self._state.get(envelope_id)

    def is_terminal(self, envelope_id: str) -> bool:
        st = self.status_of(envelope_id)
        return st is not None and st != SENDING

    def mark(self, envelope_id: str, status: str) -> None:
        with self._lock:
            self._state[envelope_id] = status
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"id": envelope_id, "status": status}) + "\n")
