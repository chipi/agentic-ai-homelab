"""What a number depended on, captured so "we varied one thing" can be checked.

An eval measures three things — the SYSTEM UNDER TEST, the INSTRUMENT (the adapter: its
`call_system` and its `score`) and the DATA (dataset + reference). A number is only
interpretable if all three are identified, and a COMPARISON is only valid if exactly one
of them moved. Without a fingerprint that is an assertion; with one it is checkable.

STDLIB ONLY, deliberately. This module must never import torch, transformers,
scikit-learn or any provider SDK. Someone evaluating a pure-LLM system, or a regex
baseline, should never install an ML framework to use this harness — the experiment
brings its own weight, and the core only knows how to ASK.

Which is why the model half is inverted: the core defines a VOCABULARY, not a mechanism.
An adapter may expose

    def fingerprint(params) -> dict

and return whatever identifies ITS system, in this shape:

    {"id": ..., "revision": ..., "revision_source": ..., "device": ..., "precision": ...}

`revision_source` is never parsed here — it exists for whoever reads the run later, and
says HOW the revision was determined: "hf-snapshot", "ollama-digest", "gguf-sha256",
"sklearn-artifact", "api-model-string". A HuggingFace cache layout is a HuggingFace
concept and has no business in this file.

A missing revision is recorded as missing. The core does not invent one — two runs of
"the same model" that cannot prove they used the same weights should say so rather than
imply a reproducibility they do not have.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, Optional

#: Reported when installed, WITHOUT importing them. importlib.metadata reads distribution
#: metadata off disk, so the core can say "torch 2.2.2" while having no torch dependency
#: and never loading it into the process. That distinction is the whole point of this file.
_WATCHED_DISTRIBUTIONS = (
    "torch",
    "transformers",
    "scikit-learn",
    "sentence-transformers",
    "numpy",
    "openai",
    "anthropic",
    "datasets",
    "rouge-score",
)


def _installed_versions() -> Dict[str, str]:
    """Versions of anything watched that is installed. No imports of the packages."""
    from importlib.metadata import PackageNotFoundError, version  # stdlib

    out: Dict[str, str] = {}
    for dist in _WATCHED_DISTRIBUTIONS:
        try:
            out[dist] = version(dist)
        except PackageNotFoundError:
            continue
    return out


def _git(root: Path, *args: str) -> Optional[str]:
    """A git command's stdout, or None when git/repo is absent. Never raises."""
    try:
        r = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def _harness_identity(root: Path) -> Dict[str, Any]:
    """The INSTRUMENT: this harness's own code state."""
    commit = _git(root, "rev-parse", "--short=12", "HEAD")
    status = _git(root, "status", "--porcelain")
    return {
        "commit": commit,
        # A dirty tree is not a version. Recorded rather than only refused, so a number
        # produced from one carries the caveat instead of implying reproducibility.
        "dirty": bool(status) if status is not None else None,
    }


def sha256_file(path: Path) -> Optional[str]:
    """Content hash of one file, or None if unreadable."""
    try:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _adapter_identity(adapter_path: Optional[Path], adapter_id: str) -> Dict[str, Any]:
    """The INSTRUMENT's scoring half, by CONTENT rather than by path.

    A path is not an identity: the adapter holds `score()`, so editing it changes what
    every number means, and a run that recorded only `examples/x/adapter.py` would still
    claim a scorer that no longer exists as it was. A git commit would not catch an
    uncommitted edit either. The file's sha256 does.
    """
    return {
        "id": adapter_id,
        "sha256": sha256_file(adapter_path) if adapter_path else None,
    }


def _host_identity() -> Dict[str, Any]:
    """The machine. Wall-clock is machine-dependent, which makes the machine part of
    what a latency number MEANS — so it is recorded, not assumed.

    `label` is overridable because the auto-detected string cannot tell two Macs apart
    and the operator can: EVAL_HOST_LABEL=m4pro / mini-intel / dgx.
    """
    uname = platform.uname()
    return {
        "label": os.environ.get("EVAL_HOST_LABEL") or None,
        "platform": f"{uname.system}/{uname.machine}",
        "release": uname.release,
        "processor": platform.processor() or None,
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
    }


def _model_identity(hook: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]],
                    params: Dict[str, Any]) -> Dict[str, Any]:
    """Whatever the adapter says identifies its system under test.

    Absent hook -> `{"identity_declared": False}`. That is honest: an echo arm has no model,
    and a
    fingerprint claiming otherwise would be worse than one admitting the gap.

    A hook that raises is caught. Fingerprinting must never be the reason a run fails —
    it is a description of the run, not a precondition for it.
    """
    if hook is None:
        return {"identity_declared": False}
    try:
        declared = hook(params) or {}
    except Exception as exc:  # noqa: BLE001 - a broken hook must not kill the run
        return {"identity_declared": False, "error": f"{type(exc).__name__}: {exc}"}
    if not isinstance(declared, dict):
        return {"identity_declared": False, "error": "fingerprint() did not return a dict"}
    # `identity_declared` is a FLAG -- did the adapter tell us what its system under
    # test is -- not the identity itself. It was called `declared`, which reads like it
    # holds a value, and it was identical across 24 different models because it means
    # "yes". The identity lives in the keys the adapter returns, beside it.
    out: Dict[str, Any] = {"identity_declared": True, **declared}
    # Say the quiet part: no revision means no proof two runs used the same weights.
    if not declared.get("revision"):
        out.setdefault("revision", None)
        out.setdefault("revision_source", "unavailable")
    return out


def build_fingerprint(
    *,
    root: Path,
    dataset: Dict[str, Any],
    reference_id: Optional[str],
    reference_tier: Optional[str],
    config_id: str,
    params: Dict[str, Any],
    adapter_id: str,
    adapter_path: Optional[Path],
    model_hook: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """The full fingerprint, plus one hash over all of it.

    The hash is the point: comparing two runs field by field is work nobody does, and a
    single differing hash answers "did anything else move?" at a glance. If it matches,
    you varied one thing. If it does not, you have not run the experiment you think you
    have — and the fields say which part drifted.
    """
    fp: Dict[str, Any] = {
        "version": 1,
        "instrument": {
            "harness": _harness_identity(root),
            "adapter": _adapter_identity(adapter_path, adapter_id),
        },
        "system_under_test": {
            "model": _model_identity(model_hook, params),
            "libraries": _installed_versions(),
        },
        "data": {
            "dataset_id": dataset.get("dataset_id"),
            # The item hashes ARE the dataset's identity — dataset_id is a name, and a
            # name can be reused over different bytes.
            "items_sha256": _items_digest(dataset),
            "n_items": len(dataset.get("items") or []),
            "reference_id": reference_id,
            "reference_tier": reference_tier,
        },
        "host": _host_identity(),
        "arm": {"config_id": config_id, "params": dict(params or {})},
    }
    fp["hash"] = _hash_of(fp)
    return fp


def _items_digest(dataset: Dict[str, Any]) -> Optional[str]:
    """One hash over every item's frozen sha256, in item order."""
    items = dataset.get("items") or []
    if not items:
        return None
    h = hashlib.sha256()
    for item in items:
        h.update(str(item.get("item_id", "")).encode())
        h.update(str(item.get("source_sha256", "")).encode())
    return h.hexdigest()


def _hash_of(fingerprint: Dict[str, Any]) -> str:
    """SHA256 over the fingerprint, minus the hash field itself.

    sort_keys so field order cannot change the answer; default=str so an unexpected type
    from an adapter's hook degrades to a stable string instead of raising.
    """
    body = {k: v for k, v in fingerprint.items() if k != "hash"}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, default=str).encode()
    ).hexdigest()


def differing_paths(a: Dict[str, Any], b: Dict[str, Any], _prefix: str = "") -> list[str]:
    """Dotted paths where two fingerprints disagree — what `run-compare` should name.

    "The hashes differ" is true and useless. "system_under_test.model.revision differs"
    tells you whether you compared two models or two machines.
    """
    out: list[str] = []
    for key in sorted(set(a) | set(b)):
        if key == "hash":
            continue
        av, bv = a.get(key), b.get(key)
        path = f"{_prefix}{key}"
        if isinstance(av, dict) and isinstance(bv, dict):
            out.extend(differing_paths(av, bv, f"{path}."))
        elif av != bv:
            out.append(path)
    return out
