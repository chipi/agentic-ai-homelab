"""What filing and the stale sweep looked up, computed and wrote, recorded for an exact replay (ADR-0004 / RFC-0002
§9 step 1, the fleet session's part). Off unless SF_CAPTURE_PROBES=1, like capture.py; never raises into a cycle.

  results/filing/<the decision's capture file name>   one per filing decision (file_or_update, file_escalation):
      the issue it was given, the four keys, the ledger row it matched with the dimension it matched on, every GitHub
      call in order (method, path, payload, response or error), every clock reading in order, the ledger rows it
      wrote, and the result string. capture.record writes it under the decision's capture name, so one decision is one
      name in both folders. fleet-eval-data's exact_filing_replay.py replays it.
  results/sweeps/<UTC>Z.json                          one per stale sweep that ran: now, dry_run, the occurrences it
      read (count, last row, sha256 of the list: the rows themselves are dispositions.tsv's, append-only), the firing
      alert names, every GitHub call, and the summary.

Not recorded: the ledger's maintenance commands (filing.backfill_alert_keys, filing.retire_glitchtip_project) also
write filed.tsv, outside any decision, so no record has them. LAST_FILING holds one record: a decision that called
file_or_update twice before capture.record would keep only the second (none does today; escalation is one call).

New files only: probes/ is never written here (the freezer, outcome_count.py and the held-out split read every *.json
there as a capture). Records hold production data: mode 600, and scrubbed before anything leaves the host.
"""
import contextlib
import datetime
import hashlib
import json
import os

import config

LAST_FILING = None   # the finished record of the latest filing decision, for capture.record to write


def active():
    return config.CAPTURE_PROBES


def _results_dir():
    return os.path.dirname(config.CAPTURE_DIR.rstrip("/"))


class _Recorder:
    def __init__(self, kind):
        self.rec = {"kind": kind, "github": []}

    def note(self, key, value):
        self.rec[key] = value

    def append(self, key, value):
        self.rec.setdefault(key, []).append(value)


_CURRENT = None


def note(key, value):
    """Record a value on the running record (no-op when nothing is recording)."""
    if _CURRENT is not None:
        try:
            _CURRENT.note(key, json.loads(json.dumps(value, default=str)))
        except Exception:  # noqa: BLE001 — recording must not break filing
            pass


def append(key, value):
    if _CURRENT is not None:
        try:
            _CURRENT.append(key, json.loads(json.dumps(value, default=str)))
        except Exception:  # noqa: BLE001
            pass


@contextlib.contextmanager
def recording(ns, kind):
    """While active: wrap ns["_gh"] (a module's namespace: whatever _gh is now, the real client or a stand-in) so every
    call is recorded, and ns["_now"] when it has one, so every clock reading is recorded in order (`clock`: filing
    stamps its ledger rows with it). Restored afterwards. Yields the recorder, or None when off or one already runs."""
    global _CURRENT
    if not active() or _CURRENT is not None:
        yield None
        return
    rec = _Recorder(kind)
    inner = ns["_gh"]
    inner_now = ns.get("_now")

    def now():
        t = inner_now()
        rec.append("clock", t.isoformat())
        return t

    def gh(method, path, payload=None):
        call = {"method": method, "path": path, "payload": payload}
        try:
            out = inner(method, path, payload)
        except Exception as e:  # noqa: BLE001 — recorded, then raised as before
            call["error"] = f"{type(e).__name__}: {e}"[:300]
            rec.append("github", call)
            raise
        call["response"] = out
        try:
            rec.append("github", json.loads(json.dumps(call, default=str)))
        except Exception:  # noqa: BLE001
            pass
        return out

    ns["_gh"], _CURRENT = gh, rec
    if inner_now is not None:
        ns["_now"] = now
    try:
        yield rec
    finally:
        ns["_gh"], _CURRENT = inner, None
        if inner_now is not None:
            ns["_now"] = inner_now


def _write(path, obj):
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f, ensure_ascii=False, default=str)
    os.replace(tmp, path)


def write_filing(capture_path, fingerprint):
    """Write the latest filing record as results/filing/<capture's file name>, if it is this decision's."""
    global LAST_FILING
    rec, LAST_FILING = LAST_FILING, None
    if not rec or rec.get("fingerprint") != fingerprint or not capture_path:
        return None
    try:
        path = os.path.join(_results_dir(), "filing", os.path.basename(capture_path))
        _write(path, rec)
        return path
    except Exception as e:  # noqa: BLE001
        print(f"    [callrec] filing record skipped: {e}")
        return None


def write_sweep(rec, now, occurrences):
    """Write one stale sweep's record as results/sweeps/<UTC>Z.json."""
    try:
        rows = [list(o) for o in occurrences]
        rec.note("occurrences", {"count": len(rows), "last": rows[-1] if rows else None,
                                 "sha256": hashlib.sha256(json.dumps(rows).encode()).hexdigest()})
        stamp = now.astimezone(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = os.path.join(_results_dir(), "sweeps", f"{stamp}.json")
        _write(path, rec.rec)
        return path
    except Exception as e:  # noqa: BLE001
        print(f"    [callrec] sweep record skipped: {e}")
        return None
