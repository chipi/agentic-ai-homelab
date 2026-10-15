"""Mirror the operator's GitHub decisions onto the GlitchTip issues the fleet filed (#100).

GitHub is where the operator acks a filed signal (close as fixed / not planned / duplicate);
GlitchTip never heard about it, so those issues stayed "unresolved" (2026-10-15: of 363
GitHub issues filed from GlitchTip, 312 were closed). This pass reads, per GlitchTip
fingerprint in the filed ledger, its GitHub issue and mirrors it:

  closed as duplicate of #M  -> follow #M: merge into #M's GlitchTip issue when it is the
                                SAME error (same project, same fleet skeleton), then take #M's
                                state; otherwise resolve if #M is closed, keep open if not
  closed as fixed            -> resolve in next release (a later recurrence is a regression)
  closed not planned         -> resolve (operator 2026-10-15: resolve, not ignore)
  open / reopened            -> status untouched

Every mapped GlitchTip issue gets one "Tracked in GitHub: <url>" comment. The fleet never
closes a GitHub issue (fleet-architecture invariant 6); it only copies the operator's call.
A resolved issue that recurs is reopened by GlitchTip, re-triaged by the fleet, and the
filing path reopens (<7 d) or re-files on GitHub, so nothing is lost.

    python3 glitchtip_sync.py            # dry run: counts + samples, no writes
    python3 glitchtip_sync.py --apply    # mirror

Needs GLITCHTIP_WRITE_TOKEN (event:write) and GITHUB_TOKEN. Idempotent: an issue already in
the target state is skipped, the comment is posted once.
"""
import argparse
import collections
import json
import os
import urllib.parse
import urllib.request

import config
import filing

MARKER = "Tracked in GitHub:"
ORG = "homelab"


def _gt(method, path, body=None, token=None):
    req = urllib.request.Request(
        f"{config.GLITCHTIP_URL}/api/0{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token or config.GLITCHTIP_WRITE_TOKEN}",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        return (json.loads(raw) if raw else None), r.headers


def glitchtip_issues():
    """{shortId: issue} for every issue in the org, any status."""
    out, cursor = {}, ""
    while True:
        q = urllib.parse.urlencode({"query": "", "limit": 100})
        page, headers = _gt("GET", f"/organizations/{ORG}/issues/?{q}{cursor}")
        for i in page or []:
            out[i.get("shortId")] = i
        nxt = [p for p in (headers.get("Link") or "").split(",") if 'rel="next"' in p and 'results="true"' in p]
        if not nxt:
            return out
        cursor = "&cursor=" + urllib.parse.quote(nxt[0].split("cursor=")[1].split(">")[0].split("&")[0])


def github_states(pairs):
    """{(repo, number): {state, reason, dup: (repo, number) | None, url}} via batched GraphQL."""
    by_repo = collections.defaultdict(set)
    for repo, n in pairs:
        by_repo[repo].add(int(n))
    out = {}
    for repo, nums in by_repo.items():
        owner, name = repo.split("/", 1)
        nums = sorted(nums)
        for k in range(0, len(nums), 40):
            fields = " ".join(
                f"i{n}:issue(number:{n}){{state stateReason url timelineItems(itemTypes:[CLOSED_EVENT],last:1)"
                f"{{nodes{{... on ClosedEvent{{duplicateOf{{... on Issue{{number repository{{nameWithOwner}}}}}}}}}}}}}}"
                for n in nums[k:k + 40])
            d = filing._gh("POST", "/graphql", {"query": f'query{{repository(owner:"{owner}",name:"{name}"){{{fields}}}}}'})
            for key, v in (((d.get("data") or {}).get("repository")) or {}).items():
                if not v:
                    continue
                nodes = (v.get("timelineItems") or {}).get("nodes") or []
                dup = (nodes[-1].get("duplicateOf") if nodes else None) or {}
                out[(repo, int(key[1:]))] = {
                    "state": v["state"], "reason": v.get("stateReason") or "", "url": v.get("url", ""),
                    "dup": (dup["repository"]["nameWithOwner"], dup["number"]) if dup.get("number") else None}
    return out


def plan(rows, issues, gh):
    """Decide one action per mapped GlitchTip issue. Pure: no I/O (tested)."""
    by_gh = collections.defaultdict(list)       # (repo, n) -> [shortId] (to find a duplicate's target)
    for r in rows:
        by_gh[(r["repo"], int(r["issue"]))].append(r["fingerprint"].split(":", 1)[1])
    actions = []
    for r in rows:
        sid = r["fingerprint"].split(":", 1)[1]
        issue = issues.get(sid)
        key = (r["repo"], int(r["issue"]))
        st = gh.get(key)
        if not issue or not st:
            actions.append({"sid": sid, "action": "skip", "why": "not in GlitchTip" if not issue else "no GitHub state"})
            continue
        base = {"sid": sid, "id": issue["id"], "project": (issue.get("project") or {}).get("slug"),
                "status": issue.get("status"), "gh": f"{r['repo']}#{r['issue']}", "url": st["url"]}
        if st["state"] == "OPEN":
            actions.append({**base, "action": "note"})
            continue
        if st["reason"] == "DUPLICATE" and st["dup"]:
            # The canonical GitHub issue is the bug's real record: follow ITS state. Merge in
            # GlitchTip only when both are the same error (the fleet's own skeleton): an
            # umbrella issue can hold several different errors, and merging those would
            # destroy them (2026-10-15 dry run: orrery #557 held a SyntaxError, a TypeError
            # and a CSS-preload error).
            canon = st["dup"]
            canon_st = gh.get((canon[0], int(canon[1])))
            canon_url = f"https://github.com/{canon[0]}/issues/{canon[1]}"
            target = next((issues[s] for s in by_gh.get((canon[0], int(canon[1])), [])
                           if s in issues and s != sid
                           and (issues[s].get("project") or {}).get("slug") == base["project"]
                           and filing._alert_skeleton(issues[s].get("title", ""))
                           == filing._alert_skeleton(issue.get("title", ""))), None)
            closed = bool(canon_st) and canon_st["state"] == "CLOSED"
            release = closed and canon_st["reason"] == "COMPLETED"
            if target:
                actions.append({**base, "action": "merge", "target": target["id"],
                                "target_sid": target.get("shortId"), "canon": canon_url,
                                "then_resolve": closed, "release": release})
            elif closed and base["status"] != "resolved":
                actions.append({**base, "action": "resolve", "release": release, "canon": canon_url})
            else:
                actions.append({**base, "action": "note", "canon": canon_url})
            continue
        if base["status"] == "resolved":
            actions.append({**base, "action": "note"})    # already resolved; just the comment
            continue
        actions.append({**base, "action": "resolve", "release": st["reason"] == "COMPLETED"})
    return actions


def _has_marker(issue_id):
    comments, _ = _gt("GET", f"/issues/{issue_id}/comments/")
    return any(MARKER in ((c.get("data") or {}).get("text") or "") for c in comments or [])


def _comment(a):
    text = f"{MARKER} {a['url']} (signal-fleet)"
    if a.get("canon"):
        text += f"; closed there as a duplicate of {a['canon']}"
    _gt("POST", f"/issues/{a['id']}/comments/", {"data": {"text": text}})


def _resolve(issue_id, release):
    body = {"status": "resolved"}
    if release:
        body["statusDetails"] = {"inNextRelease": True}
    _gt("PUT", f"/issues/{issue_id}/", body)


def apply(actions):
    done = collections.Counter()
    for a in actions:
        if a["action"] in ("skip", "merge"):    # merges: commented on the survivor below
            continue
        try:
            if not _has_marker(a["id"]):
                _comment(a)
                done["commented"] += 1
            if a["action"] == "resolve":
                _resolve(a["id"], a.get("release"))
                done["resolved"] += 1
        except Exception as ex:  # noqa: BLE001 — one bad issue must not stop the pass
            done["errors"] += 1
            print(f"  sync {a['sid']} {a['action']} failed: {ex}")
    # Merges per target, in ONE call each: GlitchTip keeps the most recent (highest id) issue
    # of the set, so merging pair by pair could soft-delete the target before the next pair.
    groups = collections.defaultdict(list)
    for a in actions:
        if a["action"] == "merge":
            groups[a["target"]].append(a)
    for target, members in groups.items():
        ids = [int(target)] + [int(m["id"]) for m in members]
        try:
            q = urllib.parse.urlencode([("id", i) for i in ids])
            _gt("PUT", f"/organizations/{ORG}/issues/?{q}", {"merge": 1})
            done["merged"] += len(members)
            survivor = max(ids)
            if not _has_marker(survivor):
                _comment({**members[0], "id": survivor})
                done["commented"] += 1
            if members[0].get("then_resolve"):
                _resolve(survivor, members[0].get("release"))
                done["resolved"] += 1
        except Exception as ex:  # noqa: BLE001
            done["errors"] += 1
            print(f"  sync merge into {target} failed: {ex}")
    return done


def run(do_apply=False, samples=3):
    rows = [r for r in filing._ledger_rows() if r.get("fingerprint", "").startswith("glitchtip:")]
    issues = glitchtip_issues()
    gh = github_states({(r["repo"], r["issue"]) for r in rows})
    canon = {st["dup"] for st in gh.values() if st.get("dup")}
    missing = {(rp, n) for rp, n in canon if (rp, int(n)) not in gh}
    if missing:
        gh.update(github_states(missing))
    actions = plan(rows, issues, gh)
    counts = collections.Counter(a["action"] for a in actions)
    print(f"glitchtip-sync: {len(rows)} mapped GlitchTip issues -> {dict(counts)}")
    for kind in ("merge", "resolve", "note", "skip"):
        for a in [x for x in actions if x["action"] == kind][:samples]:
            extra = f" -> {a.get('target_sid')}" if kind == "merge" else (" (in next release)" if a.get("release") else "")
            print(f"  {kind:8} {a['sid']:28} {a.get('gh', '')}{extra} {a.get('why', '')}")
    if not do_apply:
        print("DRY RUN (pass --apply)")
        return counts
    done = apply(actions)
    print(f"glitchtip-sync applied: {dict(done)}")
    return done


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--samples", type=int, default=3)
    a = ap.parse_args()
    run(do_apply=a.apply, samples=a.samples)
