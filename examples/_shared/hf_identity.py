"""Identify a HuggingFace model exactly, for an adapter's `fingerprint()` hook.

OPTIONAL AND OUT OF THE CORE. `scripts/_fingerprint.py` defines a vocabulary — id,
revision, revision_source — and never learns what a HuggingFace cache looks like. A
HuggingFace layout is a HuggingFace concept; an Ollama adapter brings its own helper and
imports nothing from here.

It lives in examples/_shared/ so the second HF-using adapter does not reinvent snapshot
resolution, and so the core still cannot reach it.

WHY THE SNAPSHOT PATH IS THE ANSWER
  The cache stores a revision at `models--org--name/snapshots/<revision-sha>/`. The
  directory name IS the content identity, so identifying exactly which weights loaded
  costs nothing — no hashing 1.6GB on every run.

  That distinction is not academic. A pinned revision that is not cached can fall back to
  a different cached one, and the pin then describes what you ASKED for while the snapshot
  describes what you GOT. Those differed silently in a sibling project this week. The pin
  belongs in the config; the resolved snapshot belongs in the fingerprint.

The heavier tiers are opt-in because the cheap one catches the failure that actually
happens:

    default                      resolved revision            free
    EVAL_FINGERPRINT_WEIGHTS=1   sha256 of the weight files   minutes
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Dict, Optional

#: Mirrors huggingface_hub's default. Read rather than imported, so this helper works
#: without huggingface_hub installed.
def _hub_cache() -> Path:
    for var in ("HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE"):
        if os.environ.get(var):
            return Path(os.environ[var]).expanduser()
    if os.environ.get("HF_HOME"):
        return Path(os.environ["HF_HOME"]).expanduser() / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def _repo_dir(model_id: str) -> Path:
    return _hub_cache() / f"models--{model_id.replace('/', '--')}"


def resolved_revision(model_id: str, revision: Optional[str] = None) -> Optional[str]:
    """The revision actually on disk for `model_id`.

    With `revision` given, confirms that exact snapshot exists and returns it — so a
    fingerprint records a pin only when the pin is really what is there.

    Without one, returns the single cached snapshot when there is exactly one. With
    several it returns None rather than guessing: two snapshots and no stated pin means
    the loader chooses, and a fingerprint must not pretend to know which.
    """
    snapshots = _repo_dir(model_id) / "snapshots"
    if not snapshots.is_dir():
        return None
    present = sorted(p.name for p in snapshots.iterdir() if p.is_dir())
    if revision:
        return revision if revision in present else None
    return present[0] if len(present) == 1 else None


def weight_files(model_id: str, revision: str) -> list[Path]:
    """The weight files in a resolved snapshot, safetensors preferred."""
    snap = _repo_dir(model_id) / "snapshots" / revision
    if not snap.is_dir():
        return []
    safes = sorted(snap.glob("*.safetensors"))
    return safes or sorted(snap.glob("*.bin"))


def _weights_sha256(files: list[Path]) -> Optional[str]:
    """One hash over the weight files, in name order. Minutes, hence opt-in."""
    if not files:
        return None
    h = hashlib.sha256()
    for f in sorted(files, key=lambda p: p.name):
        h.update(f.name.encode())
        try:
            with f.open("rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 22), b""):
                    h.update(chunk)
        except OSError:
            return None
    return h.hexdigest()


def hf_model_fingerprint(
    model_id: str,
    *,
    revision: Optional[str] = None,
    device: Optional[str] = None,
    precision: Optional[str] = None,
) -> Dict[str, Any]:
    """The dict an adapter's `fingerprint()` should return for an HF model.

    `revision_source` says how the revision was determined, for whoever reads the run:
    "hf-snapshot" when resolved from the cache, "unavailable" when it could not be — which
    is recorded as such rather than filled in with something plausible.
    """
    resolved = resolved_revision(model_id, revision)
    out: Dict[str, Any] = {
        "id": model_id,
        "revision": resolved,
        "revision_source": "hf-snapshot" if resolved else "unavailable",
        "device": device,
        "precision": precision,
    }
    if resolved:
        files = weight_files(model_id, resolved)
        # Names and sizes are free and catch a truncated download; the content hash is not.
        out["weight_files"] = [f"{f.name}:{f.stat().st_size}" for f in files]
        if os.environ.get("EVAL_FINGERPRINT_WEIGHTS") == "1":
            out["weights_sha256"] = _weights_sha256(files)
    if revision and resolved != revision:
        # The pin and reality disagree. Say so IN the fingerprint, where a comparison will
        # see it, not only in a log line somebody has to still have.
        out["pinned_revision_requested"] = revision
        out["pin_satisfied"] = False
    elif revision:
        out["pin_satisfied"] = True
    return out
