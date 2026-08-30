"""The single structured generation call.

`instructor.from_litellm` runs in tool-calling mode by default, which means it
consumes the tool channel to extract the response model -- so a design that also
hands the model the eight real tools in the same request would have to give up
either the structured output or a round trip. Because gathering is deterministic
there are no tools to pass, and this ends up being both the frictionless option
and the most portable one: tool-calling is the most widely supported
structured-output mechanism across providers.
"""
from __future__ import annotations

import os
import random
import threading
import time

import instructor
import litellm
from litellm import completion

from .config import MODEL
from .schema_internal import Draft

litellm.drop_params = True        # reasoning models reject temperature; portability
litellm.suppress_debug_info = True  # provider banners on every retry drown the sweep

# Free and low-tier provider plans rate-limit aggressively, and a parallel eval
# sweep will trip them within seconds. Two guards, both provider-agnostic:
#
#   1. A global token bucket, so total request rate is bounded no matter how many
#      worker threads the sweep runs. Shared across threads by design.
#   2. Bounded exponential backoff with jitter on rate-limit errors specifically.
#
# Without these, a sweep does not measure the system -- it measures the quota. The
# first full run came back at 44/100 with 352 rate-limit errors and only 16 of an
# expected ~120 generations actually reaching the model.
RPM = int(os.environ.get("ACMEPAY_RPM", "12"))
_RATE_LOCK = threading.Lock()
_next_slot = [0.0]


def _await_slot() -> None:
    if RPM <= 0:
        return
    interval = 60.0 / RPM
    with _RATE_LOCK:
        now = time.monotonic()
        wait = max(0.0, _next_slot[0] - now)
        _next_slot[0] = max(now, _next_slot[0]) + interval
    if wait:
        time.sleep(wait)


def _is_rate_limit(exc: Exception) -> bool:
    if exc.__class__.__name__ in {"RateLimitError", "Timeout", "APIConnectionError",
                                  "ServiceUnavailableError", "InternalServerError"}:
        return True
    text = str(exc)
    return "429" in text or "RESOURCE_EXHAUSTED" in text or "rate limit" in text.lower()

_client = instructor.from_litellm(completion)

# instructor resolves its per-(provider, mode) handlers lazily, and the lookup is
# a check-then-act on a plain dict: it pops the loader, calls it, then stores the
# result. Two threads racing the first call leave the second one with neither the
# loader nor the handler, which surfaces as
# `KeyError: Mode (...) is not registered. Available modes: []`.
#
# The eval sweep runs cases in parallel, so this is not hypothetical -- it showed
# up as most cases silently falling back to the deterministic path. Draining the
# lazy loaders once at import, before any worker thread exists, removes the race
# without paying for a lock on every call. Wrapped defensively because it reaches
# into instructor internals.
_WARM_LOCK = threading.Lock()
_WARMED = False


def _warm_registry() -> None:
    try:
        from instructor.v2.core.registry import mode_registry
        for provider, mode in list(mode_registry._lazy_loaders):
            try:
                mode_registry.get_handlers(provider, mode)
            except Exception:
                pass
    except Exception:
        pass


_warm_registry()


def one_shot(system_text: str, user_text: str, telemetry=None, model: str | None = None) -> Draft:
    # Belt and braces: if a future instructor reshuffles its internals so the warm
    # -up above no longer applies, serialise the very first call only.
    global _WARMED
    if not _WARMED:
        with _WARM_LOCK:
            if not _WARMED:
                try:
                    return _call(system_text, user_text, telemetry, model)
                finally:
                    _WARMED = True
    return _call(system_text, user_text, telemetry, model)


MAX_ATTEMPTS = 4

# Ollama silently truncates a prompt to the server-side context window, which
# recent releases default to 4096 tokens. The request still succeeds, so nothing
# in the response says the policy corpus was cut off. The full-context design puts
# ~13K tokens in front of the model, so this has to be set explicitly or the run
# is measuring a truncated prompt. Local inference is also far slower than a
# hosted endpoint, hence the longer deadline.
_NUM_CTX = int(os.environ.get("ACMEPAY_NUM_CTX", "16384"))
_LOCAL_TIMEOUT_S = float(os.environ.get("ACMEPAY_TIMEOUT_S", "900"))


def _provider_extras(model: str) -> dict:
    if model.startswith(("ollama/", "ollama_chat/")):
        return {"num_ctx": _NUM_CTX, "timeout": _LOCAL_TIMEOUT_S}
    return {}


def _call(system_text: str, user_text: str, telemetry=None, model: str | None = None) -> Draft:
    last: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        _await_slot()
        try:
            return _once(system_text, user_text, telemetry, model)
        except Exception as exc:
            last = exc
            if not _is_rate_limit(exc) or attempt == MAX_ATTEMPTS - 1:
                raise
            # Exponential with jitter; jitter matters because parallel workers
            # otherwise retry in lockstep and trip the limit again together.
            time.sleep(min(2 ** attempt * 2.0, 30.0) + random.uniform(0, 1.5))
    raise last                                          # pragma: no cover


def _once(system_text: str, user_text: str, telemetry=None, model: str | None = None) -> Draft:
    target = model or MODEL
    draft, raw = _client.chat.completions.create_with_completion(
        model=target,
        response_model=Draft,
        messages=[
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ],
        temperature=0,          # dropped automatically where unsupported
        max_retries=2,
        cache_control={"type": "ephemeral"},   # honoured where supported
        **_provider_extras(target),
    )
    if telemetry is not None:
        telemetry.record(raw)
    return draft
