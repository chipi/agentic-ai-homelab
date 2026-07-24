"""The correlation-aware triager (SIGNALS §4, §4.1, §7).

Mirrors bugfix-fleet's directAdapter: raw OpenRouter chat + validate-and-retry +
deterministic post-LLM gates (no LLM in a gate). Returns a disposition:
dismiss / file / escalate.

Gates (SIGNALS §4.1, review R3-2):
- intent gate: on `file`, every acceptance criterion must cite an `intent_source`.
- dismiss gate: a `dismiss` must be backed by at least one usable evidence query
  (non-empty, non-error) — a model can't dismiss into a vacuum.
"""
import hashlib
import json
import re

import config
from http_util import post_json

# shared base vocab with Fleet-1 agents/triage.md + our signal extensions
# (SIGNALS §4.1 / §13.4; review R3-4 — keep docs and code identical).
ALLOWED_INTENT = {
    "reporter", "spec", "repo-data", "code-invariant", "baseline",
    "operator-rule", "slo",
}

SYSTEM = """You are the triager for an autonomous observability signal fleet.
You receive ONE production signal plus a CORRELATED evidence bundle (logs,
metrics, traces). You decide a disposition from the WHOLE picture, never a single
line. Correlation proves what happened; it cannot prove what was intended.

Dispositions:
- "dismiss": false alarm / already-recovered / no real ongoing defect. Only
  dismiss when the evidence positively supports it. If a real signal is merely
  mis-tuned (noisy threshold), dismiss AND set immediate_recommendation.
- "file": a genuine, acceptance-statable defect. Produce an L1-candidate.
- "escalate": ambiguous, novel, high blast-radius, OR no citable intent source,
  OR evidence too thin to judge.

Intent gate (hard): on "file", EVERY acceptance criterion MUST carry an
"intent_source" from: reporter, spec, repo-data, code-invariant, baseline,
operator-rule, slo. "code-invariant" (a 5xx/crash must not happen) is an
acceptance FLOOR, not the whole acceptance. If you cannot cite intent for what
"fixed" means, escalate.

work_type routing: "bug" (behavior/code defect -> dev fleet) or
"config-enhancement" (monitoring/infra config -> operator). A mis-tuned alert is
config-enhancement, never bug.

Return ONE JSON object, no prose, exactly this shape:
{"disposition":"dismiss|file|escalate","reason":"...",
 "immediate_recommendation":"... or null",
 "file":{"work_type":"bug|config-enhancement","title":"...","symptom":"...",
   "area":"...","evidence":["..."],
   "acceptance":[{"criterion":"...","intent_source":"reporter|spec|repo-data|code-invariant|baseline|operator-rule|slo"}]}
 }
On dismiss/escalate set "file" to null."""

PROMPT_SHA = hashlib.sha1(SYSTEM.encode()).hexdigest()[:8]


def _trim(val, n=1800):
    s = val if isinstance(val, str) else json.dumps(val)
    if len(s) <= n:
        return s
    return s[:n] + f"\n…[truncated {len(s) - n} of {len(s)} chars]"  # review R3-2b


def build_user(signal, evidence):
    lines = [
        "SIGNAL:",
        json.dumps({k: signal.get(k) for k in ("source", "alertname", "labels", "summary")}, indent=2),
        "",
        "CORRELATED EVIDENCE (trimmed; truncation is marked explicitly):",
    ]
    for name, val in evidence.get("queries", {}).items():
        lines.append(f"--- {name} ---")
        lines.append(_trim(val))
    return "\n".join(lines)


def _call(messages):
    if not config.OPENROUTER_KEY:  # review R3-8: clean error, not a mid-call HTTP fail
        raise SystemExit("[triage] OPENROUTER_API_KEY not set")
    payload = {
        "model": config.TRIAGE_MODEL,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    resp = post_json(
        config.OPENROUTER_URL, payload,
        headers={"Authorization": f"Bearer {config.OPENROUTER_KEY}"},
        timeout=90,
    )
    return resp["choices"][0]["message"]["content"]


def _parse(raw):
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise ValueError("no JSON object in response")
    d = json.loads(m.group(0))
    if d.get("disposition") not in ("dismiss", "file", "escalate"):
        raise ValueError(f"bad disposition: {d.get('disposition')!r}")
    if d["disposition"] == "file":
        f = d.get("file")
        if not isinstance(f, dict) or not f.get("acceptance"):
            raise ValueError("file disposition without file.acceptance")
    return d


def _intent_gate(d):
    """On `file`, count uncited/invalid acceptance criteria; any -> escalate."""
    if d.get("disposition") != "file":
        return d, "n/a"
    uncited = sum(
        1 for c in d["file"]["acceptance"]
        if not (isinstance(c, dict) and c.get("intent_source") in ALLOWED_INTENT)
    )
    if uncited:
        d["disposition"] = "escalate"
        d["reason"] = f"intent gate: {uncited} uncited acceptance criteria — " + d.get("reason", "")
        d["file"] = None
        return d, f"downgraded ({uncited} uncited)"
    return d, "passed"


def _usable(v):
    if isinstance(v, str):
        v = v.strip()
        return bool(v) and not v.startswith("<error")
    # JSON result: a PromQL vector with a non-empty result array counts
    if isinstance(v, dict):
        data = v.get("data", {})
        return bool(data.get("result")) if isinstance(data, dict) else bool(v)
    return bool(v)


def _dismiss_gate(d, evidence):
    """A dismiss must be backed by >=1 usable evidence query (review R3-2a).
    Deterministic — no LLM. Prevents a hallucinated 'already recovered' from
    passing when the evidence is empty/errored."""
    if d.get("disposition") != "dismiss":
        return d, "n/a"
    qs = (evidence or {}).get("queries", {})
    if not any(_usable(v) for v in qs.values()):
        d["disposition"] = "escalate"
        d["reason"] = "dismiss gate: no usable evidence to support dismissal — " + d.get("reason", "")
        d["immediate_recommendation"] = None
        return d, "downgraded (no evidence)"
    return d, "passed"


def triage(signal, evidence, attempts=3):
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": build_user(signal, evidence)}]
    last_err = None
    for i in range(attempts):
        try:
            raw = _call(messages)
        except SystemExit:
            raise
        except Exception as e:  # transport flake
            last_err = e
            print(f"  [triage] call attempt {i+1} failed: {e}")
            continue
        try:
            d = _parse(raw)
        except Exception as e:  # shape failure -> feed the error back (review R3-5)
            last_err = e
            print(f"  [triage] parse attempt {i+1} failed: {e}")
            messages.append({"role": "assistant", "content": raw[:1000]})
            messages.append({"role": "user", "content":
                             f"Your previous reply was not valid: {e}. Return ONLY the "
                             "JSON object, matching the schema exactly, no prose."})
            continue
        d, igate = _intent_gate(d)
        d, dgate = _dismiss_gate(d, evidence)
        d["_meta"] = {"attempt": i + 1, "intent_gate": igate, "dismiss_gate": dgate,
                      "model": config.TRIAGE_MODEL,
                      "prompt_ver": config.TRIAGE_PROMPT_VER, "prompt_sha": PROMPT_SHA}
        return d
    return {"disposition": "escalate",
            "reason": f"triager unparseable after {attempts}: {last_err}",
            "immediate_recommendation": None, "file": None,
            "_meta": {"attempt": attempts, "intent_gate": "n/a", "dismiss_gate": "n/a",
                      "degraded": True, "model": config.TRIAGE_MODEL,
                      "prompt_ver": config.TRIAGE_PROMPT_VER, "prompt_sha": PROMPT_SHA}}
