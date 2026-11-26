#!/usr/bin/env python3
"""The checks of the case 1 Slack flows' proof (run.sh sets the environment up and calls this; PYTHONPATH has flotilla's plumbing/).
The question flow is run with `n8n execute` (its Run now trigger) instead of waiting for the schedule; the reply flow is called with
flotilla's own plumbing/call.py (execute, check, post, sign), the sender the worker uses. Prints PASS/FAIL per check, `N of M PASS`,
exits 1 on any FAIL. Never prints a secret or a token."""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

import call  # flotilla's plumbing/call.py

E = os.environ
SLACK, HOOK, N8N = E["SLACK_URL"], E["HOOK_URL"], E["N8N_URL"]
CHANNEL = "C0CM2K87SR1"
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  <- " + str(detail)[:400]), flush=True)


def req(url, doc=None):
    r = urllib.request.Request(url, data=None if doc is None else json.dumps(doc).encode(), method="GET" if doc is None else "POST")
    with urllib.request.urlopen(r, timeout=30) as f:
        return json.loads(f.read() or b"null")


def steer(base, path, doc):
    req(base + path, doc)


def hook_calls():
    return [c for c in req(HOOK + "/__log") if c["call"] == "ask"]


def slack_log(kind):
    return [c for c in req(SLACK + "/__log") if c["call"] == kind]


def run_ask():
    """One poll of the question flow, as the schedule would run it: returns n8n's exit code (non-zero when the execution failed)."""
    p = subprocess.run(["docker", "--context", E["DEV_CONTEXT"], "exec", "-e", "N8N_RUNNERS_BROKER_PORT=5690", "n8n", "n8n", "execute", "--id=case1slackask001"],
                       capture_output=True, text=True, timeout=180)
    return p.returncode, p.stdout + p.stderr


def msg(ts, text="a question", user="U0PROOFASK1", **kw):
    m = {"ts": ts, "text": text}
    if user:
        m["user"] = user
    m.update(kw)
    steer(SLACK, "/__add", m)


# ============================ the question flow: Slack #ask -> the ask hook ============================
steer(SLACK, "/__set", {"messages": [{"ts": "1700000001.000100", "user": "U0OLD00001", "text": "an old question"},
                                      {"ts": "1700000002.000100", "bot_id": "B0OLD", "text": "an old bot line"}], "reset_log": True})
rc, out = run_ask()
h = slack_log("history")
check("ask: the first run backfills nothing (old history is not posted)", rc == 0 and not hook_calls(), (rc, out[-300:]))
check("ask: the first run asked Slack for one message only, with the token", len(h) == 1 and h[0]["limit"] == "1" and h[0]["auth"] and h[0]["channel"] == CHANNEL, h)

msg("1700000010.000100", "What is our pricing plan?")
msg("1700000011.000100", "a bot says hi", user=None, bot_id="B0BOT0001")
msg("1700000012.000100", "a thread reply", thread_ts="1700000010.000100")
msg("1700000013.000100", "someone joined", subtype="channel_join")
rc, out = run_ask()
c = hook_calls()
check("ask: a new human message produces exactly one hook call (a bot, a thread reply and a subtype message produce none)", rc == 0 and len(c) == 1, (rc, [x["delivery"] for x in c]))
if c:
    k = c[0]
    check("ask: its delivery id is slack-<channel>-<ts>", k["delivery"] == "slack-%s-1700000010.000100" % CHANNEL, k["delivery"])
    check("ask: its signature verifies (flotilla's sign, timestamp window, delivery pattern) and flotilla-side answer is 202", k["sig_ok"] and k["code"] == 202, k)
    check("ask: its body is exactly {thread, user, text}", json.loads(k["raw"]) == {"thread": "1700000010.000100", "user": "U0PROOFASK1", "text": "What is our pricing plan?"}, k["raw"])
else:
    check("ask: its delivery id is slack-<channel>-<ts>", False, "no call")

n = len(hook_calls())
steer(SLACK, "/__set", {"reset_log": True})
rc, out = run_ask()
h = slack_log("history")
check("ask: a second run with no new messages produces none", rc == 0 and len(hook_calls()) == n, (rc, len(hook_calls()), n))
check("ask: the second run asked only for what is after the newest message seen (the ignored ones included)", len(h) == 1 and h[0]["oldest"] == "1700000013.000100", h)

msg("1700000020.000100", "é" * 2500)
rc, out = run_ask()
c = hook_calls()
check("ask: a text over 2000 characters is cut to 2000", rc == 0 and len(c) == n + 1 and len(json.loads(c[-1]["raw"])["text"]) == 2000, (rc, len(c)))

# a hook failure leaves the message for the next run, then it goes once
n = len(hook_calls())
msg("1700000030.000100", "will the hook be down?")
steer(HOOK, "/__fail", {"status": 500, "times": 1})
rc1, out1 = run_ask()
c = hook_calls()[n:]
check("ask: a hook failure (500) fails the run and the message is tried once", rc1 != 0 and [x["code"] for x in c] == [500], (rc1, [x.get("code") for x in c]))
rc2, out2 = run_ask()
c = hook_calls()[n:]
check("ask: the next run sends the same delivery again and it is accepted (202)", rc2 == 0 and [x["code"] for x in c] == [500, 202] and c[0]["delivery"] == c[1]["delivery"], (rc2, [x.get("code") for x in c]))
rc3, out3 = run_ask()
check("ask: and the run after that sends nothing", rc3 == 0 and len(hook_calls()) == n + 2, (rc3, len(hook_calls()) - n))

# several messages, a Slack page of 2 (history comes newest first): all are read before any is sent, oldest first, once each
n = len(hook_calls())
steer(SLACK, "/__set", {"page_cap": 2, "reset_log": True})
for i in range(1, 6):
    msg("17000001%02d.000100" % i, "bulk %d" % i, user="U0BULK%04d" % i)
rc, out = run_ask()
c = hook_calls()[n:]
h = slack_log("history")
check("ask: five new messages over three Slack pages go oldest first, one call each", rc == 0 and [x["delivery"].split("-")[-1] for x in c] == ["17000001%02d.000100" % i for i in range(1, 6)], (rc, [x["delivery"] for x in c]))
check("ask: the pages were followed by cursor", [x["cursor"] for x in h] == ["", "2", "4"], h)
steer(SLACK, "/__set", {"page_cap": 0})

# Slack saying ok:false fails the run and leaves the state
n = len(hook_calls())
steer(SLACK, "/__set", {"history_error": "invalid_auth", "reset_log": True})
msg("1700000200.000100", "asked while Slack was refusing")
rc, out = run_ask()
check("ask: Slack ok:false fails the run with Slack's error and posts nothing", rc != 0 and "invalid_auth" in out and len(hook_calls()) == n, (rc, out[-300:]))
steer(SLACK, "/__set", {"history_error": None})
rc, out = run_ask()
c = hook_calls()[n:]
check("ask: the state was unchanged, so the next good run sends that message", rc == 0 and [x["delivery"].split("-")[-1] for x in c] == ["1700000200.000100"], (rc, [x["delivery"] for x in c]))

# flotilla refusing one message for itself (422) is not retried for ever
n = len(hook_calls())
msg("1700000300.000100", "a message the hook refuses")
steer(HOOK, "/__fail", {"status": 422, "times": 1})
rc1, out1 = run_ask()
rc2, out2 = run_ask()
rc3, out3 = run_ask()
check("ask: a message flotilla refuses for itself (422) is sent once and moved past", len(hook_calls()) == n + 1, len(hook_calls()) - n)
check("ask: the refusal shows as one failed run (the next), then the runs are green", rc1 == 0 and rc2 != 0 and "1700000300.000100" in out2 and rc3 == 0, (rc1, rc2, rc3))

# ============================ the reply flow: flotilla's plumbing.reply -> chat.postMessage ============================
URL = N8N + "/webhook/flotilla-reply"
env = {"PLUMBING_REPLY_URL": URL, "PLUMBING_REPLY_SECRET_FILE": E["REPLY_SECRET_FILE"]}
secret = open(E["REPLY_SECRET_FILE"]).read().strip()
case = {"id": "case-proof-" + str(int(time.time()))}
THREAD = "1700000010.000100"
params = {"channel": "general", "thread": THREAD, "text": "[flotilla] The pricing plan is in the roadmap doc. Sources: https://example.org/doc"}
action = "plumbing.reply"
plan = {"action": action, "params": params, "plan_hash": call.plan_hash(case["id"], action, params)}
steer(SLACK, "/__set", {"reset_log": True, "post_error": None})

st = call.check(case, {"action": action, "params": params}, env)
check("reply: status before the send says not done (flotilla's check: not_yet)", st["outcome"] == "not_yet", st)
out = call.execute(case, plan, env)
posts = slack_log("post")
check("reply: flotilla's sender gets a ref back (executed)", out["outcome"] == "executed" and out.get("ref"), out)
p = posts[0]["body"] if posts else {}
check("reply: exactly one chat.postMessage, in the question's thread, in #ask, with the token", len(posts) == 1 and posts[0]["auth"] and p.get("channel") == CHANNEL and p.get("thread_ts") == THREAD, posts)
check("reply: its text is the plan's and unfurling is off", p.get("text") == params["text"] and p.get("unfurl_links") is False and p.get("unfurl_media") is False, p)
st = call.check(case, {"action": action, "params": params}, env)
check("reply: status after the send says done with the ref (flotilla's check: verified)", st["outcome"] == "verified" and out.get("ref", "x") in st["detail"], st)
out2 = call.execute(case, plan, env)
check("reply: a re-send of the same delivery posts nothing new and answers the same ref", out2["outcome"] == "executed" and out2.get("ref") == out.get("ref") and len(slack_log("post")) == 1, (out2, len(slack_log("post"))))
other = dict(params, text="[flotilla] a different reply")
st = call.check(case, {"action": action, "params": other}, env)
check("reply: status for a ref never sent says not done", st["outcome"] == "not_yet", st)


def raw_call(doc, delivery="plan-rawcheck0001", sec=secret, now=time.time):
    try:
        call.post(URL, sec, delivery, doc, now=now)
        return 200
    except urllib.error.HTTPError as e:
        e.close()
        return e.code


n = len(slack_log("post"))
send = {"mode": "send", "action": action, "case_id": case["id"], "plan_hash": "x", "params": params}
check("reply: a bad signature is 401", raw_call(send, sec="0" * 64) == 401)
check("reply: a stale timestamp is 401", raw_call(send, now=lambda: time.time() - 3600) == 401)
check("reply: a channel other than general is refused (400)", raw_call(dict(send, params=dict(params, channel="random")), delivery="plan-rawcheck0002") == 400)
check("reply: a thread that is not a Slack ts is refused (400)", raw_call(dict(send, params=dict(params, thread="../x")), delivery="plan-rawcheck0003") == 400)
check("reply: a text over 3000 characters is refused (400)", raw_call(dict(send, params=dict(params, text="x" * 3001)), delivery="plan-rawcheck0004") == 400)
check("reply: the refused and unsigned calls posted nothing", len(slack_log("post")) == n, len(slack_log("post")) - n)

# Slack refusing the post: a 502, nothing is recorded, and the retry posts once
params3 = dict(params, text="[flotilla] a reply while Slack refuses")
plan3 = {"action": action, "params": params3, "plan_hash": call.plan_hash(case["id"], action, params3)}
steer(SLACK, "/__set", {"post_error": "channel_not_found"})
n = len(slack_log("post"))
o = call.execute(case, plan3, env)
check("reply: Slack refusing the post is not a ref (escalate), and status says not done", o["outcome"] == "escalate" and call.check(case, {"action": action, "params": params3}, env)["outcome"] == "not_yet", o)
steer(SLACK, "/__set", {"post_error": None})
o = call.execute(case, plan3, env)
check("reply: the retry of that delivery posts once", o["outcome"] == "executed" and len(slack_log("post")) == n + 2, (o, len(slack_log("post")) - n))

ok = sum(RESULTS)
print("%d of %d PASS" % (ok, len(RESULTS)))
sys.exit(0 if ok == len(RESULTS) else 1)
