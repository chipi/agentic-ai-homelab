"""THE INTEGRATION SEAM. This is the file you edit; the rest is bookkeeping.

You already have a system — a summariser, a classifier, an extractor, a RAG
chain. This file is where you hand it to the harness. Two functions:

    call_system(text, params)  -> what your system produces, plus what it cost
    score(output, reference)   -> how good that output was

Everything else — freezing datasets, hashing, provenance, timing, aggregation,
the refusals — is generic and does not change.

`call_system` returns a `Result`, and the fields beyond `output` are optional.
Return what your system can tell you; the harness records whatever arrives and
skips what does not. Cost and token counts are the difference between "model B
is better" and "model B is better and costs 4x", which is usually the actual
decision.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


@dataclass
class Result:
    """What one call to your system produced, and what it cost."""

    output: str
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    cost_usd: Optional[float] = None
    latency_ms: Optional[float] = None
    extra: Dict[str, float] = field(default_factory=dict)


# ── 1. YOUR SYSTEM ───────────────────────────────────────────────────────────
def call_system(text: str, params: Dict[str, Any]) -> Result:
    """Run YOUR system over one item. Replace the body.

    `params` is whatever the experiment config put under `params:` — model name,
    temperature, prompt version, thresholds. Keep the knobs in the config, not
    in here, so an arm is a YAML file rather than a code edit.

    The default dispatches on `params["provider"]` so the bundled demo and the
    example adapters work out of the box:

        echo        no network, deterministic — proves the plumbing
        anthropic   Claude via the official SDK
        openai      anything OpenAI-compatible, including OpenRouter

    A real integration usually deletes all of this and calls one function:

        from myproject.summarise import summarise
        return Result(output=summarise(text, model=params["model"]))
    """
    provider = params.get("provider", "echo")
    fn: Callable[[str, Dict[str, Any]], Result] = PROVIDERS.get(provider, _echo)
    started = time.perf_counter()
    result = fn(text, params)
    if result.latency_ms is None:
        result.latency_ms = round((time.perf_counter() - started) * 1000, 3)
    return result


# ── 2. HOW GOOD WAS IT ───────────────────────────────────────────────────────
def score(output: str, reference: Optional[str]) -> Dict[str, float]:
    """Score one output. Replace with whatever "good" means for you.

    Called with the golden reference when one exists for the item, and with
    None when it does not — so the same adapter works before and after you have
    ground truth.

    The default is deliberately crude: token-overlap F1 against the reference,
    plus the output length. It is a placeholder that produces a real number so
    the loop runs end to end. Swap it for ROUGE, exact match, an embedding
    cosine, a rubric — whatever your domain actually rewards.

    Do not mistake the default for a metric you can defend in a decision.
    """
    out_len = float(len(output.split()))
    if reference is None:
        return {"output_words": out_len}
    a, b = set(output.lower().split()), set(reference.lower().split())
    if not a or not b:
        return {"output_words": out_len, "overlap_f1": 0.0}
    overlap = len(a & b)
    precision, recall = overlap / len(a), overlap / len(b)
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return {"output_words": out_len, "overlap_f1": round(f1, 6)}


# ── example adapters — delete the ones you do not use ────────────────────────
def _echo(text: str, params: Dict[str, Any]) -> Result:
    """No network. Returns the first N sentences — a stand-in 'summary'.

    Deterministic on purpose: `--repeat 3` on this provider reports spread
    0.000000, which is the reading you want to contrast against a real model.
    """
    n = int(params.get("sentences", 3))
    parts = [s.strip() for s in text.replace("\n", " ").split(".") if s.strip()]
    return Result(output=". ".join(parts[:n]) + ("." if parts else ""), cost_usd=0.0)


def _anthropic(text: str, params: Dict[str, Any]) -> Result:
    import anthropic  # imported lazily so the demo needs no SDK

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise SystemExit("ANTHROPIC_API_KEY is not set")
    client = anthropic.Anthropic(api_key=key)
    model = params.get("model", "claude-sonnet-4-6")
    msg = client.messages.create(
        model=model,
        max_tokens=int(params.get("max_tokens", 600)),
        temperature=float(params.get("temperature", 0.0)),
        messages=[{"role": "user", "content": params.get("prompt", "Summarise:") + "\n\n" + text}],
    )
    usage = getattr(msg, "usage", None)
    ti = getattr(usage, "input_tokens", None)
    to = getattr(usage, "output_tokens", None)
    return Result(
        output="".join(b.text for b in msg.content if getattr(b, "type", "") == "text"),
        tokens_in=ti,
        tokens_out=to,
        cost_usd=_price(params, ti, to),
    )


def _openai_compatible(text: str, params: Dict[str, Any]) -> Result:
    """OpenAI-shaped APIs, including OpenRouter — set `base_url` in params."""
    from openai import OpenAI  # lazy

    env_key = params.get("api_key_env", "OPENAI_API_KEY")
    key = os.environ.get(env_key)
    if not key:
        raise SystemExit(f"{env_key} is not set")
    client = OpenAI(api_key=key, base_url=params.get("base_url") or None)
    resp = client.chat.completions.create(
        model=params["model"],
        temperature=float(params.get("temperature", 0.0)),
        max_tokens=int(params.get("max_tokens", 600)),
        messages=[
            {"role": "user", "content": params.get("prompt", "Summarise:") + "\n\n" + text}
        ],
    )
    u = getattr(resp, "usage", None)
    ti = getattr(u, "prompt_tokens", None)
    to = getattr(u, "completion_tokens", None)
    return Result(
        output=resp.choices[0].message.content or "",
        tokens_in=ti,
        tokens_out=to,
        cost_usd=_price(params, ti, to),
    )


def _price(params: Dict[str, Any], tin: Optional[int], tout: Optional[int]) -> Optional[float]:
    """Cost from per-million-token prices declared in the config.

    Prices live in the experiment config, not in code, because they change and
    because a run should record the price it was costed at. A number computed
    from today's price list is not comparable to one computed from last
    quarter's without saying so.
    """
    pin, pout = params.get("usd_per_mtok_in"), params.get("usd_per_mtok_out")
    if pin is None or pout is None or tin is None or tout is None:
        return None
    return round(tin / 1e6 * float(pin) + tout / 1e6 * float(pout), 8)


PROVIDERS: Dict[str, Callable[[str, Dict[str, Any]], Result]] = {
    "echo": _echo,
    "anthropic": _anthropic,
    "openai": _openai_compatible,
    "openrouter": _openai_compatible,
}
