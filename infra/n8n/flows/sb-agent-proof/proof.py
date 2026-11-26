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
    raw = docker("exec", "n8n-db", "psql", "-U", "n8n", "-d", "n8n", "-tAc", "select \"staticData\"::text from workflow_entity where id='sbaskagent00001'").strip()
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


def mention(text, thread_ts=None, ts=None, event_id=None, retry=0, extra=None):
    """Inject an app_mention through the stub's Socket Mode server. Returns (ts, event_id, injected at)."""
    ts = ts or next_ts()
    event_id = event_id or "Ev%s" % ts.replace(".", "")
    ev = {"type": "app_mention", "user": USER, "channel": CHANNEL, "ts": ts, "text": "<@%s> %s" % (BOT, text)}
    if thread_ts:
        ev["thread_ts"] = thread_ts
    ev.update(extra or {})
    t = time.time()
    r = req(SLACK + "/__event", {"event": ev, "event_id": event_id, "retry_attempt": retry})
    assert r["ok"], "the stub has no open Socket Mode connection"
    return ts, event_id, t


def ask(text, thread_ts=None, timeout=300, ts=None):
    """A mention, then wait for its one reply and its outcome record. Returns (ts, reply body or None, outcome or None, seconds)."""
    ts, eid, t0 = mention(text, thread_ts, ts=ts)
    root = thread_ts or ts
    got = wait(lambda: replies_in(root) if any(p["body"]["thread_ts"] == root for p in posts()) else None, timeout)
    dt = time.time() - t0
    oc = wait(lambda: next((o for o in outcomes() if o["event_id"] == eid), None), 30)
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

# ============================================================ every envelope was acked; nothing secret in the bridge's log ============================================================
log = slack_log()
sent = [c["frame"]["envelope_id"] for c in log if c["call"] == "sent" and c["frame"].get("envelope_id")]
acked = [c["frame"].get("envelope_id") for c in log if c["call"] == "ack"]
check("every envelope the stub sent (%d, the retry, the ignored ones and the bot's included) was acked by the bridge, each once" % len(sent), len(sent) > 10 and sorted(sent) == sorted(acked), (len(sent), len(acked), set(sent) ^ set(acked)))
blog = docker("logs", "n8n-proof-bridge")
texts = ["frontier", "Borealis", "occupancy", "football", "universal variable", "PROOF-FORCE"]
check("bridge log: no token, no secret, no socket URL ticket and no message text",
      APP_TOKEN not in blog and SECRET not in blog and "ticket" not in blog and not any(t.lower() in blog.lower() for t in texts), [t for t in texts if t.lower() in blog.lower()])

print()
print("latency per mention, from the injected event to the reply in the thread (the model is the X3's local Ollama, qwen3 30B-A3B: no vendor, no network hop beyond the tailnet host); in-flow = the agent's start to its answer")
for name, a, b in LATENCY:
    print("  %-50s total %.1fs, in-flow %.1fs" % (name, a, b))
if LATENCY:
    xs = sorted(a for _, a, _ in LATENCY)
    print("  %d mentions: min %.1fs, median %.1fs, max %.1fs" % (len(xs), xs[0], xs[len(xs) // 2], xs[-1]))
print("%d of %d PASS" % (sum(RESULTS), len(RESULTS)))
sys.exit(0 if all(RESULTS) else 1)
