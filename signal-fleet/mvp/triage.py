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
import os
import re
import time
import urllib.error

import config
import observ
import probes
from http_util import post_json


class TriagerDown(Exception):
    """The triager LLM gateway is PERSISTENTLY unavailable (auth 401/403) — not a
    one-off transport flake. Propagated out of triage() so the orchestrator fails
    CLOSED (one aggregate issue), instead of escalating every signal individually.
    This is the 2026-08-13→19 flood's core fix (a wiped litellm key 401'd every
    call and the fleet fail-open escalated ~90 signals)."""

ALLOWED_INTENT = {"reporter", "spec", "repo-data", "code-invariant", "baseline",
                  "operator-rule", "slo"}
MAX_PROBES = int(config.env("SF_MAX_PROBES", "3"))
# occurrence_history stays a corroborator but is content-checked, not just usability-
# checked (review R7): it is self-derived from the same issue, so it is ALWAYS usable
# — only a BENIGN-looking history (low count / low level / resolved) may corroborate.
CORROB_PROBES = {"service_logs", "metric", "trace", "source_state", "occurrence_history"}
INDEP_PROBES = {"service_logs", "metric", "trace", "source_state"}
# \btest\b misses camelCase hooks (crashOrreryTest) — the known crash-test hook
# is listed explicitly; do NOT loosen to bare `test` (matches "latest").
# staging/\bdev\b/\bverify\b: non-prod environments and verification runs are
# noise-at-source in the prod tracker (PODCAST-7: env=dev from a laptop run).
CLEANUP_MARKERS = re.compile(
    r"delete me|safe to delete|\btest\b|validation|probe|smoke|e2e|ladder-verify|"
    r"wiring|placeholder|dashless|crashorrerytest|staging|\bdev\b|\bverify\b", re.I)

# Operational states that are NOT code bugs: a guardrail firing (its own incident,
# working as designed), a billing state, or a DOWNSTREAM effect of one. These are
# classified deterministically and acknowledged-not-ticketed — the guardrail/alert
# already fired; the fleet must not turn each occurrence into a bug ticket. 72 of
# the 2026-08-13→19 flood were "cost soft cap". Downstream (provider-not-initialized
# / fallback-failed) is folded to the same class here (the correlation half of #6:
# they share the budget/cap root). See docs/wip/signal-fleet-flood-hardening.md.
OPERATIONAL_MARKERS = [
    (re.compile(r"cost soft cap|cost cap exceeded|costcapexceeded|soft[- ]?cap exceeded", re.I),
     "cost-cap"),
    (re.compile(r"no budget|no credit|insufficient (credit|budget|fund)|\b402\b|"
                r"payment required|out of credit|quota exceeded", re.I),
     "provider-budget"),
    (re.compile(r"openaiprovider not initialized|provider not initialized|"
                r"fallback tier failed|all fallbacks failed|fallback failed", re.I),
     "provider-fallback"),
]


def operational_class(signal):
    """Return the operational class (cost-cap/provider-budget/provider-fallback) if
    the signal is an operational state, else None. Deterministic, no LLM."""
    hay = " ".join(str(signal.get(k, "")) for k in ("alertname", "summary")) + \
        " " + json.dumps(signal.get("labels", {}))
    for rx, cls in OPERATIONAL_MARKERS:
        if rx.search(hay):
            return cls
    return None


# #3/#2 — secondary classes that BIAS routing (work_type) but NEVER gate the
# disposition. The LLM still owns file-vs-escalate; the class is a per-signal HINT
# that steers `bug` → `config-enhancement` for provider/environment/recoverable
# conditions and templates the acceptance criteria. PRECEDENCE (review R5):
# operational_class runs FIRST (dismiss, no LLM); signal_class only classifies what
# reaches investigation, so a "fallback failed" (operational → dismiss) never reaches
# the recoverable hint. Markers are SPECIFIC/server-side so they can't fire on the
# existing client-side fixtures (a bare "timeout" is NOT enough — a named upstream
# is required), which keeps the eval's existing behavior unchanged.
SIGNAL_CLASS_MARKERS = [
    (re.compile(r"(deepgram|openai|anthropic|gemini|whisper|elevenlabs|assemblyai|"
                r"\bs3\b|\bgcs\b)\b.{0,40}?(timed out|timeout|temporarily unavailable|"
                r"connection reset|\b50[234]\b)", re.I), "external-transient"),
    (re.compile(r"\b(write|read) operation timed out\b", re.I), "external-transient"),
    (re.compile(r"data_inspection_failed|content[_ ]?policy|moderation_blocked|"
                r"invalid_request_error.{0,40}(safety|policy)", re.I), "external"),
    (re.compile(r"permission denied|read-only file system|no space left|cargo_home|"
                r"/root/\.cargo|lanceerror\(io\)|errno 1[38]|errno 28|disk quota exceeded",
                re.I), "environment"),
    (re.compile(r"recoverablesummarizationerror|recoverable\w*error|repaired \d+/\d+|"
                r"\bdegraded\b|recovered gracefully|extractive fallback|reroll succeeded",
                re.I), "recoverable"),
]

# defeasible hints — each ends by handing the decision back so the class stays a
# BIAS, not a gate (the anchor-override fixture verifies the LLM can overrule it).
_CLASS_HINT = {
    "external-transient": (
        "PRE-CLASSIFICATION HINT (deterministic, advisory): this looks like an EXTERNAL "
        "TRANSIENT — a named third-party dependency timed out or was briefly unavailable. "
        "If so it is NOT a code invariant: file as work_type=config-enhancement "
        "(retry-with-backoff, then WARN + degrade on exhaustion). BUT if the evidence "
        "shows OUR code mishandles the failure, file work_type=bug. You decide."),
    "external": (
        "PRE-CLASSIFICATION HINT (deterministic, advisory): this looks like an UPSTREAM "
        "REJECTION — the provider refused on its own policy/safety, not our defect. If so, "
        "work_type=config-enhancement (catch → skip/fallback that item + WARN). File "
        "work_type=bug only if our code should have handled it and does not. You decide."),
    "environment": (
        "PRE-CLASSIFICATION HINT (deterministic, advisory): this looks like an ENVIRONMENT/"
        "INFRA condition (permissions, disk, missing mount) — a container/image fix, "
        "work_type=config-enhancement, NOT a code invariant. File work_type=bug only if "
        "the code itself is at fault. You decide."),
    "recoverable": (
        "PRE-CLASSIFICATION HINT (deterministic, advisory): this looks RECOVERABLE — the "
        "pipeline already handled/degraded through it and still logged ERROR. It is WARN-"
        "level, low-priority: file work_type=config-enhancement (track the degradation) "
        "rather than work_type=bug. File work_type=bug only if the recovery itself is "
        "broken. You decide."),
}


def signal_class(signal):
    """Deterministic secondary class or None. A HINT to the triager (see _CLASS_HINT),
    NEVER a disposition gate. Runs conceptually AFTER operational_class."""
    hay = " ".join(str(signal.get(k, "")) for k in ("alertname", "summary")) + \
        " " + json.dumps(signal.get("labels", {}))
    for rx, cls in SIGNAL_CLASS_MARKERS:
        if rx.search(hay):
            return cls
    return None

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
    intro = "SIGNAL:\n" + json.dumps(
        {k: signal.get(k) for k in ("source", "alertname", "labels", "summary")}, indent=2)
    cls = signal_class(signal)   # #3/#2 — per-signal HINT, keeps PROMPT_SHA stable
    # SF_NO_CLASS_HINT suppresses the hint — used ONLY for the eval A/B to reproduce
    # pre-#3/#2 behavior on the identical fixtures. Never set in production.
    if cls and not os.environ.get("SF_NO_CLASS_HINT"):
        intro += "\n\n" + _CLASS_HINT[cls]
    return intro


def _trim(v, n=1800):
    s = v if isinstance(v, str) else json.dumps(v)
    return s if len(s) <= n else s[:n] + f"\n…[truncated {len(s)-n} of {len(s)} chars]"


def _call(messages):
    if not config.OPENROUTER_KEY:
        raise SystemExit("[triage] OPENROUTER_API_KEY not set")
    try:
        resp = post_json(config.OPENROUTER_URL,
                         {"model": config.TRIAGE_MODEL, "messages": messages,
                          "response_format": {"type": "json_object"}, "temperature": 0},
                         headers={"Authorization": f"Bearer {config.OPENROUTER_KEY}"}, timeout=90)
    except urllib.error.HTTPError as e:
        # 401/403 = the gateway rejected our key (wiped litellm virtual key is the
        # known cause) — PERSISTENT, every call will fail. Fail closed, don't escalate.
        if e.code in (401, 403):
            raise TriagerDown(f"HTTP {e.code} auth failure to the triager gateway "
                              f"({config.OPENROUTER_URL}) — litellm virtual key rejected "
                              f"(recreate: infra/litellm/README.md)") from e
        raise
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
    r = config.RATES.get(config.TRIAGE_MODEL)
    cost = 0.0
    if r and isinstance(usage, dict):
        cost = (usage.get("prompt_tokens") or 0) * r[0] + (usage.get("completion_tokens") or 0) * r[1]
    disp["_meta"] = {"model": config.TRIAGE_MODEL, "prompt_ver": config.TRIAGE_PROMPT_VER,
                     "prompt_sha": PROMPT_SHA, "gates": gates,
                     "probes": [t["probe"] for t in trace], "n_probes": len(trace),
                     "table_miss": table_miss, "cost_usd": round(cost, 6),
                     "certainty": disp.get("certainty"), "usage": usage}
    observ.finalize(signal, disp, usage=usage, latency_s=time.time() - t0)
    return disp


def investigate(signal, max_probes=None, probe_table=None):
    n = MAX_PROBES if max_probes is None else max_probes
    messages = [{"role": "system", "content": _sys()},
                {"role": "user", "content": _signal_intro(signal)}]
    # usage accumulates across ALL turns — reconciliation vs LiteLLM metering
    # (2026-07-30) showed last-turn-only recording undercounted tokens ~4x
    trace, usage, t0 = [], {"prompt_tokens": 0, "completion_tokens": 0}, time.time()
    for step in range(n + 1):
        try:
            raw, turn_usage = _call(messages)
            if isinstance(turn_usage, dict):
                for k in ("prompt_tokens", "completion_tokens"):
                    usage[k] += turn_usage.get(k) or 0
        except SystemExit:
            raise
        except TriagerDown:
            raise   # persistent auth outage — fail CLOSED at the orchestrator, not per-signal
        except Exception as e:  # transport (one-off flake) — keep the per-signal escalate
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
    # deterministic operational-state gate (no LLM): guardrail/billing/downstream
    # states are acknowledged-not-ticketed, and this holds even when the triager is
    # down (so a 401 outage can't turn a cost-cap storm into bug tickets).
    cls = operational_class(signal)
    if cls:
        disp = {
            "disposition": "dismiss",
            "reason": (f"operational state ({cls}) — a guardrail/billing state or its "
                       f"downstream, not a code bug; the alert already fired. "
                       f"Acknowledged, not ticketed."),
            "dismissal_evidence": f"deterministic operational classifier matched '{cls}'",
            "certainty": "high",
            "_meta": {"model": "none(operational-gate)",
                      "prompt_ver": config.TRIAGE_PROMPT_VER, "prompt_sha": PROMPT_SHA,
                      "gates": f"operational:{cls}", "probes": [], "n_probes": 0,
                      "table_miss": 0, "cost_usd": 0.0, "certainty": "high",
                      "operational_class": cls, "usage": {}},
        }
        observ.finalize(signal, disp, usage={}, latency_s=0.0)
        print(f"    [operational:{cls}] {signal.get('alertname','')[:70]} -> dismiss (no ticket)")
        return disp
    return investigate(signal)
