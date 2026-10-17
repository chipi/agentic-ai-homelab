"""Replay eval for three filing fixes from the 2026-10-17 weekly review, baseline vs fix.

  A  short-id reuse (filing): a recreated GlitchTip project restarts its counter, so a
     new issue inherits an old ledger row's fingerprint (ORRERY-DEV-1 -> orrery#429).
  B  short-id reuse (GitHub -> GlitchTip sync, #100): the same row made the sync resolve
     the new issue from an unrelated old GitHub close (audit log 2026-10-17 07:52).
  C  fatal events in the low-signal rollup: PLAYER-I (iOS SIGABRT), PLAYER-L (watchdog
     kill) and PLAYER-1I (Android process death) were rollup lines on #2000.
  D  one provider-auth failure, several issues: the 10-16 nightly filed #2371-#2374
     (+#2377 on 10-17), the 10-14 dev run #2354-#2357.

Input, frozen 2026-10-17:
  reference-filing/filed-2026-10-17.tsv         the live filed-ledger
  reference-filing/identity-2026-10-17.json     every GlitchTip issue (any status), the
      dispositions alert name per ledger fingerprint, and GitHub state/title/created/
      closed/duplicateOf for every issue the ledger points to (titles scrubbed).
Baseline = filing.py / glitchtip_sync.py at BASE_REV (git), fix = the working tree.
GitHub reads come from the frozen state; writes are recorded, never sent.

Pass:
  A  every reused row: baseline acts on the old issue (faithful), fix never does; every
     other row (incl. Grafana rows, whose later startsAt is normal) acts exactly as before.
  B  baseline resolves ORRERY-DEV-1 (what the live sync did); fix skips every reused row
     and changes nothing else (except merges whose target was a reused row).
  C  baseline: every rollup row is low-signal (faithful); fix: low-signal except exactly
     the fatal ones; PLAYER-1I files its own issue.
  D  sequential filing sim, world as at each filing: baseline reproduces history (each
     issue-opening row opens an issue); every row the fix folds onto an earlier issue is
     either an expected case or the operator's own duplicateOf link points at the same
     issue; #2371 and #2354 absorb their storms; no fold crosses a project.

  python3 eval_identity_replay.py     # exit 1 on any failure
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "..", "reference-filing", "filed-2026-10-17.tsv")
CORPUS = os.path.join(HERE, "..", "reference-filing", "identity-2026-10-17.json")
BASE_REV = "237371c"   # main before these fixes
GROUP_RULES_SINCE = "2026-08-20"   # f9a6b14 (2026-08-19) last changed GROUP_RULES
NOW = datetime(2026, 10, 17, 15, 30, tzinfo=timezone.utc)
_TMP = tempfile.mkdtemp(prefix="sf-identity-replay-")
os.environ["SF_FILED_LEDGER"] = os.path.join(_TMP, "filed.tsv")
shutil.copy(LEDGER, os.environ["SF_FILED_LEDGER"])
os.environ.setdefault("SF_OBSERV_DISABLED", "1")
os.environ.setdefault("GITHUB_TOKEN", "replay-never-sent")
sys.path.insert(0, HERE)

EXPECTED_FOLDS = {   # row's own issue -> issue it should fold onto (the operator's 10-17 closes)
    "chipi/podcast_scraper#2372": "chipi/podcast_scraper#2371",
    "chipi/podcast_scraper#2373": "chipi/podcast_scraper#2371",
    "chipi/podcast_scraper#2374": "chipi/podcast_scraper#2371",
    "chipi/podcast_scraper#2377": "chipi/podcast_scraper#2371",
    "chipi/podcast_scraper#2355": "chipi/podcast_scraper#2354",
    "chipi/podcast_scraper#2356": "chipi/podcast_scraper#2354",
    "chipi/podcast_scraper#2357": "chipi/podcast_scraper#2354",
}


def _ts(v):
    """ISO time -> datetime on Python 3.9 too (it parses only 3- or 6-digit fractions)."""
    m = re.match(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?(Z|[+-]\d\d:\d\d)?$", (v or "").strip())
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


def _baseline(rel, name):
    src = subprocess.run(["git", "-C", HERE, "show", f"{BASE_REV}:signal-fleet/mvp/{rel}"],
                         capture_output=True, text=True, check=True).stdout
    tmp = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, dir=HERE, prefix=f"_{name}_")
    tmp.write(src)
    tmp.close()
    try:
        return _load(tmp.name, name)
    finally:
        os.unlink(tmp.name)


def _stub(mod, c, writes, at=NOW):
    states, dups = c["states"], c["duplicate_of"]

    def issue_state(repo, n):
        s = states.get(f"{repo}#{n}", {"state": "open", "reason": "", "closed_at": "", "labels": []})
        return {"state": s["state"], "labels": s["labels"], "reason": s["reason"], "url": "",
                "closed_at": _ts(s["closed_at"])}

    def gh(method, path, payload=None):
        if method != "GET":
            writes.append((method, path, payload or {}))
        return {"number": 999999, "html_url": "replay"}

    mod.issue_state = issue_state
    mod._gh = gh
    mod._now = lambda: at
    mod._today = lambda: at.strftime("%Y-%m-%d")
    for f in ("_glitchtip_note", "_grafana_annotation", "_ensure_labels"):
        setattr(mod, f, lambda *a, **k: None)
    mod._milestone_number = lambda *a, **k: None
    mod._related_issues = lambda *a, **k: []
    mod.duplicate_of = lambda repo, n: (
        (dups[f"{repo}#{n}"].split("#")[0], int(dups[f"{repo}#{n}"].split("#")[1]))
        if dups.get(f"{repo}#{n}") else None)


def _outcome(mod, c, signal, issue=None):
    shutil.copy(LEDGER, os.environ["SF_FILED_LEDGER"])
    mod.FILED = os.environ["SF_FILED_LEDGER"]
    writes = []
    _stub(mod, c, writes)
    res = mod.file_or_update(signal, issue or {"title": "replayed recurrence", "body": "", "labels": []}, "bug")
    targets = sorted({m.group(1) + "#" + m.group(2) for _, p, _ in writes
                      for m in [re.match(r"/repos/([^/]+/[^/]+)/issues/(\d+)", p)] if m})
    for method, p, body in writes:
        if method == "POST" and re.fullmatch(r"/repos/[^/]+/[^/]+/issues", p):
            m = re.search(r"Regression of (\S+#\d+)", body.get("body", ""))
            targets.append("regression-of:" + m.group(1) if m else "new-issue")
    return res.split(":")[0], targets


def section_a(base, fix, c, rows, gi, fails):
    reused, same, other = [], 0, 0
    for r in rows:
        src = r["fingerprint"].split(":")[0]
        if src not in ("glitchtip", "grafana"):
            continue
        issue = gi.get(r["fingerprint"].split(":", 1)[1]) if src == "glitchtip" else None
        if src == "glitchtip" and not issue:
            continue                     # no GlitchTip issue holds this id: nothing to recur
        start = issue["firstSeen"] if issue else NOW.isoformat()   # Grafana: a later firing
        sig = {"fingerprint": r["fingerprint"], "occurrence_id": f"{r['fingerprint']}@{start}",
               "source": src, "alertname": "replayed recurrence", "startsAt": start,
               "labels": {}, "summary": ""}
        key = f"{r['repo']}#{r['issue']}"
        b, f = _outcome(base, c, sig), _outcome(fix, c, sig)
        is_reused = bool(issue) and _ts(issue["firstSeen"]) > _ts(r["filed_at"])
        if is_reused:
            reused.append(f"    {r['fingerprint']:<28} {key:<30} baseline {b[0]:<10} {','.join(b[1]):<44} -> fix {f[0]} {','.join(f[1])}")
            if not ({key, "regression-of:" + key} & set(b[1])):
                fails.append(f"A {r['fingerprint']}: baseline did not act on {key} — replay not faithful ({b})")
            if {key, "regression-of:" + key} & set(f[1]):
                fails.append(f"A {r['fingerprint']}: fix still acts on the old issue {key} ({f})")
        else:
            other += 1
            same += b == f
            if b != f:
                fails.append(f"A {r['fingerprint']} ({src}, not reused) changed: {b} -> {f}")
    print(f"A  short-id reuse, filing path: {len(reused)} reused rows; other rows unchanged {same}/{other}")
    print("\n".join(reused))
    return len(reused)


def _sync_gh(c):
    out = {}
    for k, s in c["states"].items():
        repo, n = k.rsplit("#", 1)
        reason = {"completed": "COMPLETED", "not_planned": "NOT_PLANNED", "duplicate": "DUPLICATE"}.get(s["reason"], "")
        d = c["duplicate_of"].get(k)
        out[(repo, int(n))] = {"state": s["state"].upper(), "reason": reason, "url": f"https://github.com/{k}",
                               "dup": (d.split("#")[0], int(d.split("#")[1])) if d else None}
    return out


def section_b(sync_base, sync_fix, c, rows, gi, fails):
    grows = [r for r in rows if r["fingerprint"].startswith("glitchtip:")]
    gh = _sync_gh(c)
    api = {k: dict(i, project={"slug": i["project"]}) for k, i in gi.items()}   # API shape
    pb, pf = sync_base.plan(grows, api, gh), sync_fix.plan(grows, api, gh)
    reused = {r["fingerprint"][10:] for r in grows
              if r["fingerprint"][10:] in gi and _ts(gi[r["fingerprint"][10:]]["firstSeen"]) > _ts(r["filed_at"])}
    # faithful: at 07:52 ORRERY-DEV-1 was unresolved, and the live sync resolved it
    before = dict(api, **{"ORRERY-DEV-1": dict(api["ORRERY-DEV-1"], status="unresolved")})
    dev1 = [a for a in sync_base.plan(grows, before, gh) if a["sid"] == "ORRERY-DEV-1"]
    if not dev1 or dev1[0]["action"] != "resolve":
        fails.append(f"B baseline does not resolve ORRERY-DEV-1 as the live sync did: {dev1}")
    if [a for a in sync_fix.plan(grows, before, gh) if a["sid"] == "ORRERY-DEV-1"][0]["action"] != "skip":
        fails.append("B fix still acts on ORRERY-DEV-1 in its 07:52 state")
    changed = 0
    for a, b in zip(pb, pf):
        if a == b:
            continue
        changed += 1
        if a["sid"] in reused:
            if b["action"] != "skip":
                fails.append(f"B reused {a['sid']}: fix plans {b['action']}")
        elif a.get("target_sid") not in reused:
            fails.append(f"B {a['sid']} (not reused) changed: {a['action']} -> {b['action']}")
    print(f"\nB  sync plan: {len(grows)} rows; {len(reused)} reused; changed {changed} "
          f"(baseline ORRERY-DEV-1: {dev1[0]['action'] if dev1 else '-'})")
    for a, b in zip(pb, pf):
        if a != b:
            print(f"    {a['sid']:<28} {a.get('gh', ''):<30} baseline {a['action']:<8} -> fix {b['action']} {b.get('why', '')}")


def section_c(base, fix, c, rows, gi, fails):
    roll = [r for r in rows if r["group_key"].startswith("low-signal:")]
    fatal, n = [], 0
    for r in roll:
        i = gi.get(r["fingerprint"][10:])
        if not i or _ts(i["firstSeen"]) > _ts(r["filed_at"]):
            continue                    # issue gone or id reused: its level is not this row's
        n += 1
        sig = {"fingerprint": r["fingerprint"], "source": "glitchtip", "raw": {},
               "labels": {"project": i["project"], "level": i["level"], "count": "1", "culprit": ""}}
        lb, lf = base.low_signal(sig), fix.low_signal(sig)
        if not lb:
            fails.append(f"C baseline says {r['fingerprint']} is not low-signal — replay not faithful")
        if lf != (i["level"] != "fatal"):
            fails.append(f"C {r['fingerprint']} level {i['level']}: fix low_signal={lf}")
        if i["level"] == "fatal":
            fatal.append(f"    {r['fingerprint']:<20} {i['title'][:70]}")
    want = {"glitchtip:PLAYER-I", "glitchtip:PLAYER-L", "glitchtip:PLAYER-1I"}
    got = {x.split()[0] for x in fatal}
    if got != want:
        fails.append(f"C fatal rollup rows {sorted(got)} != {sorted(want)}")
    i = gi["PLAYER-1I"]
    sig = {"fingerprint": "glitchtip:PLAYER-1I", "occurrence_id": "glitchtip:PLAYER-1I@x", "source": "glitchtip",
           "alertname": i["title"], "startsAt": i["firstSeen"], "raw": {},
           "labels": {"project": "player", "level": "fatal", "count": "1", "culprit": ""}, "summary": ""}
    b, f = _outcome(base, c, sig), _outcome(fix, c, sig)
    if f[0] != "FILED" or "new-issue" not in f[1]:
        fails.append(f"C PLAYER-1I: fix should file its own issue, got {f}")
    print(f"\nC  rollup: {len(roll)} rows, {n} with their own GlitchTip issue; fatal (now their own issue): {len(fatal)}")
    print("\n".join(fatal))
    print(f"    PLAYER-1I through file_or_update: baseline {b[0]} {b[1]} -> fix {f[0]} {f[1]}")


def _project(sid, gi, slugs):
    if sid in gi:
        return gi[sid]["project"]
    pre = sid.rsplit("-", 1)[0].lower()
    return pre if pre in slugs else ""


def _sim(mod, c, rows, gi, slugs, use_new):
    """Replay every issue-opening ledger row in filing order through the storm-group
    decision as filing.ledger_lookup makes it: the NEWEST earlier ledger row whose group
    key (from the code under test) matches, its issue followed through duplicateOf, then
    open -> fold; closed < 7 d -> reopen (fold); closed older -> regression = new issue."""
    def gk_of(r):
        # ledger_lookup matches the group key STORED on a row; rows filed before the
        # rules last changed stored the key of their day, so they keep it
        if r["filed_at"] < GROUP_RULES_SINCE:
            g = r.get("group_key", "")
            return "" if g.startswith(mod.ROLLUP_PREFIX) else g
        key = f"{r['repo']}#{r['issue']}"
        sid = r["fingerprint"].split(":", 1)[1] if r["fingerprint"].startswith("glitchtip:") else ""
        title = (c["states"].get(key) or {}).get("title", "")
        alert = c["alertname"].get(r["fingerprint"], "")
        if use_new:
            return mod.group_key_for(alert, title, _project(sid, gi, slugs) if sid else "")
        return mod.group_key_for(alert, title)
    seq = sorted(rows, key=lambda r: r["filed_at"])
    keys = [gk_of(r) for r in seq]
    first = {}
    for idx, r in enumerate(seq):
        first.setdefault(f"{r['repo']}#{r['issue']}", idx)
    out = {}
    for key, idx in first.items():
        gk, at = keys[idx], _ts(seq[idx]["filed_at"])
        verdict = "FILE"
        if (c["states"].get(key) or {}).get("regression_of"):
            out[key] = verdict    # opened via its own fingerprint row (checked before groups)
            continue
        prev = [k for k in range(idx) if gk and keys[k] == gk]
        if prev:
            x = seq[prev[-1]]
            tgt = _chain_end(f"{x['repo']}#{x['issue']}", c["duplicate_of"])
            s = c["states"].get(tgt, {})
            created, closed = _ts(s.get("created_at", "")), _ts(s.get("closed_at", ""))
            if created and created > at:
                closed = None                    # target is the future: treat as unseen
            open_then = (not created or created <= at) and (not closed or closed > at)
            if tgt != key and (open_then or (closed and at - closed < timedelta(days=7))):
                verdict = tgt
        out[key] = verdict
    return out


def _chain_end(key, dups):
    hops = 0
    while dups.get(key) and hops < 3:
        key, hops = dups[key], hops + 1
    return key


def section_d(base, fix, c, rows, gi, fails):
    slugs = {i["project"] for i in c["glitchtip_issues"]}
    rows = [r for r in rows if r["fingerprint"].startswith(("glitchtip:", "grafana:"))]
    sb, sf = _sim(base, c, rows, gi, slugs, False), _sim(fix, c, rows, gi, slugs, True)
    folded_b = {k: v for k, v in sb.items() if v != "FILE"}
    # faithful: since the group rules last changed (f9a6b14, 2026-08-19), every issue the
    # ledger shows opened must also open in the baseline sim
    opened_at = {}
    for r in rows:
        opened_at.setdefault(f"{r['repo']}#{r['issue']}", r["filed_at"])
        opened_at[f"{r['repo']}#{r['issue']}"] = min(opened_at[f"{r['repo']}#{r['issue']}"], r["filed_at"])
    hist_bad = [k for k in folded_b if opened_at.get(k, "") >= GROUP_RULES_SINCE]
    if hist_bad:
        fails.append(f"D baseline folds issues that history opened: {hist_bad[:5]} — replay not faithful")
    moved = {k: v for k, v in sf.items() if v != "FILE" and sb.get(k) == "FILE"}
    reverted = [k for k, v in sb.items() if v != "FILE" and sf.get(k) != v]
    for k in reverted:
        fails.append(f"D {k}: baseline folded onto {sb[k]}, fix does not ({sf.get(k)})")
    lines = []
    for k, tgt in sorted(moved.items()):
        why = ("expected" if EXPECTED_FOLDS.get(k) == tgt else
               "operator duplicateOf" if _chain_end(k, c["duplicate_of"]) == tgt else "UNEXPECTED")
        if why == "UNEXPECTED":
            fails.append(f"D {k} folds onto {tgt} with no expectation or duplicate link")
        lines.append(f"    {k:<30} -> {tgt:<30} {why:<20} {(c['states'].get(k) or {}).get('title', '')[:60]}")
    for k, tgt in EXPECTED_FOLDS.items():
        if moved.get(k) != tgt:
            fails.append(f"D expected {k} -> {tgt}, fix gives {sf.get(k)}")
    print(f"\nD  storm fold: {len(sb)} issue-opening rows; baseline folds {len(folded_b)}; fix folds {len(moved)} more")
    print("\n".join(lines))


def main():
    c = json.load(open(CORPUS))
    gi = {i["shortId"]: i for i in c["glitchtip_issues"]}
    base, fix = _baseline("filing.py", "filing_baseline"), _load(os.path.join(HERE, "filing.py"), "filing_fix")
    rows = base._ledger_rows()
    fails = []
    n_reused = section_a(base, fix, c, rows, gi, fails)
    if n_reused < 7:
        fails.append(f"A expected >= 7 reused rows in the corpus, found {n_reused}")
    sync_base = _baseline("glitchtip_sync.py", "sync_baseline")
    sync_fix = _load(os.path.join(HERE, "glitchtip_sync.py"), "sync_fix")
    section_b(sync_base, sync_fix, c, rows, gi, fails)
    section_c(base, fix, c, rows, gi, fails)
    section_d(base, fix, c, rows, gi, fails)
    shutil.rmtree(_TMP, ignore_errors=True)
    print("\n" + ("PASS" if not fails else "FAIL:\n  " + "\n  ".join(fails[:25])))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
