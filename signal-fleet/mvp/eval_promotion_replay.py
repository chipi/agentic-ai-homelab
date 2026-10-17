"""Replay eval: a rolled-up signal the fleet decided to FILE is promoted on its next
recurrence, not after RETRIAGE_HOURS (or never).

The bug (2026-10-17 weekly review): the low-signal gate folds a one-event error into a
rollup, and promotion happens only in file_or_update. A recurrence within
RETRIAGE_HOURS of the last triage wrote a `recurrence` row and stopped, and after the
window the issue was re-triaged only if it was still among the 10 most recently seen.
6 fingerprints (12 count changes) stayed rollup lines for good, among them the fatal
PLAYER-1I on podcast_scraper#2000.

Input, frozen 2026-10-17:
  reference-recurrence/dispositions-2026-10-17.tsv.gz   every GlitchTip disposition row
  reference-filing/filed-2026-10-17.tsv                 the filed-ledger
Every historical recurrence (one per fingerprint and count change) is replayed through
the REAL orchestrator.run_glitchtip of
  baseline  orchestrator.py at BASE_REV (git)
  fix       the working tree
with that fingerprint's ledger as of the event, the filed-ledger as of the event, the
clock at the event, triage and recurrence writes recorded, never sent. Pass:
  - baseline: every event is a recurrence row, as history recorded (faithful);
  - fix: exactly the EXPECTED events re-triage; every other event acts as before.

  python3 eval_promotion_replay.py     # exit 1 on any failure
"""
import contextlib
import gzip
import importlib.util
import io
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DISP = os.path.join(HERE, "..", "reference-recurrence", "dispositions-2026-10-17.tsv.gz")
FILED = os.path.join(HERE, "..", "reference-filing", "filed-2026-10-17.tsv")
BASE_REV = "69f88f1"   # main before this fix
_TMP = tempfile.mkdtemp(prefix="sf-promo-replay-")
os.environ["SF_FILED_LEDGER"] = os.path.join(_TMP, "filed.tsv")
os.environ["SF_LEDGER"] = os.path.join(_TMP, "dispositions.tsv")
os.environ.setdefault("SF_OBSERV_DISABLED", "1")
os.environ.setdefault("GITHUB_TOKEN", "replay-never-sent")
sys.path.insert(0, HERE)

EXPECTED = {   # (fingerprint, new count): decided 'file', folded into a rollup, then recurred
    ("glitchtip:PODCAST-PIPELINE-4N", n) for n in (2, 3, 4, 5, 6)} | {
    ("glitchtip:PODCAST-PIPELINE-4P", 2), ("glitchtip:PODCAST-PIPELINE-4P", 3),
    ("glitchtip:PODCAST-PIPELINE-4R", 2), ("glitchtip:PODCAST-PIPELINE-53", 2),
    ("glitchtip:PODCAST-PIPELINE-93", 2), ("glitchtip:PODCAST-PIPELINE-93", 3),
    ("glitchtip:PLAYER-1I", 2)}


def _ts(v):
    m = re.match(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?(Z|[+-]\d\d:\d\d)?", (v or "").strip())
    if not m:
        return None
    tz = m.group(3) or "+00:00"
    return datetime.fromisoformat(f"{m.group(1)}.{(m.group(2) or '0').ljust(6, '0')[:6]}"
                                  f"{'+00:00' if tz == 'Z' else tz}")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _baseline():
    src = subprocess.run(["git", "-C", HERE, "show", f"{BASE_REV}:signal-fleet/mvp/orchestrator.py"],
                         capture_output=True, text=True, check=True).stdout
    tmp = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, dir=HERE, prefix="_orch_base_")
    tmp.write(src)
    tmp.close()
    try:
        return _load(tmp.name, "orchestrator_baseline")
    finally:
        os.unlink(tmp.name)


def _outcome(mod, header, fp_rows, filed_hdr, filed_rows, ev):
    import actions, config, filing, sources
    with open(os.environ["SF_LEDGER"], "w") as f:
        f.write(header + "\n" + "".join(r + "\n" for r in fp_rows))
    with open(os.environ["SF_FILED_LEDGER"], "w") as f:
        f.write(filed_hdr + "\n" + "".join(r + "\n" for r in filed_rows))
    config.LEDGER = os.environ["SF_LEDGER"]
    filing.FILED = os.environ["SF_FILED_LEDGER"]
    seen = []
    sources.glitchtip_unresolved = lambda limit=10: [{"replay": True}]
    sources.to_error_signal = lambda issue: dict(ev["signal"])
    actions.record_recurrence = lambda sig, base: seen.append("recurrence")
    actions.act = lambda *a, **k: None
    mod._triage_or_defer = lambda sig: seen.append("triage")
    mod._hours_since = lambda ts: (ev["at"] - _ts(ts)).total_seconds() / 3600
    with contextlib.redirect_stdout(io.StringIO()):
        mod.run_glitchtip(limit=10, dry_run=True)
    return seen[0] if seen else "skip"


def main():
    lines = gzip.open(DISP, "rt").read().splitlines()
    header, rows = lines[0], lines[1:]
    cols = header.split("\t")
    ti, oi, fi, di, ri = (cols.index(c) for c in ("ts", "occurrence_id", "fingerprint", "disposition", "reason"))
    filed = open(FILED).read().splitlines()
    filed_hdr, filed_rows = filed[0], [r for r in filed[1:] if r]
    filed_at = filed_hdr.split("\t").index("filed_at")
    by_fp, events, seen = {}, [], set()
    for idx, r in enumerate(rows):
        p = r.split("\t")
        if len(p) <= ri:
            continue
        by_fp.setdefault(p[fi], []).append(idx)
        if p[di] != "recurrence":
            continue
        m = re.search(r"count (\d+) -> (\d+)", p[ri])
        if not m or (p[fi], int(m.group(2))) in seen:
            continue
        seen.add((p[fi], int(m.group(2))))
        occ = p[oi]
        events.append({"idx": idx, "fp": p[fi], "count": int(m.group(2)), "at": _ts(p[ti]),
                       "signal": {"fingerprint": p[fi], "occurrence_id": occ, "source": "glitchtip",
                                  "alertname": p[cols.index("alertname")], "raw": {},
                                  "startsAt": occ.split("@", 1)[1] if "@" in occ else "",
                                  "labels": {"count": m.group(2)}}})
    base, fix = _baseline(), _load(os.path.join(HERE, "orchestrator.py"), "orchestrator_fix")
    fails, changed, same = [], [], 0
    for ev in events:
        fp_rows = [rows[i] for i in by_fp[ev["fp"]] if i < ev["idx"]]
        frows = [r for r in filed_rows if r.split("\t")[filed_at][:19] <= ev["at"].isoformat()[:19]]
        b = _outcome(base, header, fp_rows, filed_hdr, frows, ev)
        f = _outcome(fix, header, fp_rows, filed_hdr, frows, ev)
        if b != "recurrence":
            fails.append(f"{ev['fp']} count {ev['count']} @ {ev['at']:%Y-%m-%d %H:%M}: baseline {b}, history recorded a recurrence")
        key = (ev["fp"], ev["count"])
        if b != f:
            changed.append(f"    {ev['at']:%Y-%m-%d %H:%M} {ev['fp']:<32} count {ev['count']:<4} baseline {b:<10} -> fix {f}")
            if key not in EXPECTED or f != "triage":
                fails.append(f"{ev['fp']} count {ev['count']}: unexpected change {b} -> {f}")
        else:
            same += 1
            if key in EXPECTED:
                fails.append(f"{ev['fp']} count {ev['count']}: expected an immediate re-triage, fix gives {f}")
    print(f"Promotion replay — {len(events)} historical recurrences (one per fingerprint and count change)\n")
    print(f"  unchanged: {same}    changed: {len(changed)} (expected {len(EXPECTED)})")
    print("\n".join(changed))
    print("\n" + ("PASS" if not fails else "FAIL:\n  " + "\n  ".join(fails[:25])))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
