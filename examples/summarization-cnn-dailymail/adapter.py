"""ML vs LLM on CNN/DailyMail. The seam for this example.

An arm here is a YAML file naming a model. That is the whole point: when a model ships,
you add one config and get an answer instead of an impression.

    provider: hf_local   a summariser running on this machine.   cost 0. Needs torch.
    provider: litellm    a hosted model through the proxy.       cost > 0. Needs openai.

Neither import happens until an arm asks for it, so the LLM arms run without torch
installed and the local arm runs without a network.

WHAT THE SCORERS ARE FOR
  A facet earns its place only if it can point the OPPOSITE way to another one. Four here:

    rouge1          word coverage
    rouge2 / rougeL right words in the right ORDER. A summary using the right words in the
                    wrong order scores high rouge1 and low rouge2/L, and that gap is
                    extractive-vs-abstractive — invisible in any single number.
    compression     summary length / article length. Disagrees with ROUGE, which rises
                    with length: a verbose model wins ROUGE and fails the task.
    grounding       share of summary bigrams present in the article. This is the one ROUGE
                    cannot do. ROUGE cannot tell a good paraphrase from a confident
                    fabrication — both merely differ from the reference. Expect an LLM to
                    beat BART on ROUGE AND ground less: better and riskier at once, which
                    is the finding worth shipping this example for.

  grounding and compression are OURS, ~20 lines, so they are not comparable to anybody
  else's numbers. ROUGE is `rouge-score`, the implementation the papers use, so those are.
"""

from __future__ import annotations

import os
import random
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))


@dataclass
class Result:
    output: str
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    cost_usd: Optional[float] = None
    latency_ms: Optional[float] = None
    extra: Dict[str, float] = field(default_factory=dict)
    # Raw provider metadata, recorded verbatim and never averaged. Mirrors the field on
    # the harness's own Result -- this example defines its own copy of the dataclass so
    # it stands alone, and the two must stay in step.
    meta: Dict[str, Any] = field(default_factory=dict)



# ── the prompt, in one place ─────────────────────────────────────────────────
_PROMPT_CACHE: Dict[str, str] = {}


def _prompt(params: Dict[str, Any]) -> str:
    """The instruction every arm sends, read from ONE file.

    It used to be duplicated in `params.prompt` across every config — identical by
    generation, not by construction, so a single hand-edit would have made one arm
    incomparable with the other fifteen and nothing would have said so.

    `prompt_file` is resolved relative to this adapter, and its sha256 goes into the
    fingerprint: "every arm used the same prompt" becomes checkable rather than asserted,
    and a prompt change makes every run before and after distinguishable.

    An explicit `prompt:` still wins, so prompt research stays possible — but it is then a
    visible override recorded on the run, never an accident.
    """
    if params.get("prompt"):
        return str(params["prompt"])
    rel = str(params.get("prompt_file") or "prompt.txt")
    path = (Path(__file__).resolve().parent / rel).resolve()
    key = str(path)
    if key not in _PROMPT_CACHE:
        if not path.is_file():
            raise SystemExit(f"prompt file not found: {path}")
        _PROMPT_CACHE[key] = path.read_text(encoding="utf-8").strip()
    return _PROMPT_CACHE[key]


def _prompt_sha256(params: Dict[str, Any]) -> str:
    import hashlib  # noqa: PLC0415

    return hashlib.sha256(_prompt(params).encode()).hexdigest()

# ── the local model, loaded once ─────────────────────────────────────────────
#: Module-level so `warmup()` can pay the load cost OUTSIDE the timed loop. Left inside
#: it, ~1.6GB of weights amortise over the dataset and latency_ms would be measuring
#: dataset size rather than the model.
_PIPE: Any = None
_PIPE_KEY: Optional[tuple] = None


def _local_pipeline(params: Dict[str, Any]) -> Any:
    global _PIPE, _PIPE_KEY
    key = (params.get("model"), params.get("revision"), params.get("device"))
    if _PIPE is not None and _PIPE_KEY == key:
        return _PIPE
    from transformers import pipeline  # noqa: PLC0415 - only when an arm asks

    kwargs: Dict[str, Any] = {"model": params["model"]}
    if params.get("revision"):
        kwargs["revision"] = params["revision"]
    if params.get("device"):
        kwargs["device"] = params["device"]
    _PIPE = pipeline("summarization", **kwargs)
    _PIPE_KEY = key
    return _PIPE


def _hf_local(text: str, params: Dict[str, Any]) -> Result:
    pipe = _local_pipeline(params)
    # Truncation is the honest option and it is recorded: a 530-word article exceeds
    # BART's 1024-token window, and silently dropping the tail while reporting a ROUGE
    # score would be measuring the first half of the article.
    out = pipe(
        text,
        max_length=int(params.get("max_length", 128)),
        min_length=int(params.get("min_length", 32)),
        do_sample=False,
        truncation=True,
    )
    return Result(output=out[0]["summary_text"].strip(), cost_usd=0.0)


def _litellm(text: str, params: Dict[str, Any]) -> Result:
    from openai import OpenAI  # noqa: PLC0415

    base = (params.get("base_url") or os.environ.get("LITELLM_BASE_URL", "")).rstrip("/")
    if not base.startswith("http"):
        raise SystemExit("LITELLM_BASE_URL is not set — copy .env.example to .env")
    key_env = params.get("api_key_env", "LITELLM_API_KEY")
    key = os.environ.get(key_env)
    if not key:
        raise SystemExit(f"{key_env} is not set")
    client = OpenAI(api_key=key, base_url=f"{base}/v1")
    # Provider-specific knobs go through extra_body, because the OpenAI client rejects
    # anything it does not recognise. `reasoning` is the one that matters here: every arm
    # declares `reasoning: {enabled: false}`, and building the request from a fixed list of
    # fields DROPPED it — the configs said reasoning was off, the requests did not, and the
    # numbers would have been reported as measuring a non-reasoning model.
    extra_body: Dict[str, Any] = {}
    for passthrough in ("reasoning", "reasoning_effort"):
        if params.get(passthrough) is not None:
            extra_body[passthrough] = params[passthrough]
    # WHICH MACHINE RAN IT. For an open-weight model the host is part of the system under
    # test -- two providers can serve the same weights at different quantisations, and a
    # gateway load-balances between them without telling you. `provider_routing` is the
    # policy we ASK for; the provider we actually GOT is recorded per call below. The key
    # is not called `provider` because that name is already taken by this adapter's own
    # backend selector (litellm / hf_local).
    if params.get("provider_routing") is not None:
        extra_body["provider"] = params["provider_routing"]
    resp = client.chat.completions.create(
        model=params["model"],
        temperature=float(params.get("temperature", 0.0)),
        max_tokens=int(params.get("max_tokens", 200)),
        messages=[{"role": "user", "content": _prompt(params) + "\n\n" + text}],
        **({"extra_body": extra_body} if extra_body else {}),
    )
    usage = getattr(resp, "usage", None)
    ti = getattr(usage, "prompt_tokens", None)
    to = getattr(usage, "completion_tokens", None)
    max_tokens = int(params.get("max_tokens", 200))
    # DID THE MODEL RUN OUT OF ROOM? A truncated summary's ROUGE is not a measurement of
    # the model, it is a measurement of the ceiling — and nothing in this harness noticed.
    #
    # It showed up as a fake finding. Reasoning models emit thinking tokens INSIDE the
    # output budget: at max_tokens=200, qwen-flash spent ~194 tokens and produced 12 words
    # (15.9 tokens/word, against ~1.4 for a non-reasoning model), so its summary was cut
    # off and it scored half of everyone else. That read as "this model is bad" and was
    # "my cap was too low". finish_reason is the provider telling us directly.
    finish = getattr(resp.choices[0], "finish_reason", None)
    truncated = finish == "length" or (to is not None and to >= max_tokens * 0.98)

    # WERE REASONING TOKENS BILLED? Every arm declares `reasoning: {enabled: false}`, and
    # for most providers that holds. It did not hold everywhere: a 24-arm sweep showed two
    # arms billing 2.2 output tokens per visible word against a field at 1.3, with nothing
    # visible in the text to explain it -- hidden thinking, charged for, invisible. The
    # comparison claimed to hold reasoning constant and did not.
    #
    # The provider reports this directly in usage.completion_tokens_details, so it is a
    # METRIC, not a forensic detail: it belongs in the table where a contaminated arm is
    # obvious, rather than in a file somebody has to think to open.
    reasoning_tokens = _reasoning_tokens(usage)

    return Result(
        output=(resp.choices[0].message.content or "").strip(),
        tokens_in=ti,
        tokens_out=to,
        cost_usd=_price(params, ti, to),
        # `reasoning_tokens` is recorded ONLY when the provider actually reported it.
        # Writing 0.0 for an unreported value would state "this arm billed no reasoning
        # tokens" on no evidence -- the leaderboard would print a measured zero where the
        # truth is that we do not know. An absent metric prints as "--", which is correct.
        extra={
            "truncated": 1.0 if truncated else 0.0,
            **({"reasoning_tokens": float(reasoning_tokens)}
               if reasoning_tokens is not None else {}),
        },
        # Kept verbatim so a later question can be answered without re-running: the whole
        # usage object, why generation stopped, and the model string the PROVIDER reports
        # -- which is the upstream model, not the proxy alias we asked for.
        meta={
            "usage": _as_dict(usage),
            "finish_reason": finish,
            "response_model": getattr(resp, "model", None),
            "system_fingerprint": getattr(resp, "system_fingerprint", None),
            # Distinguishes "provider said zero" from "provider said nothing", which the
            # numeric metric above cannot express once it is a float.
            "reasoning_tokens_reported": reasoning_tokens is not None,
            # Non-standard field; the OpenAI SDK keeps it in model_extra. This is the only
            # way to learn which host actually served the request -- the proxy rewrites
            # `model` to our own alias, so the response otherwise says nothing about it.
            "provider": (
                getattr(resp, "provider", None)
                or (getattr(resp, "model_extra", None) or {}).get("provider")
            ),
        },
    )


def _as_dict(obj: Any) -> Any:
    """Best-effort plain-data view of a provider SDK object, for the run record.

    SDKs disagree: pydantic models, dataclasses, plain dicts. None of them are worth a
    hard dependency, and a failure here must never lose the run -- so this degrades to
    a string rather than raising.
    """
    if obj is None:
        return None
    for attr in ("model_dump", "to_dict", "dict"):
        fn = getattr(obj, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception:  # noqa: BLE001 -- forensics must not break a paid run
                pass
    if isinstance(obj, dict):
        return obj
    try:
        return dict(vars(obj))
    except Exception:  # noqa: BLE001
        return str(obj)


def _reasoning_tokens(usage: Any) -> Optional[int]:
    """Reasoning/thinking tokens billed for this call, or None if unreported.

    None and 0 are different claims. 0 means the provider told us there were none;
    None means it said nothing, and an arm whose reasoning status is UNKNOWN must not
    be presented as an arm with reasoning off.
    """
    d = _as_dict(usage)
    if not isinstance(d, dict):
        return None
    details = d.get("completion_tokens_details") or d.get("output_tokens_details") or {}
    if not isinstance(details, dict):
        details = _as_dict(details) if details else {}
    if isinstance(details, dict):
        for k in ("reasoning_tokens", "reasoning", "thinking_tokens"):
            if isinstance(details.get(k), int):
                return details[k]
    return None


def _price(params: Dict[str, Any], tin: Optional[int], tout: Optional[int]) -> Optional[float]:
    """Cost from prices declared in the config, or None when they are not.

    None means UNPRICED, and the leaderboard prints it as unknown. A local arm must report
    0.0 instead — a measured zero is a claim ("this is free"), a missing value is not.
    """
    pin, pout = params.get("usd_per_mtok_in"), params.get("usd_per_mtok_out")
    if pin is None or pout is None or tin is None or tout is None:
        return None
    return round(tin / 1e6 * float(pin) + tout / 1e6 * float(pout), 8)


PROVIDERS = {"hf_local": _hf_local, "litellm": _litellm}







def call_system(text: str, params: Dict[str, Any]) -> Result:
    provider = params.get("provider", "litellm")
    fn = PROVIDERS.get(provider)
    if fn is None:
        raise SystemExit(f"unknown provider {provider!r} — expected one of {sorted(PROVIDERS)}")
    started = time.perf_counter()
    result = fn(text, params)
    if result.latency_ms is None:
        result.latency_ms = round((time.perf_counter() - started) * 1000, 3)
    return result


# ── warm-up ──────────────────────────────────────────────────────────────────
def warmup(params: Dict[str, Any]) -> None:
    """Load weights / prove the endpoint answers, before anything is timed or paid for.

    A local arm loads ~1.6GB here so the timed loop measures inference. A hosted arm sends
    ONE tiny request: a bad key should fail now, not on item 34 of 50 after 33 were paid
    for. That request costs a fraction of a cent and counts toward EVAL_MAX_COST_USD like
    any other, because a cap that ignores a real call is not a cap.
    """
    provider = params.get("provider", "litellm")
    if provider == "hf_local":
        _local_pipeline(params)
    else:
        _litellm("Warm up.", {**params, "max_tokens": 1})


# ── fingerprint ──────────────────────────────────────────────────────────────
_UPSTREAM_CACHE: Dict[str, Optional[str]] = {}


def _resolve_upstream(alias: Optional[str]) -> Optional[str]:
    """Ask the proxy what upstream model an alias points at, or None if it cannot say.

    One HTTP call per process, cached. Returning None is a legitimate answer and is
    recorded as such -- a proxy that is down must not cause the run to claim an identity
    it did not verify, and must not kill a paid sweep either.
    """
    if not alias:
        return None
    if alias in _UPSTREAM_CACHE:
        return _UPSTREAM_CACHE[alias]
    resolved: Optional[str] = None
    base = (os.environ.get("LITELLM_BASE_URL") or "").rstrip("/")
    key = os.environ.get("LITELLM_API_KEY")
    if base.startswith("http") and key:
        import json as _json  # noqa: PLC0415
        import urllib.request  # noqa: PLC0415

        try:
            req = urllib.request.Request(
                base + "/model/info", headers={"Authorization": "Bearer " + key}
            )
            with urllib.request.urlopen(req, timeout=15) as fh:
                for entry in (_json.load(fh).get("data") or []):
                    if entry.get("model_name") == alias:
                        resolved = (entry.get("litellm_params") or {}).get("model")
                        break
        except Exception:  # noqa: BLE001 -- provenance is best-effort, the run is not
            resolved = None
    _UPSTREAM_CACHE[alias] = resolved
    return resolved


def fingerprint(params: Dict[str, Any]) -> Dict[str, Any]:
    """What this arm's system under test IS. The core asks; it does not inspect.

    Local: resolved from the HF cache, so the record says which weights actually loaded
    rather than which were requested. Hosted: the proxy's model string, which is all a
    caller can honestly claim — the provider does not expose a weight revision, so
    `revision_source` says "api-model-string" and does not pretend otherwise.
    """
    if params.get("provider") == "hf_local":
        from hf_identity import hf_model_fingerprint  # noqa: PLC0415

        return hf_model_fingerprint(
            params["model"],
            revision=params.get("revision"),
            device=str(params.get("device", "cpu")),
            precision=str(params.get("precision", "fp32")),
        )
    # RESOLVE THE ALIAS. `params["model"]` is a name WE invented on our own proxy
    # ("eval-opus-5"). Recording it as the system under test meant the fingerprint stayed
    # byte-identical if the alias were re-pointed at a different upstream model -- the
    # experiment could change completely and every provenance check would still pass.
    # That is the exact failure a fingerprint exists to prevent, so the upstream id is
    # resolved from the proxy and recorded as the identity; the alias is kept beside it
    # because it is what the config asked for.
    alias = params.get("model")
    upstream = _resolve_upstream(alias)
    return {
        "id": upstream or alias,
        "alias": alias,
        # Never let an unresolved alias masquerade as a resolved identity: a reader must
        # be able to tell "this IS the upstream model" from "this is only what we asked
        # for and the proxy did not answer".
        "id_source": "proxy-model-info" if upstream else "alias-unresolved",
        "revision": None,
        "revision_source": "api-model-string",
        "endpoint": os.environ.get("LITELLM_BASE_URL"),
        # The routing POLICY, which is knowable before the run and therefore belongs in
        # the fingerprint. Which provider actually answered is only knowable afterwards,
        # so it is recorded in the run as `providers_seen` instead -- asking for a thing
        # and getting it are two different facts and the record keeps them apart.
        "provider_routing": params.get("provider_routing"),
        "temperature": params.get("temperature"),
        # The instruction is part of the system under test. Two arms given different
        # prompts are not comparable, and run-compare marks a differing hash as a confound
        # exactly as it does a differing host.
        "prompt_sha256": _prompt_sha256(params),
        # Part of the system under test: the same model with reasoning on and off is two
        # different systems, and a run must say which one produced its numbers.
        "reasoning": params.get("reasoning"),
    }


# ── the scorers ──────────────────────────────────────────────────────────────
_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> List[str]:
    return _WORD.findall(text.lower())


def _bigrams(tokens: List[str]) -> set:
    return set(zip(tokens, tokens[1:]))


def _grounding(summary: str, source: str) -> Optional[float]:
    """Share of the summary's bigrams that appear in the source.

    High = extractive, and safe. Low = abstractive, which is either a good paraphrase or a
    fabrication — this cannot tell those apart either, but it CAN tell you the model left
    the source behind, which ROUGE cannot. Read it beside ROUGE, never instead of it.
    """
    sb, ab = _bigrams(_tokens(summary)), _bigrams(_tokens(source))
    if not sb:
        return None
    return len(sb & ab) / len(sb)



# ── format compliance ────────────────────────────────────────────────────────
# The prompt says "Output only the summary." Whether a model OBEYED that is not a
# ROUGE question, and it is not something to check by reading a few outputs: five were
# read on one article and declared clean, and a scan of all 1440 found 65 contaminated
# -- including four where the model wrote its reasoning out in the open ("The user wants
# a 2-3 sentence news wire style summary... Let me draft:") and scored 0.10 for it.
#
# So it is COMPUTED, on every output, as a metric. Three flags rather than one score,
# because they are three different failures with three different meanings:
#   narration  the model thought out loud instead of answering -- the output is not a
#              summary at all, and its quality numbers describe something else
#   label      "**Wire Summary:**" and friends -- disobedient but harmless, ~0.001 ROUGE
#   bullets    list formatting where prose was asked for
_COT = re.compile(
    r"\b(the user (wants|is asking|asked)|let me (draft|think|write|check)|"
    r"i (need|should|will) (to )?(draft|write|summar|check)|okay,? (so|let)|"
    r"first,? i|that'?s (three|two) sentences|wait,?|hmm,?|let'?s (see|draft)|"
    r"<think>|</think>|analysis:|draft:|final( answer| summary)?:)",
    re.I,
)
_LABEL = re.compile(r"^\s*(\*\*|##|#\s)?\s*(wire |news )?summary\s*[:\-]|^\s*\*\*", re.I)
_BULLET = re.compile(r"^\s*[-*\u2022]\s", re.M)


def _format_flags(output: str) -> Dict[str, float]:
    """1.0 = this output broke the format contract in that way, 0.0 = it did not."""
    return {
        "fmt_narration": 1.0 if _COT.search(output) else 0.0,
        "fmt_label": 1.0 if _LABEL.match(output) else 0.0,
        "fmt_bullets": 1.0 if _BULLET.search(output) else 0.0,
    }



def _clip_words(text: str, budget: int) -> str:
    """First `budget` whitespace-delimited words, keeping the whitespace between them.

    Naive `" ".join(text.split()[:n])` loses newlines, and newlines are what rougeLsum
    uses to find sentences.
    """
    if budget <= 0:
        return ""
    kept, count, i = [], 0, 0
    for token in re.split(r"(\s+)", text):
        if token and not token.isspace():
            if count == budget:
                break
            count += 1
        kept.append(token)
        i += 1
    return "".join(kept).strip()


def score(output: str, reference: Optional[str], source: Optional[str] = None) -> Dict[str, float]:
    """ROUGE against the gold summary, plus the facets ROUGE cannot see."""
    out: Dict[str, float] = {"summary_words": float(len(output.split()))}
    # Format compliance does not need a reference -- it is a property of the output
    # alone -- so it is computed before the early return, and an arm scored without
    # ground truth still reports whether it obeyed the prompt.
    out.update(_format_flags(output))
    if reference is None:
        return out

    from rouge_score import rouge_scorer  # noqa: PLC0415

    # rougeLsum, not rougeL. rougeL takes the longest common subsequence over the whole
    # text as one string, so it penalises a model for ordering the same facts across
    # sentences differently; rougeLsum does it per sentence. These outputs are 2-3
    # sentences, and rougeLsum is what the CNN/DailyMail literature reports -- using
    # rougeL made our numbers non-comparable to every published figure for no benefit.
    #
    # rouge2 is gone: it correlated at 0.83 with the LCS metric across 24 arms, so it
    # never disagreed with it. A facet that always agrees is not a facet.
    # split_summaries=True IS THE WHOLE POINT, and without it the rename was cosmetic.
    # rouge_score splits for rougeLsum on "\n" ONLY. Our gold references contain no
    # newlines, so rougeLsum was byte-identical to rougeL on 1435 of 1440 outputs -- the
    # metric advertised in this file as "the CNN/DailyMail convention" was plain rougeL
    # wearing its name. Sentence-level LCS never ran once.
    #
    # Measured on a reordered-sentence pair: rougeL 0.6000 / rougeLsum 0.6000 without the
    # flag, 0.6000 / 1.0000 with it.
    scorer = rouge_scorer.RougeScorer(
        ["rouge1", "rougeLsum"], use_stemmer=True, split_summaries=True
    )
    scores = scorer.score(reference, output)
    for name, value in scores.items():
        # 10 decimals, not 6. These are ratios of small integers, so two arms that
        # genuinely tie on an item can differ by ~1e-7 after 6-decimal rounding and get
        # strictly ordered by the significance test -- inventing a difference the data
        # does not contain. Storage is free; the precision is not recoverable later.
        out[name] = round(value.fmeasure, 10)
    out["reference_words"] = float(len(reference.split()))

    # ── the two facets that are meant to disagree ────────────────────────────
    # F1 against a single reference is a LENGTH ranking wearing a quality costume:
    # across 24 arms, rho(words, precision) = -0.845 and rho(words, recall) = +0.795.
    # Picking recall over F1 does not remove the bias, it flips it. So measure both
    # ends deliberately, and control the one that can be controlled.
    #
    # COVERAGE: recall, with the output cut to the REFERENCE's own length. Every arm is
    # judged on the same budget the human used, so writing more cannot buy coverage --
    # it can only buy it by putting the important thing first. Truncating to the
    # per-item reference length rather than a fixed constant keeps this correct on any
    # dataset, including one whose references vary in length.
    ref_words = reference.split()
    budget = len(ref_words)
    # Clip on WORDS but rejoin on the original whitespace, so sentence structure survives
    # into the scorer. The previous " ".join(...) flattened every newline, which meant
    # rougeLsum's sentence splitting could not run on the clipped text even once the
    # split_summaries flag was set. Clipping mid-sentence is fine -- union-LCS handles a
    # partial trailing sentence -- but silently turning the text into one line is not.
    clipped = _clip_words(output, budget) if budget else output
    out["coverage"] = round(scorer.score(reference, clipped)["rougeLsum"].recall, 10)
    # CONCISION: precision over the WHOLE output -- what share of what the model wrote
    # earned its place. Padding is punished here exactly as it is rewarded in raw recall.
    out["concision"] = round(scores["rougeLsum"].precision, 10)
    # Length ratio against the REFERENCE: 1.0 means the model wrote as much as the human
    # did. ROUGE rises with length, so this is how a verbose winner gets caught.
    if reference.split():
        out["length_vs_reference"] = round(len(output.split()) / len(reference.split()), 6)
    if source:
        grounded = _grounding(output, source)
        if grounded is not None:
            out["grounding"] = round(grounded, 10)
        if source.split():
            out["compression"] = round(len(output.split()) / len(source.split()), 6)
    return out

#: What THIS adapter's metrics mean. The core classifies the ones it ships; an example
#: brings its own vocabulary and must say which are quality and which merely describe the
#: output. Without it the leaderboard ranked a ten-model sweep by `compression` — a length
#: ratio — and its own "that is a descriptive metric" warning stayed silent, because by the
#: core's tuples compression looked like quality.
#: The headline facet. Coverage, not concision: the question this example exists to ask
#: is "did the summary carry the story", and the terseness half is the counterweight you
#: read beside it -- not the thing that decides the ranking. Sorting alphabetically made
#: `concision` the default and put the shortest arms on top.
#: Extra failure shapes worth retrying for THIS adapter, on top of the core's list.
#: The core owns the universal ones (429, 503, "rate limit"); an adapter adds only what
#: is peculiar to its own backends. Retrying itself is the harness's job -- this example
#: carried its own copy for exactly one afternoon, which is one afternoon too long for
#: infrastructure every adapter needs.
TRANSIENT_MARKERS = ("model is warming up", "no instances available", "upstream")

PRIMARY_METRIC = "coverage"

METRIC_KINDS = {
    # The two that are built to disagree: coverage rewards saying the important thing,
    # concision rewards not saying anything else. No arm maxes both, and which one you
    # care about is a product decision the eval must not make for you.
    "coverage": "quality",
    "concision": "quality",
    # Literature-comparable F1s. Kept so our numbers can be placed beside published
    # CNN/DailyMail results -- but both are length-sensitive, so they are read after
    # coverage/concision, not instead of them.
    "rouge1": "quality",
    "rougeLsum": "quality",
    "grounding": "quality",
    # Descriptive: they say what the output WAS, not whether it was good. Ranking by any of
    # them puts the most verbose arm on top.
    "compression": "descriptive",
    "length_vs_reference": "descriptive",
    "summary_words": "descriptive",
    "reference_words": "descriptive",
    # Not quality and not cost: a diagnostic. Any arm with truncated > 0 has scores that
    # describe the token ceiling rather than the model, and its row should not be read.
    "truncated": "descriptive",
    # Same category, same reason: an arm billing reasoning tokens was not held to the
    # reasoning-off condition the other arms were, so it is not comparable to them --
    # whatever its quality column says.
    "reasoning_tokens": "descriptive",
    # Format compliance. Descriptive because they describe the output rather than rank it
    # -- but fmt_narration > 0 means some of that arm's outputs are not summaries, so its
    # quality column is partly measuring something else. Read it before the ranking.
    "fmt_narration": "descriptive",
    "fmt_label": "descriptive",
    "fmt_bullets": "descriptive",
}
