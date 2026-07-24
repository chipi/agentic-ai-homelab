"""Investigation-driven triager (SIGNALS §7.3, minimal round-6 version).

A bounded menu-driven probe loop (hard cap N): each turn the model either requests
a typed probe (probes.py) OR decides ONE of four terminal dispositions —
dismiss / cleanup / file / escalate(with a question). Deterministic + replayable.

Deterministic gates (no LLM):
- intent gate on File (§4.1, UNCHANGED — investigation earns what/where/how-often,
  never intent; certainty is not a source),
- cleanup gate (a machine-checkable test/noise marker must be present),
- dismiss gate (must have run a corroborating probe).
Certainty is metadata only, never a gate.
"""
import hashlib
import json
import re
import time

import config
import observ
import probes
from http_util import post_json

ALLOWED_INTENT = {"reporter", "spec", "repo-data", "code-invariant", "baseline",
                  "operator-rule", "slo"}
MAX_PROBES = int(config.env("SF_MAX_PROBES", "3"))
# occurrence_history stays a corroborator but is content-checked, not just usability-
# checked (review R7): it is self-derived from the same issue, so it is ALWAYS usable
# — only a BENIGN-looking history (low count / low level / resolved) may corroborate.
CORROB_PROBES = {"service_logs", "metric", "trace", "source_state", "occurrence_history"}
INDEP_PROBES = {"service_logs", "metric", "trace", "source_state"}
# \btest\b misses camelCase hooks (crashOrreryTest) — the known crash-test hook
# is listed explicitly; do NOT loosen to bare `test` (matches "latest")
CLEANUP_MARKERS = re.compile(
    r"delete me|safe to delete|\btest\b|validation|probe|smoke|e2e|ladder-verify|"
    r"wiring|placeholder|dashless|crashorrerytest", re.I)

_SYSTEM = """You are the triager for an autonomous observability signal fleet. Your JOB
is to DISPOSE of each signal so a human does NOT have to look at it. You INVESTIGATE
with up to %d probes, then COMMIT to ONE terminal disposition. Request probes BY NAME.

ESCALATION IS THE EXPENSIVE EXCEPTION. Every escalate lands on the operator's desk and
spends their attention — the one resource this fleet exists to protect. You should
escalate at most ~1 IN 20 signals. If you escalate more, you are failing the job.
Escalate ONLY when, after probing, you genuinely cannot tell whether the signal is a
real problem or benign — NOT merely because intent is unstated. COMMIT to a decision.

How to decide (investigation earns WHAT / WHERE / HOW-OFTEN):

• FILE — a real problem. This is CHEAP and PREFERRED over escalate: filing hands the
  work to the downstream fix-fleet, not to the operator. Anything error-shaped is
  file-able — an unhandled error / exception / null-deref / failed load is ITSELF a
  code-invariant violation ("code must not throw uncaught"), a citable
  intent_source=code-invariant. You do NOT need an external spec to file a genuine
  error. work_type: bug for code defects, config-enhancement for config/infra issues.
  SPECIAL CASE — telemetry/infra pipeline errors (export timeouts, retry exhaustion,
  queue drops, batch failures): file as config-enhancement EVEN IF the burst has
  subsided. A burst of pipeline failures means a mis-tuned component and possibly
  silent data loss; "it stopped erroring" is NOT "it is healthy".

• DISMISS — the signal is benign / expected / known client-noise. You MUST name the
  probe result that shows benign in dismissal_evidence (an independent probe, or an
  occurrence_history that is genuinely benign — low count, low level, resolved). Do
  not dismiss a real error just because it is rare. The one class where a plain
  browser error is usually dismissable: CLIENT-SIDE NETWORK TRANSIENTS (failed
  dynamic-import/module fetch, script or service-worker load failure) with a benign
  occurrence pattern (low count, no user spread, no recurrence) — dismiss those
  citing that occurrence evidence. NEVER dismiss a signal that carries a test/
  synthetic marker — that is cleanup, not dismiss.

• CLEANUP — test / synthetic / noise you can point to a concrete marker for
  (test hooks, "delete me", validation/smoke events). If you can quote the marker,
  cleanup is ALWAYS preferred over dismiss: cleanup removes the noise at the source;
  dismiss leaves it standing to fire again.

• ESCALATE — LAST RESORT, ~1/20. Genuine category ambiguity you could not resolve by
  probing. Carry a specific question for the human.

Prefer FILE for anything that looks like a real problem; DISMISS (with evidence) or
CLEANUP (with a marker) for benign or junk. Escalate is the residue, not a default.
Write all text in ENGLISH.

Each turn return exactly ONE FLAT JSON object — a probe:
  {"action":"probe","probe":"<name>","probe_args":{...},"why":"..."}
or a terminal decision:
  {"action":"decide","disposition":"file","reason":"...","certainty":"low|med|high","file":{"work_type":"bug|config-enhancement","title":"...","symptom":"...","area":"...","evidence":["..."],"acceptance":[{"criterion":"...","intent_source":"reporter|spec|repo-data|code-invariant|baseline|operator-rule|slo"}]}}
  {"action":"decide","disposition":"dismiss","reason":"...","dismissal_evidence":"the independent probe result proving benign","immediate_recommendation":"... or null","certainty":"..."}
  {"action":"decide","disposition":"cleanup","reason":"...","marker":"the exact test/noise marker text you saw","certainty":"..."}
  {"action":"decide","disposition":"escalate","reason":"...","question":"the specific question a human must answer","certainty":"..."}

PROBE MENU:
%s"""


def _sys():
    return _SYSTEM % (MAX_PROBES, probes.menu())


PROMPT_SHA = hashlib.sha1(_sys().encode()).hexdigest()[:8]


def _signal_intro(signal):
    return "SIGNAL:\n" + json.dumps(
        {k: signal.get(k) for k in ("source", "alertname", "labels", "summary")}, indent=2)


def _trim(v, n=1800):
    s = v if isinstance(v, str) else json.dumps(v)
    return s if len(s) <= n else s[:n] + f"\n…[truncated {len(s)-n} of {len(s)} chars]"


def _call(messages):
    if not config.OPENROUTER_KEY:
        raise SystemExit("[triage] OPENROUTER_API_KEY not set")
    resp = post_json(config.OPENROUTER_URL,
                     {"model": config.TRIAGE_MODEL, "messages": messages,
                      "response_format": {"type": "json_object"}, "temperature": 0},
                     headers={"Authorization": f"Bearer {config.OPENROUTER_KEY}"}, timeout=90)
    return resp["choices"][0]["message"]["content"], resp.get("usage", {})


def _parse(raw):
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise ValueError("no JSON object")
    return json.loads(m.group(0))


def _usable(v):
    if isinstance(v, str):
        v = v.strip()
        return bool(v) and not v.startswith("<")
    if isinstance(v, dict):
        data = v.get("data")
        if isinstance(data, dict):
            return bool(data.get("result"))
        return bool(v)
    return bool(v)


# ---- deterministic gates ----
def _intent_gate(d):
    if d.get("disposition") != "file":
        return d, "n/a"
    f = d.get("file") or {}
    acc = f.get("acceptance") or []
    uncited = sum(1 for c in acc if not (isinstance(c, dict) and c.get("intent_source") in ALLOWED_INTENT))
    if uncited or not acc:
        d["disposition"] = "escalate"
        d["reason"] = f"intent gate: {uncited or 'no'} uncited acceptance — " + d.get("reason", "")
        d["question"] = "What is the intended (citable) behavior that 'fixed' means?"
        d["file"] = None
        return d, "downgraded"
    return d, "passed"


def _cleanup_gate(d, signal):
    if d.get("disposition") != "cleanup":
        return d, "n/a"
    text = " ".join(str(signal.get(k, "")) for k in ("alertname", "summary")) + " " + json.dumps(signal.get("labels", {}))
    if CLEANUP_MARKERS.search(text) or signal.get("labels", {}).get("environment") in ("test", "dev"):
        return d, "passed"
    d["disposition"] = "escalate"
    d["reason"] = "cleanup gate: no machine-checkable test/noise marker — " + d.get("reason", "")
    d["question"] = "Is this genuinely test/noise, safe to clean up at the source?"
    return d, "downgraded (no marker)"


def _benign_history(v):
    """Content check for occurrence_history (review R7): it is self-derived and thus
    always usable, so only a BENIGN-looking history may corroborate a dismiss."""
    if not isinstance(v, dict):
        return False
    lvl = str(v.get("level", "")).lower()
    status = str(v.get("status", "")).lower()
    try:
        cnt = int(v.get("count") or 0)
    except (TypeError, ValueError):
        cnt = 0
    return lvl in ("debug", "info") or status in ("resolved", "ignored") or cnt <= 1


def _corroborates(t):
    """An independent probe with usable content corroborates benign. occurrence_history
    may corroborate ONLY when its content is benign — not merely because it returned."""
    p, r = t["probe"], t["result"]
    if p not in CORROB_PROBES or not _usable(r):
        return False
    if p == "occurrence_history":
        return _benign_history(r)
    return p in INDEP_PROBES


def _to_escalate(d, reason, question):
    d["disposition"] = "escalate"
    d["reason"] = reason + " — " + d.get("reason", "")
    d["question"] = question
    return d


def _dismiss_gate(d, trace):
    if d.get("disposition") != "dismiss":
        return d, "n/a"
    if not str(d.get("dismissal_evidence") or "").strip():
        _to_escalate(d, "dismiss gate: no dismissal_evidence cited",
                     "Dismissed without citing corroborating evidence — confirm benign?")
        return d, "downgraded (no evidence cited)"
    if any(_corroborates(t) for t in trace):
        return d, "passed"
    _to_escalate(d, "dismiss gate: no independent corroborating probe",
                 "Dismissed without independent/benign corroboration — confirm benign?")
    return d, "downgraded (no corroboration)"


def _gate(d, signal, trace):
    d, ig = _intent_gate(d)
    d, cg = _cleanup_gate(d, signal)
    d, dg = _dismiss_gate(d, trace)
    return d, f"i:{ig}/c:{cg}/d:{dg}"


def _finish(signal, disp, trace, gates, usage, t0):
    table_miss = sum(1 for t in trace
                     if isinstance(t["result"], str) and t["result"].startswith("<TABLE-MISS"))
    disp["_meta"] = {"model": config.TRIAGE_MODEL, "prompt_ver": config.TRIAGE_PROMPT_VER,
                     "prompt_sha": PROMPT_SHA, "gates": gates,
                     "probes": [t["probe"] for t in trace], "n_probes": len(trace),
                     "table_miss": table_miss,
                     "certainty": disp.get("certainty"), "usage": usage}
    observ.finalize(signal, disp, usage=usage, latency_s=time.time() - t0)
    return disp


def investigate(signal, max_probes=None, probe_table=None):
    n = MAX_PROBES if max_probes is None else max_probes
    messages = [{"role": "system", "content": _sys()},
                {"role": "user", "content": _signal_intro(signal)}]
    trace, usage, t0 = [], {}, time.time()
    for step in range(n + 1):
        try:
            raw, usage = _call(messages)
        except SystemExit:
            raise
        except Exception as e:  # transport
            return _finish(signal, {"disposition": "escalate", "reason": f"triager call failed: {e}",
                                    "question": "transient failure — retry?"}, trace, "n/a", usage, t0)
        if not isinstance(raw, str) or not raw.strip():
            # contentless completion = provider flake (measured 2026-07-24:
            # billing/provider issues present as empty responses) — retry the
            # same turn; do NOT feed None into the parse-feedback path
            print(f"    [triage] empty completion at step {step+1} — retrying turn")
            continue
        try:
            out = _parse(raw)
        except Exception as e:
            messages.append({"role": "assistant", "content": raw[:600]})
            messages.append({"role": "user", "content": f"Invalid JSON ({e}). Return ONE valid JSON object only."})
            continue
        if out.get("action") == "probe" and step < n:
            name, args = out.get("probe"), out.get("probe_args") or {}
            result = probes.run_probe(signal, name, args, table=probe_table)
            trace.append({"probe": name, "args": args, "result": result})
            print(f"    probe[{step+1}] {name} -> {_trim(result, 90)}")
            messages.append({"role": "assistant", "content": raw[:600]})
            messages.append({"role": "user", "content": f"PROBE {name} result:\n{_trim(result)}"})
            continue
        # decide: the disposition object IS `out` (flat; "disposition" is a string)
        disp = {k: v for k, v in out.items() if k != "action"}
        if not isinstance(disp.get("disposition"), str):
            messages.append({"role": "assistant", "content": raw[:400]})
            messages.append({"role": "user", "content":
                             ("Probe budget exhausted. " if step >= n else "")
                             + 'Return a FLAT decision: {"action":"decide","disposition":'
                               '"dismiss|cleanup|file|escalate", ...}.'})
            if step < n:
                continue
            try:
                out2 = _parse(_call(messages)[0])
                disp = {k: v for k, v in out2.items() if k != "action"}
            except Exception:
                disp = {}
        if not isinstance(disp.get("disposition"), str):
            disp = {"disposition": "escalate", "reason": "no terminal decision",
                    "question": "triager did not reach a disposition"}
        d, gates = _gate(disp, signal, trace)
        return _finish(signal, d, trace, gates, usage, t0)


# back-compat: orchestrator calls triage.triage(signal, evidence); investigation
# does its own lazy probing, so `evidence` is ignored.
def triage(signal, evidence=None, attempts=3):
    return investigate(signal)
