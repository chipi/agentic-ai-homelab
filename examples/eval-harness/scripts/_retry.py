"""Retrying transient provider failures. Generic infrastructure, not domain logic.

This lives in the CORE, not in an adapter, because of how it was learned. The bundled
demo adapter had retries and honoured `EVAL_MAX_RETRIES`, so the knob looked wired up
everywhere — and the summarisation example, which defined its own adapter, had none at
all. Two sweeps lost an arm to a single upstream 429: ~20 paid calls thrown away, and
the run reported "ARM FAILED" as though the model could not do the task.

Raising `EVAL_MAX_RETRIES` did nothing, because the adapter doing the work never read it.
That is the failure mode this module exists to prevent: an adapter author should get
retries by not thinking about it, rather than by remembering to copy twenty lines.

    attempts        EVAL_MAX_RETRIES       default 8
    delay cap       EVAL_RETRY_MAX_DELAY   default 60 seconds

Backoff doubles — 1, 2, 4, 8, 16, 32 … — and then flattens at the cap, so the wait grows
quickly while a blip is likely and then stops growing rather than running away. Jitter is
added so that N arms retrying after the same upstream hiccup do not return in lockstep
and cause the next one.
"""

from __future__ import annotations

import os
import random
import time
from typing import Any, Callable, Iterable, Optional, Sequence, Tuple

#: Substrings that mark a failure as worth retrying. Matched case-insensitively against
#: "TypeName: message", because provider SDKs disagree about everything else: some raise
#: typed errors, some raise a generic one with the status in the text, some wrap a third
#: party's exception. The status codes and these words are what they have in common.
TRANSIENT: Tuple[str, ...] = (
    "429", "500", "502", "503", "504",
    "rate limit", "rate-limited", "ratelimit", "too many requests",
    "overloaded", "capacity", "temporarily", "try again",
    "timeout", "timed out", "connection", "reset by peer", "eof occurred",
)

#: NOT retryable, whatever else the message says. A bad key or a malformed request fails
#: identically on every attempt, so retrying only spends time — and, where a provider
#: bills rejected requests, money — to fail more slowly. Checked BEFORE `TRANSIENT`,
#: because "401 ... please try again later" should not be read as transient.
FATAL: Tuple[str, ...] = (
    "401", "403", "invalid api key", "authentication", "permission denied",
    "not found", "404", "model_not_found", "does not exist",
    "invalid_request", "context length", "max_tokens",
)


def is_transient(exc: BaseException, extra: Iterable[str] = ()) -> bool:
    """Whether this failure is worth another attempt."""
    msg = f"{type(exc).__name__}: {exc}".lower()
    if any(m in msg for m in FATAL):
        return False
    return any(m in msg for m in tuple(TRANSIENT) + tuple(extra))


def _env_int(name: str, default: int) -> int:
    try:
        return int(float(os.environ.get(name, "").strip()))
    except (TypeError, ValueError):
        return default


def call_with_retries(
    fn: Callable[..., Any],
    args: Sequence[Any] = (),
    *,
    extra_transient: Iterable[str] = (),
    attempts: Optional[int] = None,
    max_delay: Optional[float] = None,
    label: str = "",
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    """Call `fn(*args)`, retrying transient failures with capped exponential backoff.

    `SystemExit` is never retried: the harness raises it for "your key is not set" and
    similar, and those are instructions to the operator, not weather.

    `sleep` is injectable so the behaviour can be tested without actually waiting — a
    retry policy whose tests are slow is a retry policy nobody tests.
    """
    tries = max(1, attempts if attempts is not None else _env_int("EVAL_MAX_RETRIES", 8))
    cap = max_delay if max_delay is not None else float(_env_int("EVAL_RETRY_MAX_DELAY", 60))
    last: Optional[BaseException] = None
    for attempt in range(1, tries + 1):
        try:
            return fn(*args)
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001 — provider SDKs vary too much to enumerate
            if attempt == tries or not is_transient(exc, extra_transient):
                raise
            last = exc
            delay = min(cap, 2.0 ** (attempt - 1)) + random.uniform(0, 0.5)
            where = f" {label}" if label else ""
            print(f"      transient{where} ({type(exc).__name__}), "
                  f"retry {attempt}/{tries - 1} in {delay:.1f}s")
            sleep(delay)
    raise last if last else RuntimeError("unreachable")
