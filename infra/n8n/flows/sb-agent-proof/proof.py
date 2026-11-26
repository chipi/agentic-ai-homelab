#!/usr/bin/env python3
"""The checks of the second brain agent's proof (run.sh sets the environment up and calls this).

The path under test is the real one: the stub Slack's Socket Mode server sends envelopes -> sb-bridge/bridge.js (in n8n's image) acks and
forwards a signed POST -> n8n's published workflow `second brain: Slack mention -> answer in thread` (webhook, agent, MCP tools, citation
check, chat.postMessage to the stub). The witnesses are independent of the workflow's own verdict: the stub Slack's log (every post, every
conversations.replies call, every envelope sent and ack received), the real second-brain server's own request log, the bridge's log lines,
and the outcome records the workflow keeps in its static data (read from Postgres: ids, verdict, tools called, no text).
Prints PASS/FAIL per check and `N of M PASS`, exits 1 on any FAIL. Never prints a secret."""
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

E = os.environ
SLACK, DOCS, TASKS, N8N, BRIDGE, WSST = E["SLACK_URL"], E["DOCS_URL"], E["TASKS_URL"], E["N8N_URL"], E["BRIDGE_URL"], E["SLACK_URL"]
CTX = E["DEV_CONTEXT"]
SECRET = E["PROOF_BRIDGE_SECRET"]
APP_TOKEN = E["PROOF_APP_TOKEN"]
CHANNEL, BOT, USER = "C0PROOFASK1", "U0BOT00001", "U0PROOFUSR1"
LABEL = "[second brain] "
NOT_FOUND = LABEL + "I could not find a sourced answer."
FAILED = LABEL + "I hit an error answering this; try again later."
FIXTURE_IDS = {"arxiv:2001.00001", "arxiv:2002.00002", "ntrs:20000000001", "doi:10.1000/Fixture.2"}
RESULTS, LATENCY = [], []
HOOK = N8N + "/webhook/second-brain-mention"
_seq = [0]


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  <- " + str(detail)[:700]), flush=True)


def req(url, doc=None):
    r = urllib.request.Request(url, data=None if doc is None else json.dumps(doc).encode(), method="GET" if doc is None else "POST")
    with urllib.request.urlopen(r, timeout=30) as f:
        return json.loads(f.read() or b"null")


def slack_log():
    return req(SLACK + "/__log")


def posts():
    return [c for c in slack_log() if c["call"] == "post"]


def replies_in(thread_ts):
    return [p["body"] for p in posts() if p["body"]["thread_ts"] == thread_ts]


def sh(*a):
    return subprocess.run(list(a), capture_output=True, text=True).stdout


def docker(*a):
    return sh("docker", "--context", CTX, *a)


def outcomes():
    raw = docker("exec", "n8n-db", "psql", "-U", "n8n", "-d", "n8n", "-tAc", "select \"staticData\"::text from workflow_entity where id='sbaskrun0000001'").strip()
    try:
        return (json.loads(raw) or {}).get("global", {}).get("outcomes", []) if raw else []
    except ValueError:
        return []


def wait(pred, timeout=240, step=1.0):
    t = time.time()
    while time.time() - t < timeout:
        v = pred()
        if v:
            return v
        time.sleep(step)
    return None


def lib_calls():
    out = docker("logs", "n8n-proof-library")
    n = 0
    for line in out.splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("method") == "POST" and d.get("tool") in ("search", "read", "paper"):
            n += 1
    return n


def next_ts():
    _seq[0] += 1
    return "%d.%06d" % (1800000000 + _seq[0], 100 + _seq[0])


def mention(text, thread_ts=None, ts=None, event_id=None, retry=0, extra=None, user=None, channel=None):
    """Inject an app_mention through the stub's Socket Mode server. Returns (ts, event_id, injected at)."""
    ts = ts or next_ts()
    event_id = event_id or "Ev%s" % ts.replace(".", "")
    ev = {"type": "app_mention", "user": user or USER, "channel": channel or CHANNEL, "ts": ts, "text": "<@%s> %s" % (BOT, text)}
    if thread_ts:
        ev["thread_ts"] = thread_ts
    ev.update(extra or {})
    t = time.time()
    r = req(SLACK + "/__event", {"event": ev, "event_id": event_id, "retry_attempt": retry})
    assert r["ok"], "the stub has no open Socket Mode connection"
    return ts, event_id, t


def ask(text, thread_ts=None, timeout=300, ts=None, user=None, channel=None, extra=None, canned=False):
    """A mention, then wait for its one reply and its outcome record. Returns (ts, reply body or None, outcome or None, seconds)."""
    ts, eid, t0 = mention(text, thread_ts, ts=ts, user=user, channel=channel, extra=extra)
    root = thread_ts or ts
    got = wait(lambda: replies_in(root) if any(p["body"]["thread_ts"] == root for p in posts()) else None, timeout)
    dt = time.time() - t0
    oc = None if canned else wait(lambda: next((o for o in outcomes() if o["event_id"] == eid), None), 30)
    if oc:
        LATENCY.append((text[:48], dt, oc["latencyMs"] / 1000.0))
    return ts, (got[-1] if got else None), oc, dt


def sources(text):
    return [l.split("|")[0].split("]", 1)[1].strip() for l in text.splitlines() if re.match(r"^\[\d+\]\s", l)]


def hook_call(body, ts=None, sig=None, headers=True):
    raw = json.dumps(body).encode()
    ts = ts or str(int(time.time()))
    sig = sig or "sha256=" + hmac.new(SECRET.encode(), ts.encode() + b"." + raw, hashlib.sha256).hexdigest()
    h = {"Content-Type": "application/json"}
    if headers:
        h.update({"X-SB-Timestamp": ts, "X-SB-Signature": sig})
    r = urllib.request.Request(HOOK, data=raw, headers=h, method="POST")
    t = time.time()
    try:
        with urllib.request.urlopen(r, timeout=60) as f:
            return f.status, time.time() - t
    except urllib.error.HTTPError as e:
        return e.code, time.time() - t


def bridge_lines():
    out = docker("logs", "n8n-proof-bridge")
    ls = []
    for line in out.splitlines():
        try:
            ls.append(json.loads(line))
        except ValueError:
            pass
    return ls


# ============================================================ the compose files: litellm_clients is created by hand as an internal network ============================================================
def net_block(path, name):
    t = open(path).read()
    i = t.rfind("\nnetworks:\n")
    m = re.search(r"\n  %s:\n((?:    .*\n|\n)*)" % name, t[i:] if i >= 0 else t)
    return m.group(1) if m else ""


INFRA = os.path.dirname(os.path.dirname(E["SB_BRIDGE_DIR"]))
nb_l = net_block(INFRA + "/litellm/docker-compose.yml", "litellm_clients")
nb_n = net_block(INFRA + "/n8n/docker-compose.yml", "litellm_clients")
readme = open(INFRA + "/n8n/README.md").read()
check("compose: litellm_clients is external in both stacks (so LiteLLM is not recreated for it) and the README creates it with `docker network create --internal`, connects the live gateway, and the rollback removes it",
      "external: true" in nb_l and "name: litellm_clients" in nb_l and "external: true" in nb_n and "docker network create --internal litellm_clients" in readme
      and "docker network connect litellm_clients litellm" in readme and "docker network disconnect litellm_clients litellm" in readme, (nb_l, nb_n))
check("compose: the sb-bridge compose header no longer says *.slack.com", "*.slack.com" not in open(E["SB_BRIDGE_DIR"] + "/docker-compose.yml").read().replace("not *.slack.com", ""), "")

# ============================================================ the bridge and its socket ============================================================
st = req(SLACK + "/__state")
check("bridge: it opened a Socket Mode connection with the app-level token and got hello (healthz 200, the stub has one connection)",
      st["connected"] and st["opened"] >= 1 and any(c["call"] == "open" and c["auth"] for c in slack_log())
      and urllib.request.urlopen(BRIDGE + "/healthz", timeout=5).status == 200, (st, bridge_lines()[:4]))

# ============================================================ a mention the library can answer ============================================================
n0 = lib_calls()
T1, r1, o1, dt = ask("Which paper in the library covers frontier exploration with learned occupancy maps, and what does it show?")
check("library mention: exactly one reply, in the mention's own thread (thread_ts = its ts), labelled [second brain]",
      r1 is not None and len(replies_in(T1)) == 1 and r1["text"].startswith(LABEL) and r1["channel"] == CHANNEL, (replies_in(T1), o1))
if r1 and o1:
    ids = set(sources(r1["text"]))
    check("library mention: it cites a fixture paper id, and a library tool call returned it in that execution (verdict ok, tools called, the real server's log shows calls)",
          bool(ids) and ids <= FIXTURE_IDS and o1["verdict"] == "ok" and any(t.startswith("library_") for t in o1["tools"]) and lib_calls() > n0, (ids, o1))
    check("library mention: unfurls off, under 1500 characters, no broadcast", r1["unfurl_links"] is False and r1["unfurl_media"] is False and len(r1["text"]) <= 1500 + len(LABEL) and "<!" not in r1["text"], r1)
L1 = [l for l in bridge_lines() if l.get("msg") == "mention" and l.get("ts") == T1]
check("bridge: one log line for that mention (channel, ts, forwarded 200), and nothing of its text", len(L1) == 1 and L1[0]["forwarded"] == 200 and L1[0]["channel"] == CHANNEL, L1)

# ============================================================ a mention inside a thread gets the thread as context ============================================================
ROOT = next_ts()
MENTION_TS = next_ts()
req(SLACK + "/__set", {"threads": {ROOT: [
    {"ts": ROOT, "user": "U0OTHER0001", "text": "I am reading about the universal variable solution of the two-body boundary problem today."},
    {"ts": next_ts(), "bot_id": "B0BOT0001", "text": "[second brain] noted."},
    {"ts": MENTION_TS, "user": USER, "text": "<@%s> which paper in the library is that about?" % BOT}]}})
nrep = len([c for c in slack_log() if c["call"] == "replies"])
T2, r2, o2, dt = ask("which paper in the library is that about?", thread_ts=ROOT, ts=MENTION_TS)
rc = [c for c in slack_log() if c["call"] == "replies"][nrep:]
check("thread mention: the thread was fetched (conversations.replies with the thread's root ts, the bot's token)", len(rc) >= 1 and rc[0]["ts"] == ROOT and rc[0]["channel"] == CHANNEL and rc[0]["auth"], rc)
check("thread mention: the reply is in that thread, once, and the agent had the earlier messages as context (ctxMessages 2: the root and the bot's note, not the mention itself)",
      r2 is not None and len(replies_in(ROOT)) == 1 and o2 is not None and o2["ctxMessages"] == 2 and not o2["ctxNote"], (replies_in(ROOT), o2))
check("thread mention: the question is answerable only from the thread (the root names the topic): it cites the NTRS fixture, which a library tool returned",
      r2 is not None and o2 is not None and "ntrs:20000000001" in sources(r2["text"]) and o2["verdict"] == "ok", (r2, o2))

# ============================================================ docs, tasks, nothing ============================================================
T3, r3, o3, dt = ask("What did we decide about Borealis support pricing?")
refs = sources(r3["text"]) if r3 else []
check("docs mention: one reply citing the Borealis doc (link or id) that a docs tool returned (verdict ok)",
      r3 is not None and bool(refs) and any(("borealis-pricing-decision" in x or "1BorealisPricing0002" in x or "Borealis vendor pricing decision" in x) for x in refs)
      and o3 is not None and o3["verdict"] == "ok" and any(t.startswith("docs_") for t in o3["tools"]) and any(c["tool"] == "search" for c in req(DOCS + "/__log")), (r3, o3))
T4, r4, o4, dt = ask("Which follow-up tasks are open?")
check("tasks mention: one reply citing a task the tasks tool returned (verdict ok)",
      r4 is not None and bool(sources(r4["text"])) and o4 is not None and o4["verdict"] == "ok" and "tasks_list" in o4["tools"], (r4, o4))
T5, r5, o5, dt = ask("Who won the 1998 football world cup final and by what score?")
check("unanswerable mention: one reply, the not-found message, no citation",
      r5 is not None and len(replies_in(T5)) == 1 and r5["text"] == NOT_FOUND and "[1]" not in r5["text"], (r5, o5))

# ============================================================ what is ignored, and Slack's retry ============================================================
n = len(posts())
sent0 = len([c for c in slack_log() if c["call"] == "sent"])
req(SLACK + "/__event", {"event": {"type": "message", "user": USER, "channel": CHANNEL, "ts": next_ts(), "text": "just chatting, no mention"}, "event_id": "EvPlainMessage1"})
req(SLACK + "/__event", {"event": {"type": "app_mention", "bot_id": "B0OTHERBOT", "channel": CHANNEL, "ts": next_ts(), "text": "<@%s> a bot mentioning" % BOT}, "event_id": "EvBotMention001"})
req(SLACK + "/__event", {"event": {"type": "app_mention", "subtype": "message_changed", "user": USER, "channel": CHANNEL, "ts": next_ts(), "text": "<@%s> an edit" % BOT}, "event_id": "EvEditMention001"})
time.sleep(6)
ig = [l for l in bridge_lines() if l.get("msg") == "ignored"]
check("a plain message event, a bot's mention and an edit are ignored: acked, not forwarded, no reply", len(posts()) == n and len(ig) >= 3, (len(posts()) - n, ig))

n = len(posts())
RT = next_ts()
eid = "EvRetry%s" % RT.replace(".", "")
mention("PROOF-FORCE-ANSWER: Occupancy maps shorten paths [1].\n\nSources:\n[1] arxiv:9999.99999 | nothing returned this", ts=RT, event_id=eid)
mention("PROOF-FORCE-ANSWER: Occupancy maps shorten paths [1].\n\nSources:\n[1] arxiv:9999.99999 | nothing returned this", ts=RT, event_id=eid, retry=1)
wait(lambda: len(replies_in(RT)) >= 1, 240)
time.sleep(8)
check("Slack's retry (the same event_id twice): the bridge forwards once and the thread gets one reply",
      len(replies_in(RT)) == 1 and len([l for l in bridge_lines() if l.get("msg") == "duplicate" and l.get("event_id") == eid]) == 1
      and len([l for l in bridge_lines() if l.get("msg") == "mention" and l.get("event_id") == eid]) == 1, (replies_in(RT), [l for l in bridge_lines() if l.get("event_id") == eid]))
check("... the forced answer citing an id no tool returned is replaced by the not-found message, and the execution's record says unsourced and names the id",
      len(replies_in(RT)) == 1 and replies_in(RT)[0]["text"] == NOT_FOUND
      and any(o["event_id"] == eid and o["verdict"] == "unsourced" and "arxiv:9999.99999" in o["reason"] for o in outcomes()), (replies_in(RT), [o for o in outcomes() if o["event_id"] == eid]))

# ============================================================ the webhook itself: signature, window, once, at once ============================================================
body = {"channel": CHANNEL, "ts": next_ts(), "thread_ts": None, "user": USER, "bot": BOT, "event_id": "EvDirect000001",
        "text": "<@%s> PROOF-FORCE-ANSWER: Learned maps help [1].\n\nSources:\n[1] arxiv:2001.00001 | nothing was called" % BOT}
s_bad, _ = hook_call(body, sig="sha256=" + "0" * 64)
s_none, _ = hook_call(body, headers=False)
s_old, _ = hook_call(body, ts=str(int(time.time()) - 3600))
s_wrong, _ = hook_call(body, sig="sha256=" + hmac.new(b"another secret entirely, not the bridge's", str(int(time.time())).encode() + b"." + json.dumps(body).encode(), hashlib.sha256).hexdigest())
check("webhook: a bad signature, a wrong secret, no headers and a stale timestamp are all 401, and nothing is posted",
      (s_bad, s_none, s_old, s_wrong) == (401, 401, 401, 401) and not replies_in(body["ts"]), (s_bad, s_none, s_old, s_wrong))
n = len(posts())
tstart = time.time()
s1, t1 = hook_call(body)
reply = wait(lambda: replies_in(body["ts"]), 240)
tpost = [p["t"] for p in posts() if p["body"]["thread_ts"] == body["ts"]]
s2, _ = hook_call(body)
time.sleep(8)
check("webhook: a signed call is answered 200 at once (before the reply is posted), the same event again is 200 and posts nothing more",
      s1 == 200 and s2 == 200 and bool(tpost) and tpost[0] >= tstart + t1 and len(replies_in(body["ts"])) == 1 and t1 < 5, (s1, s2, t1, len(replies_in(body["ts"]))))
check("... the forced answer's source (a real fixture id) was not returned by any tool in that execution: replaced by the not-found message",
      reply is not None and reply[-1]["text"] == NOT_FOUND, reply)
s_bad_body, _ = hook_call({"channel": "nonsense", "ts": "1.1", "user": USER, "event_id": "EvX1", "text": "x"})
check("webhook: a signed call with a malformed channel is 400", s_bad_body == 400, s_bad_body)

# ============================================================ the bridge reconnects ============================================================
st0 = req(SLACK + "/__state")
req(SLACK + "/__disconnect", {"reason": "refresh_requested"})
st1 = wait(lambda: (lambda s: s if s["opened"] > st0["opened"] and s["connected"] else None)(req(SLACK + "/__state")), 60)
check("bridge: after Slack's `disconnect` it opens a new connection by itself (and healthz is 200 again)", st1 is not None and urllib.request.urlopen(BRIDGE + "/healthz", timeout=5).status == 200, (st0, st1))
T6, r6, o6, dt = ask("Which paper covers a universal variable solution of the two-body boundary problem?")
check("bridge: the next mention after the reconnect is delivered and answered, with a source a library tool returned",
      r6 is not None and o6 is not None and o6["verdict"] == "ok" and "ntrs:20000000001" in sources(r6["text"]), (r6, o6))

# ============================================================ an MCP server down ============================================================
docker("stop", "n8n-proof-docs")
T7, r7, o7, dt = ask("What did we decide about Borealis support pricing?")
check("docs server down: the mention gets the error reply, once, and the execution says error", r7 is not None and len(replies_in(T7)) == 1 and r7["text"] == FAILED and o7 is not None and o7["verdict"] == "error", (r7, o7))
T8, r8, o8, dt = ask("Another one while it is down: which paper is about repair agents?")
check("a second mention while it is down also gets its one error reply (every tool is built before any answer)", r8 is not None and len(replies_in(T8)) == 1 and r8["text"] == FAILED, (r8, o8))
docker("start", "n8n-proof-docs")
time.sleep(3)
time.sleep(5)
check("the failed mentions are not asked again when the server is back (still one reply each)", len(replies_in(T7)) == 1 and len(replies_in(T8)) == 1, (len(replies_in(T7)), len(replies_in(T8))))
T9, r9, o9, dt = ask("Which paper is about repair agents that use tools?")
check("the next mention is answered again, with a source a library tool returned",
      r9 is not None and o9 is not None and o9["verdict"] == "ok" and bool(sources(r9["text"])) and set(sources(r9["text"])) <= FIXTURE_IDS, (r9, o9))

# ============================================================ who may ask: the allowlist (fail closed) ============================================================
REFUSED = LABEL + "I only answer for my owner here."
n0 = lib_calls()
T10, r10, o10, dt = ask("Which paper covers frontier exploration?", user="U0INTRUDER01", canned=True)
time.sleep(4)
check("allowlist: a mention from a user who is not allowed gets one short refusal in its thread, no agent run, no tool call",
      r10 is not None and len(replies_in(T10)) == 1 and r10["text"] == REFUSED and lib_calls() == n0
      and not any(o["ts"] == T10 for o in outcomes()), (replies_in(T10), lib_calls() - n0))
T11, r11, o11, dt = ask("Which paper covers frontier exploration?", channel="C0OTHERCHAN1", canned=True)
time.sleep(3)
check("allowlist: an allowed user in a channel that is not on SB_ALLOWED_CHANNELS gets the same refusal and no agent run",
      r11 is not None and len(replies_in(T11)) == 1 and r11["text"] == REFUSED and lib_calls() == n0, (replies_in(T11), lib_calls() - n0))
check("allowlist: the allowed user's mentions above were answered (the list admits them)", o1 is not None and o1["verdict"] == "ok", o1)

# ============================================================ a file, a very long message: a short reply, not silence ============================================================
T12, r12, o12, dt = ask("here is a file", extra={"subtype": "file_share"}, canned=True)
check("a mention with a file (subtype file_share) gets a short reply, once, and no agent run",
      r12 is not None and len(replies_in(T12)) == 1 and r12["text"] == LABEL + "I can't read files; please ask in text." and not any(o["ts"] == T12 for o in outcomes()), (replies_in(T12)))
T13, r13, o13, dt = ask("x" * 8100, canned=True)
check("a mention over 8000 characters gets a short reply, once, and no agent run",
      r13 is not None and len(replies_in(T13)) == 1 and r13["text"] == LABEL + "That message is too long; please ask a shorter question." and not any(o["ts"] == T13 for o in outcomes()), (replies_in(T13)))

# ============================================================ the citation check: a real reference next to an invented title, a short title ============================================================
GOOD = "arxiv:2001.00001 Frontier Exploration with Learned Occupancy Maps"
SEEN = "\nPROOF-FORCE-SEEN: " + GOOD
T14, r14, o14, dt = ask("PROOF-FORCE-ANSWER: Learned maps shorten exploration [1].\n\nSources:\n[1] arxiv:2001.00001 | Frontier Exploration with Learned Occupancy Maps" + SEEN)
check("citation check (positive control): the cited id and its verbatim title, both among what the tools returned, pass",
      r14 is not None and o14 is not None and o14["verdict"] == "ok" and r14["text"].startswith(LABEL + "Learned maps") , (r14, o14))
T15, r15, o15, dt = ask("PROOF-FORCE-ANSWER: Learned maps shorten exploration [1].\n\nSources:\n[1] arxiv:2001.00001 | An Entirely Invented Paper Title Here" + SEEN)
check("citation check: a real reference next to an invented title is replaced, and the reason names the title",
      r15 is not None and r15["text"] == NOT_FOUND and o15 is not None and o15["verdict"] == "unsourced" and "title" in o15["reason"], (r15, o15))
T16, r16, o16, dt = ask("PROOF-FORCE-ANSWER: Learned maps shorten exploration [1].\n\nSources:\n[1] ai | map" + SEEN)
check("citation check: a very short reference that is merely contained in what the tools returned does not pass",
      r16 is not None and r16["text"] == NOT_FOUND and o16 is not None and o16["verdict"] == "unsourced", (r16, o16))

# ============================================================ the same event while its first execution is still running: one answer ============================================================
body = {"channel": CHANNEL, "ts": next_ts(), "thread_ts": None, "user": USER, "bot": BOT, "event_id": "EvInflight0001",
        "text": "<@%s> Which paper in the library covers frontier exploration with learned occupancy maps, and what does it show?" % BOT}
s1, _ = hook_call(body)
time.sleep(1.0)
running = not replies_in(body["ts"])
s2, _ = hook_call(body)
wait(lambda: replies_in(body["ts"]), 240)
time.sleep(10)
check("in-flight duplicate: the same event delivered again while the first execution is still running (agent not yet done): both 200, one answer",
      s1 == 200 and s2 == 200 and running and len(replies_in(body["ts"])) == 1, (s1, s2, running, len(replies_in(body["ts"]))))

# ============================================================ n8n down while a mention arrives: the bridge keeps trying ============================================================
docker("stop", "n8n")
TB, eidb, t0 = mention("Which paper is about repair agents that use tools?")
time.sleep(12)
check("n8n down: nothing is posted yet and the mention is not given up", not replies_in(TB), replies_in(TB))
docker("start", "n8n")
got = wait(lambda: replies_in(TB), 240)
L = [l for l in bridge_lines() if l.get("msg") == "mention" and l.get("event_id") == eidb]
check("n8n back (about a minute later): the bridge's retries delivered it, once (forwarded 200 after several tries), one reply, answered",
      got is not None and len(got) == 1 and len(L) == 1 and L[0]["forwarded"] == 200 and L[0]["tries"] > 1 and got[0]["text"] != FAILED, (got, L))

# ============================================================ the connection: no hot loop, connect timeout, refresh, exit when unhealthy ============================================================
def opens():
    return [c for c in slack_log() if c["call"] == "open"]


req(SLACK + "/__set", {"mode": "close_after_hello"})
n_open = len(opens())
req(SLACK + "/__disconnect", {"reason": "warning"})
time.sleep(14)
n_loop = len(opens()) - n_open
req(SLACK + "/__set", {"mode": ""})
check("bridge: a socket that gets hello and is closed again does not loop (%d reconnects in 14 s with backoff; a loop would be hundreds)" % n_loop, 2 <= n_loop <= 7, n_loop)
back = wait(lambda: req(SLACK + "/__state")["connected"], 90)
Tr, rr, orr, dt = ask("Which paper covers a universal variable solution of the two-body boundary problem?")
check("bridge: when the closing stops it connects again by itself and the next mention is answered", bool(back) and rr is not None and orr is not None and orr["verdict"] == "ok", (back, rr, orr))

o0 = len(opens())
okr = wait(lambda: len(opens()) > o0 and req(SLACK + "/__state")["connected"], 90)
Tq, rq, oq, dt = ask("Which paper is about repair agents that use tools?")
check("bridge: without any disconnect it opens a fresh socket on its own every REFRESH_MS (25 s here; make before break) and the mention after it is answered",
      bool(okr) and rq is not None and oq is not None and oq["verdict"] == "ok", (okr, rq, oq))

# a refresh that fails (Slack refuses one apps.connections.open) is tried again, not forgotten
req(SLACK + "/__set", {"fail_opens": 1})
failed = wait(lambda: next((c for c in opens() if c.get("failed")), None), 60)
tf = failed["t"] if failed else time.time()
again = wait(lambda: next((c for c in opens() if c["t"] > tf and not c.get("failed")), None), 70)
Tf, rf, of, dt = ask("Which paper covers a universal variable solution of the two-body boundary problem?")
check("bridge: a refresh whose apps.connections.open Slack refused is tried again within the window (not left until the socket dies), and the next mention is answered",
      failed is not None and again is not None and rf is not None and of is not None and of["verdict"] == "ok", (failed, again, rf, of))

IMG = "docker.n8n.io/n8nio/n8n:2.48.7"



def run_side(name, port, token_file, extra_env):
    cmd = ["run", "-d", "--name", name, "--network", "host", "-v", E["SB_BRIDGE_DIR"] + "/bridge.js:/app/bridge.js:ro",
           "-v", token_file + ":/run/sb/slack-app.token:ro", "-v", E["PROOF_SECRETS"] + "/hook.secret:/run/sb/hook.secret:ro",
           "-e", "SLACK_APP_TOKEN_FILE=/run/sb/slack-app.token", "-e", "SB_HOOK_SECRET_FILE=/run/sb/hook.secret", "-e", "SB_HOOK_URL=" + HOOK,
           "-e", "SLACK_API_BASE=" + SLACK, "-e", "PORT=%d" % port]
    for k, v in extra_env.items():
        cmd += ["-e", "%s=%s" % (k, v)]
    docker(*(cmd + ["--entrypoint", "node", IMG, "/app/bridge.js"]))


req(SLACK + "/__set", {"mode": "no_handshake"})
o0 = len(opens())
run_side("n8n-proof-bridge3", 18087, E["PROOF_SECRETS"] + "/slack-app.token", {"CONNECT_TIMEOUT_MS": "3000"})
time.sleep(14)
b3 = docker("logs", "n8n-proof-bridge3")
req(SLACK + "/__set", {"mode": ""})
docker("rm", "-f", "n8n-proof-bridge3")
check("bridge: a socket that never opens is dropped after CONNECT_TIMEOUT_MS (3 s here) and tried again with backoff", b3.count('"connect timeout"') >= 2, b3[-400:])

bad = E["PROOF_SECRETS"] + "/bad-app.token"
with open(bad, "w") as f:
    f.write("xapp-proof-not-the-token")
os.chmod(bad, 0o644)
run_side("n8n-proof-bridge2", 18086, bad, {"UNHEALTHY_EXIT_MS": "8000"})
rc = wait(lambda: docker("inspect", "-f", "{{.State.Status}} {{.State.ExitCode}}", "n8n-proof-bridge2").strip() if docker("inspect", "-f", "{{.State.Status}}", "n8n-proof-bridge2").strip() == "exited" else None, 60)
b2 = docker("logs", "n8n-proof-bridge2")
docker("rm", "-f", "n8n-proof-bridge2")
check("bridge: with no socket for UNHEALTHY_EXIT_MS (8 s here, a refused token) the process exits 1 so the restart policy acts", rc == "exited 1" and '"unhealthy, exiting"' in b2, (rc, b2[-300:]))

# a mention whose forward budget runs out is logged as given up (channel and ts, no text)
TG_before = req(SLACK + "/__state")
run_side("n8n-proof-bridge3", 18087, E["PROOF_SECRETS"] + "/slack-app.token", {"FORWARD_BUDGET_MS": "3000", "SB_HOOK_URL": "http://127.0.0.1:1/webhook/none"})
wait(lambda: '"hello"' in docker("logs", "n8n-proof-bridge3"), 30)
TG, eidg, t0 = mention("Secret question text that must never reach a log")
time.sleep(10)
b3 = docker("logs", "n8n-proof-bridge3")
docker("rm", "-f", "n8n-proof-bridge3")
gl = [json.loads(l) for l in b3.splitlines() if l.startswith("{") and '"forward gave up"' in l]
check("bridge: a mention whose forward budget runs out is logged as `forward gave up` with its channel and ts, and no text",
      len(gl) == 1 and gl[0]["ts"] == TG and gl[0]["channel"] == CHANNEL and "Secret question" not in b3, (gl, b3[-300:]))
wait(lambda: req(SLACK + "/__state")["connected"], 60)
time.sleep(1)

# ============================================================ every envelope was acked; nothing secret in the bridge's log ============================================================
log = slack_log()
sent = [c["frame"]["envelope_id"] for c in log if c["call"] == "sent" and c["frame"].get("envelope_id")]
acked = [c["frame"].get("envelope_id") for c in log if c["call"] == "ack"]
check("every envelope the stub sent (%d, the retry, the ignored ones and the bot's included) was acked by the bridge, each once" % len(sent), len(sent) > 10 and sorted(sent) == sorted(acked), (len(sent), len(acked), set(sent) ^ set(acked)))
blog = docker("logs", "n8n-proof-bridge")
texts = ["frontier", "Borealis", "occupancy", "football", "universal variable", "PROOF-FORCE"]
check("bridge log: no token, no secret, no socket URL ticket and no message text",
      APP_TOKEN not in blog and SECRET not in blog and "ticket" not in blog and not any(t.lower() in blog.lower() for t in texts), [t for t in texts if t.lower() in blog.lower()])


# ============================================================ an empty allowlist refuses everyone (fail closed); a re-install keeps a live flow live ============================================================
def active(i):
    return docker("exec", "n8n-db", "psql", "-U", "n8n", "-d", "n8n", "-tAc", "select active from workflow_entity where id='%s'" % i).strip()


was = active("sbaskagent00001")
env = dict(E, SB_ALLOWED_USERS="", HOME=E["PROOF_HOME"])
p = subprocess.run(["bash", E["PROOF_FLOWS"] + "/install-sb-agent.sh"], env=env, capture_output=True, text=True)
check("installer: re-running it over a live mention flow leaves it active (it says so), and an empty SB_ALLOWED_USERS is warned about",
      was == "t" and active("sbaskagent00001") == "t" and "active again" in p.stdout and "refuse everyone" in p.stdout, (was, active("sbaskagent00001"), p.stdout[-400:], p.stderr[-200:]))
docker("restart", "n8n")
wait(lambda: sh("curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-m", "3", N8N + "/healthz") == "200", 120)
time.sleep(10)
n0 = lib_calls()
T20, r20, o20, dt = ask("Which paper covers frontier exploration?", canned=True)
time.sleep(3)
check("empty list: the owner's own mention is refused too (nobody is allowed), once, with no agent run and no tool call",
      r20 is not None and len(replies_in(T20)) == 1 and r20["text"] == REFUSED and lib_calls() == n0 and not any(o["ts"] == T20 for o in outcomes()), (replies_in(T20), lib_calls() - n0))

# ---- SB_ALLOWED_USERS=* : everyone ----
env = dict(E, SB_ALLOWED_USERS="*", SB_ALLOWED_CHANNELS="*", HOME=E["PROOF_HOME"])
p = subprocess.run(["bash", E["PROOF_FLOWS"] + "/install-sb-agent.sh"], env=env, capture_output=True, text=True)
docker("restart", "n8n")
wait(lambda: sh("curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-m", "3", N8N + "/healthz") == "200", 120)
time.sleep(10)
T21, r21, o21, dt = ask("Which paper covers frontier exploration with learned occupancy maps?", user="U0INTRUDER01", channel="C0OTHERCHAN1")
check("SB_ALLOWED_USERS=* and SB_ALLOWED_CHANNELS=*: a user who is not the owner, in another channel, is answered with a sourced answer (the installer says so)",
      "anyone in a channel" in p.stdout and r21 is not None and o21 is not None and o21["verdict"] == "ok" and bool(sources(r21["text"])), (p.stdout[-300:], r21, o21))
print()
print("latency per mention, from the injected event to the reply in the thread (the model is the X3's local Ollama, qwen3 30B-A3B: no vendor, no network hop beyond the tailnet host); in-flow = the agent's start to its answer")
for name, a, b in LATENCY:
    print("  %-50s total %.1fs, in-flow %.1fs" % (name, a, b))
if LATENCY:
    xs = sorted(a for _, a, _ in LATENCY)
    print("  %d mentions: min %.1fs, median %.1fs, max %.1fs" % (len(xs), xs[0], xs[len(xs) // 2], xs[-1]))
print("%d of %d PASS" % (sum(RESULTS), len(RESULTS)))
sys.exit(0 if all(RESULTS) else 1)
