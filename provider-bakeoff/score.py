"""Scorers — exact-field match for JSON, LLM judge rubric for commit messages.

Both return a `Score` with a 0-1 primary score, optional dimension breakdown,
and a free-form note. The runner aggregates these across items per provider.

Design:
- JSON extraction: deterministic exact-field comparison (case-insensitive
  for strings, exact for numbers/bools/lists/null). LLM judge can be
  optionally used as a secondary "is this semantically equivalent" check
  on items that failed exact match — captured as `secondary_score`.
- Commit message: per-item criteria rubric (expected_type, must_mention,
  must_not_use, topic_hint, max_subject_length). Scored by an LLM judge
  returning a 0-1 against the rubric.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Score:
    """One item's score for one provider."""

    primary_score: float                          # 0-1; the main number
    primary_kind: str                             # "exact_field_match" | "llm_judge_rubric"
    secondary_score: Optional[float] = None       # LLM judge on JSON mismatches
    breakdown: Dict[str, Any] = field(default_factory=dict)
    note: str = ""


# ---------------------------------------------------------------------------
# JSON extraction — exact-field match (deterministic)


_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?|\n?```\s*$", re.MULTILINE)


def _strip_code_fences(text: str) -> str:
    """Strip triple-backtick fences if a model wrapped JSON in markdown."""
    return _CODE_FENCE_RE.sub("", text).strip()


def _normalize(v: Any) -> Any:
    """Normalize a value for comparison — case-fold strings; recurse into lists/dicts."""
    if isinstance(v, str):
        return v.strip().lower()
    if isinstance(v, list):
        return [_normalize(x) for x in v]
    if isinstance(v, dict):
        return {k.lower(): _normalize(val) for k, val in v.items()}
    return v


def _flatten(obj: Any, prefix: str = "") -> Dict[str, Any]:
    """Flatten a nested dict for field-by-field comparison."""
    out: Dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, (dict, list)):
                out[key] = v
            else:
                out[key] = v
    return out


def score_json_extraction(*, response_text: str, gold: Dict[str, Any]) -> Score:
    """Compare response JSON to the gold field-by-field.

    Returns a Score with `primary_score` = fraction of gold fields the
    response got right (case-insensitive for strings, exact for everything
    else). `breakdown` lists per-field hits / misses.
    """
    expected = gold["expected_json"]
    cleaned = _strip_code_fences(response_text)
    try:
        actual = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find a JSON object inside the text — some providers add prose.
        match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", cleaned, re.DOTALL)
        if not match:
            return Score(
                primary_score=0.0,
                primary_kind="exact_field_match",
                note="response was not valid JSON",
            )
        try:
            actual = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            return Score(
                primary_score=0.0,
                primary_kind="exact_field_match",
                note=f"JSON parse failed: {exc}",
            )

    expected_n = _normalize(expected)
    actual_n = _normalize(actual)

    hits = 0
    misses: Dict[str, Any] = {}
    if isinstance(expected_n, dict):
        total = len(expected_n)
        for key, exp_val in expected_n.items():
            act_val = actual_n.get(key) if isinstance(actual_n, dict) else None
            if act_val == exp_val:
                hits += 1
            else:
                misses[key] = {"expected": exp_val, "actual": act_val}
    else:
        total = 1
        hits = 1 if expected_n == actual_n else 0

    return Score(
        primary_score=hits / total if total else 0.0,
        primary_kind="exact_field_match",
        breakdown={
            "fields_total": total,
            "fields_hit": hits,
            "misses": misses,
        },
    )


# ---------------------------------------------------------------------------
# Commit message — LLM judge against a criteria rubric


JUDGE_SYSTEM = (
    "You evaluate commit messages against a per-item criteria rubric. "
    "Return STRICT JSON only: "
    '{"format_ok": <bool>, "accuracy": <int 1-5>, "specificity": <int 1-5>, '
    '"verdict": <"good"|"acceptable"|"bad">, "rationale": "<one sentence>"}.'
)


def _build_judge_prompt(*, candidate: str, criteria: Dict[str, Any]) -> str:
    parts = [
        f"Commit message to evaluate:\n  {candidate}",
        "",
        "Criteria:",
        f"  - Expected type prefix: {criteria.get('expected_type')}",
        f"  - Topic hint: {criteria.get('topic_hint')}",
        f"  - Subject must mention any of: {criteria.get('must_mention', [])}",
        f"  - Subject must NOT use vague terms: {criteria.get('must_not_use', [])}",
        f"  - Max subject length: {criteria.get('max_subject_length', 72)}",
        "",
        "Score:",
        "  - format_ok: true if the message starts with <type>(<scope>): or <type>:",
        "    where type matches the expected type, and the subject is under max length",
        "  - accuracy 1-5: how well the subject captures the actual change",
        "  - specificity 1-5: penalize vague terms; reward precise language",
        "  - verdict: good | acceptable | bad",
    ]
    return "\n".join(parts)


def score_commit_message(
    *,
    response_text: str,
    gold: Dict[str, Any],
    judge_callable,
) -> Score:
    """Score one commit-message candidate using an LLM judge.

    `judge_callable` is a function `(prompt, system) -> (text, cost_usd)` —
    the runner wires this up. Letting the runner inject the judge keeps
    this module decoupled from any specific provider.
    """
    candidate = response_text.strip().splitlines()[0] if response_text.strip() else ""
    criteria = gold["criteria"]

    judge_prompt = _build_judge_prompt(candidate=candidate, criteria=criteria)
    text, _cost = judge_callable(prompt=judge_prompt, system=JUDGE_SYSTEM)

    cleaned = _strip_code_fences(text)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        return Score(
            primary_score=0.0,
            primary_kind="llm_judge_rubric",
            note=f"judge returned non-JSON: {text[:80]}",
        )

    verdict_map = {"good": 1.0, "acceptable": 0.6, "bad": 0.0}
    verdict_score = verdict_map.get(payload.get("verdict", "bad"), 0.0)

    accuracy = int(payload.get("accuracy", 0))
    specificity = int(payload.get("specificity", 0))
    format_ok = bool(payload.get("format_ok", False))

    # Composite: 50% verdict, 25% accuracy (normalized), 15% specificity, 10% format.
    composite = (
        0.50 * verdict_score
        + 0.25 * (accuracy / 5.0)
        + 0.15 * (specificity / 5.0)
        + 0.10 * (1.0 if format_ok else 0.0)
    )

    return Score(
        primary_score=composite,
        primary_kind="llm_judge_rubric",
        breakdown={
            "candidate": candidate,
            "format_ok": format_ok,
            "accuracy": accuracy,
            "specificity": specificity,
            "verdict": payload.get("verdict"),
            "rationale": payload.get("rationale", ""),
        },
    )


# ---------------------------------------------------------------------------
# Routing


def score_item(
    *,
    task_name: str,
    response_text: str,
    gold: Dict[str, Any],
    judge_callable=None,
) -> Score:
    """Dispatch to the right scorer based on task name."""
    if task_name == "json-extraction":
        return score_json_extraction(response_text=response_text, gold=gold)
    if task_name == "commit-message":
        if judge_callable is None:
            return Score(
                primary_score=0.0,
                primary_kind="llm_judge_rubric",
                note="no judge configured — commit-message task needs an LLM judge",
            )
        return score_commit_message(
            response_text=response_text,
            gold=gold,
            judge_callable=judge_callable,
        )
    raise ValueError(f"unknown task: {task_name}")
