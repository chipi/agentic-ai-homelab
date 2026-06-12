"""Judge protocol + two implementations.

A judge takes a (run_id, item, dimensions) and returns a per-dimension
score on a 1-5 scale plus a USD cost. Two implementations ship:

- FakeJudge: deterministic, no API. Used for tests and the demo.
- LLMJudge:  Anthropic-shaped. Adapt for OpenAI / Gemini / local vLLM.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol


@dataclass
class ItemScore:
    """One judge's verdict on one item."""

    run_id: str
    item_id: str
    per_dimension: Dict[str, int] = field(default_factory=dict)  # dim → 1-5
    total_cost_usd: float = 0.0
    errors: List[str] = field(default_factory=list)


class Judge(Protocol):
    """A judge scores items along configured dimensions."""

    name: str

    def score(
        self,
        *,
        run_id: str,
        item_id: str,
        item_content: str,
        dimensions: List[str],
    ) -> ItemScore: ...


# ---------------------------------------------------------------------------


class FakeJudge:
    """Deterministic judge — no API. Returns a hashed score per (item, dim).

    Use for the demo and for unit tests of the harness's promotion /
    aggregation paths. Real judging happens via LLMJudge.
    """

    def __init__(self, name: str = "fake-judge"):
        self.name = name

    def score(
        self,
        *,
        run_id: str,
        item_id: str,
        item_content: str,
        dimensions: List[str],
    ) -> ItemScore:
        per_dim: Dict[str, int] = {}
        for dim in dimensions:
            # Deterministic 1-5 from a hash of (run_id, item_id, dim).
            # Bias slightly toward 3-4 to look like real ratings.
            key = f"{run_id}|{item_id}|{dim}".encode("utf-8")
            digest = hashlib.sha256(key).digest()
            per_dim[dim] = 2 + (digest[0] % 4)  # → 2, 3, 4, or 5
        return ItemScore(
            run_id=run_id,
            item_id=item_id,
            per_dimension=per_dim,
            total_cost_usd=0.0,
        )


# ---------------------------------------------------------------------------


class LLMJudge:
    """Anthropic-shaped judge.

    Prompts Claude for a per-dimension 1-5 score with a brief justification.
    Returns the score; the justification is logged but not used downstream
    (the aggregate score is the answer; rationale is for spot-checking).

    Adapt the `_build_prompt` and `_parse_response` methods for OpenAI /
    Gemini / local vLLM — the I/O shape stays the same.
    """

    SYSTEM = (
        "You are an evaluation judge. Score the candidate output on each "
        "requested dimension using a 1-5 scale (1 = poor, 5 = excellent). "
        "Return STRICT JSON only: {\"scores\": {\"<dim>\": <int>, ...}, "
        "\"rationale\": \"<one sentence>\"}. No prose outside the JSON."
    )

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.name = model
        self.model = model
        # Lazy-import so the demo (FakeJudge only) doesn't require the SDK.
        from anthropic import Anthropic

        self._client = Anthropic()

    def score(
        self,
        *,
        run_id: str,
        item_id: str,
        item_content: str,
        dimensions: List[str],
    ) -> ItemScore:
        prompt = self._build_prompt(item_content, dimensions)
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=512,
                system=[
                    {
                        "type": "text",
                        "text": self.SYSTEM,
                        # System prompt cached — it's stable across all items.
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            return ItemScore(
                run_id=run_id,
                item_id=item_id,
                errors=[f"api: {type(exc).__name__}: {exc}"],
            )

        per_dim, error = self._parse_response(response, dimensions)
        cost = self._estimate_cost(response)
        return ItemScore(
            run_id=run_id,
            item_id=item_id,
            per_dimension=per_dim,
            total_cost_usd=cost,
            errors=[error] if error else [],
        )

    @staticmethod
    def _build_prompt(item_content: str, dimensions: List[str]) -> str:
        dims_csv = ", ".join(dimensions)
        return (
            f"Dimensions to score: {dims_csv}\n\n"
            f"Candidate output:\n---\n{item_content}\n---"
        )

    @staticmethod
    def _parse_response(response, dimensions: List[str]):
        try:
            text = response.content[0].text
            payload = json.loads(text)
            scores = payload.get("scores") or {}
            per_dim = {d: int(scores[d]) for d in dimensions if d in scores}
            if not per_dim:
                return {}, "parse: no scores in response"
            return per_dim, None
        except (json.JSONDecodeError, KeyError, ValueError, IndexError) as exc:
            return {}, f"parse: {type(exc).__name__}: {exc}"

    @staticmethod
    def _estimate_cost(response) -> float:
        """Rough $ estimate from usage; replace with your project's pricing table."""
        u = response.usage
        # Default Sonnet pricing as of writing — update for current model.
        input_tok = (u.input_tokens or 0) + (
            getattr(u, "cache_creation_input_tokens", 0) or 0
        )
        cached_tok = getattr(u, "cache_read_input_tokens", 0) or 0
        output_tok = u.output_tokens or 0
        return (
            input_tok * 3e-6
            + cached_tok * 0.3e-6
            + output_tok * 15e-6
        )


def build_judge(name: Optional[str], *, use_fake: bool = False) -> Optional[Judge]:
    """Factory used by runner.py.

    `None` returns `None` (skip the cross-judge pass).
    `use_fake=True` returns a FakeJudge with the configured `name`.
    Otherwise returns an LLMJudge bound to that model.
    """
    if name is None:
        return None
    if use_fake or not os.environ.get("ANTHROPIC_API_KEY"):
        return FakeJudge(name=name)
    return LLMJudge(model=name)
