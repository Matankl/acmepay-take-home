"""Per-request counters: LLM calls, tokens, cache reads, latency, real cost.

Cache reads are *measured*, not assumed. The installed litellm has no
`supports_prompt_caching` helper, and providers report the counter under
different names, so the prefix is simply built cache-friendly and whichever
counter comes back is recorded. Cost comes from litellm rather than an estimate.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field


@dataclass
class Telemetry:
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    cost_usd: float = 0.0
    latency_s: float = 0.0
    tool_calls: int = 0
    repairs: int = 0
    errors: list[str] = field(default_factory=list)
    _t0: float = field(default_factory=time.perf_counter, repr=False)

    def record(self, raw) -> None:
        self.llm_calls += 1
        usage = getattr(raw, "usage", None)
        if usage is None:
            return
        self.prompt_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
        self.completion_tokens += int(getattr(usage, "completion_tokens", 0) or 0)
        # OpenAI-style nested detail, Anthropic-style flat field, Gemini-style.
        details = getattr(usage, "prompt_tokens_details", None)
        for source in (
            getattr(details, "cached_tokens", None) if details else None,
            getattr(usage, "cache_read_input_tokens", None),
            getattr(usage, "cached_tokens", None),
        ):
            if source:
                self.cached_tokens += int(source)
                break
        try:
            from litellm import completion_cost
            self.cost_usd += float(completion_cost(completion_response=raw) or 0.0)
        except Exception:
            pass

    def stop(self) -> "Telemetry":
        self.latency_s = round(time.perf_counter() - self._t0, 3)
        return self

    def as_dict(self) -> dict:
        d = asdict(self)
        d.pop("_t0", None)
        d["cost_usd"] = round(d["cost_usd"], 6)
        # Numeric mirror of `errors`, because aggregation across cases only sums
        # numbers -- and a fallback that succeeds quietly is exactly what needs to
        # be visible in a summary.
        d["error_count"] = len(self.errors)
        return d
