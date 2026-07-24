"""The correlation-aware triager (SIGNALS §4, §4.1, §7).

Mirrors bugfix-fleet's directAdapter: raw OpenRouter chat + validate-and-retry +
a deterministic intent-source gate (no LLM in the gate). Returns a disposition:
dismiss / file / escalate. On `file`, every acceptance criterion must cite an
`intent_source` (else the gate downgrades to escalate).
"""
import json
import re

import config
from http_util import post_json

# shared vocab with Fleet-1 agents/triage.md (+ our signal-specific `slo`)
ALLOWED_INTENT = {"reporter", "spec", "repo-data", "code-invariant", "baseline", "slo"}

SYSTEM = """You are the triager for an autonomous observability signal fleet.
You receive ONE production signal plus a CORRELATED evidence bundle (logs,
metrics, traces). You decide a disposition from the WHOLE picture, never a single
line. Correlation proves what happened; it cannot prove what was intended.

Dispositions:
- "dismiss": false alarm / already-recovered / no real ongoing defect. If a real
  signal is merely mis-tuned (noisy threshold), dismiss AND set
  immediate_recommendation.
- "file": a genuine, acceptance-statable defect. Produce an L1-candidate.
- "escalate": ambiguous, novel, high blast-radius, OR no citable intent source.

Intent gate (hard): on "file", EVERY acceptance criterion MUST carry an
"intent_source" from: reporter, spec, repo-data, code-invariant, baseline, slo.
"code-invariant" (e.g. a 5xx/crash must not happen) is an acceptance FLOOR, not
the whole acceptance. If you cannot cite intent for what "fixed" means, escalate.

work_type routing: "bug" (behavior/code defect -> dev fleet) or
"config-enhancement" (monitoring/infra config -> operator). A mis-tuned alert is
config-enhancement, never bug.

Return ONE JSON object, no prose, exactly this shape:
{"disposition":"dismiss|file|escalate","reason":"...",
 "immediate_recommendation":"... or null",
 "file":{"work_type":"bug|config-enhancement","title":"...","symptom":"...",
   "area":"...","evidence":["..."],
   "acceptance":[{"criterion":"...","intent_source":"reporter|spec|repo-data|code-invariant|baseline|slo"}]}
 }
On dismiss/escalate set "file" to null."""


def _trim(val, n=1800):
    s = val if isinstance(val, str) else json.dumps(val)
    return s[:n]


def build_user(signal, evidence):
    lines = [
        "SIGNAL:",
        json.dumps({k: signal[k] for k in ("source", "alertname", "labels", "summary")}, indent=2),
        "",
        "CORRELATED EVIDENCE (trimmed):",
    ]
    for name, val in evidence.get("queries", {}).items():
        lines.append(f"--- {name} ---")
        lines.append(_trim(val))
    return "\n".join(lines)


def _call(messages):
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
    """Extract + validate the disposition JSON (directAdapter-style)."""
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
    """Deterministic post-LLM gate. On file, count uncited/invalid acceptance
    criteria; any uncited -> downgrade to escalate. No LLM here (SIGNALS §4.1)."""
    if d.get("disposition") != "file":
        return d, "n/a"
    uncited = 0
    for c in d["file"]["acceptance"]:
        src = (c or {}).get("intent_source", "") if isinstance(c, dict) else ""
        if src not in ALLOWED_INTENT:
            uncited += 1
    if uncited:
        d["disposition"] = "escalate"
        d["reason"] = f"intent gate: {uncited} uncited acceptance criteria — " + d.get("reason", "")
        d["file"] = None
        return d, f"downgraded ({uncited} uncited)"
    return d, "passed"


def triage(signal, evidence, attempts=3):
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": build_user(signal, evidence)}]
    last_err = None
    for i in range(attempts):
        try:
            raw = _call(messages)
            d = _parse(raw)
            d, gate = _intent_gate(d)
            d["_meta"] = {"attempt": i + 1, "gate": gate,
                          "model": config.TRIAGE_MODEL, "prompt_ver": config.TRIAGE_PROMPT_VER}
            return d
        except Exception as e:  # noqa: BLE001 - retry on any parse/shape failure
            last_err = e
            print(f"  [triage] attempt {i+1} failed: {e}")
    # graceful degrade -> escalate (never a silent bad disposition)
    return {"disposition": "escalate", "reason": f"triager unparseable after {attempts}: {last_err}",
            "immediate_recommendation": None, "file": None,
            "_meta": {"attempt": attempts, "gate": "n/a", "degraded": True,
                      "model": config.TRIAGE_MODEL, "prompt_ver": config.TRIAGE_PROMPT_VER}}
