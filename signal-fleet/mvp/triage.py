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
CORROB_PROBES = {"service_logs", "metric", "trace", "source_state", "occurrence_history"}
CLEANUP_MARKERS = re.compile(
    r"delete me|safe to delete|\btest\b|validation|probe|smoke|e2e|ladder-verify|"
    r"wiring|placeholder|dashless", re.I)

_SYSTEM = """You are the triager for an autonomous observability signal fleet. You
INVESTIGATE each signal with up to %d probes, then decide ONE terminal disposition.
You never write raw queries — request a probe BY NAME from the menu.

Investigation earns WHAT / WHERE / HOW-OFTEN. It does NOT earn INTENT: a File's
acceptance must still cite an intent_source; certainty from investigation is NOT a
source. Prefer dismiss/cleanup over a low-certainty File (a File has downstream cost).
Write all text in ENGLISH.

Each turn return exactly ONE FLAT JSON object — either a probe:
  {"action":"probe","probe":"<name>","probe_args":{...},"why":"..."}
or a decision (the "disposition" value is a STRING; the other fields are its siblings):
  {"action":"decide","disposition":"dismiss","reason":"...","immediate_recommendation":"... or null","certainty":"low|med|high"}
  {"action":"decide","disposition":"cleanup","reason":"...","marker":"the test/noise marker you saw","certainty":"..."}
  {"action":"decide","disposition":"file","reason":"...","certainty":"...","file":{"work_type":"bug|config-enhancement","title":"...","symptom":"...","area":"...","evidence":["..."],"acceptance":[{"criterion":"...","intent_source":"reporter|spec|repo-data|code-invariant|baseline|operator-rule|slo"}]}}
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


def _dismiss_gate(d, trace):
    if d.get("disposition") != "dismiss":
        return d, "n/a"
    if any(t["probe"] in CORROB_PROBES and _usable(t["result"]) for t in trace):
        return d, "passed"
    d["disposition"] = "escalate"
    d["reason"] = "dismiss gate: no corroborating probe run — " + d.get("reason", "")
    d["question"] = "Dismissed without corroborating evidence — confirm benign?"
    return d, "downgraded (no corroboration)"


def _gate(d, signal, trace):
    d, ig = _intent_gate(d)
    d, cg = _cleanup_gate(d, signal)
    d, dg = _dismiss_gate(d, trace)
    return d, f"i:{ig}/c:{cg}/d:{dg}"


def _finish(signal, disp, trace, gates, usage, t0):
    disp["_meta"] = {"model": config.TRIAGE_MODEL, "prompt_ver": config.TRIAGE_PROMPT_VER,
                     "prompt_sha": PROMPT_SHA, "gates": gates,
                     "probes": [t["probe"] for t in trace], "n_probes": len(trace),
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
