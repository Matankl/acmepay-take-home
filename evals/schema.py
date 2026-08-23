"""Eval case schema and grader.

One unified case schema for all 6 categories. Per-category, the *enabled*
fields differ (a factual_lookup case sets answer matchers + citations; a
tool_use case adds must_call_tools; a refusal case sets expect_refused).
Same grader, same runner, same file format.

Grading is binary per case. Aggregate later.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Case schema
# ---------------------------------------------------------------------------


@dataclass
class ToolCallExpectation:
    """Expect a tool call with `name`. Optionally require args to contain
    each (key, value) in `args_subset` exactly. Extra args are OK."""
    name: str
    args_subset: dict = field(default_factory=dict)


@dataclass
class EvalCase:
    id: str
    category: str
    question: str

    # --- Answer text matchers (case-insensitive, whitespace-normalized) ---
    answer_contains_all: list[str] = field(default_factory=list)
    answer_contains_any_of: list[list[str]] = field(default_factory=list)
    answer_must_not_contain: list[str] = field(default_factory=list)

    # --- Citation matchers (doc IDs are normalized: lowercase, strip .md) ---
    must_cite: list[str] = field(default_factory=list)
    # Each inner list is an OR group: at least one of the listed docs must
    # appear in cited_doc_ids. Use for facts that live in multiple canonical
    # docs (e.g. 10% rolling reserve appears in both settlement_timing and
    # onboarding_playbook — either citation is fine).
    must_cite_any_of: list[list[str]] = field(default_factory=list)
    forbidden_cites: list[str] = field(default_factory=list)

    # --- Tool-call matchers ---
    must_call_tools: list[ToolCallExpectation] = field(default_factory=list)
    forbidden_tools: list[str] = field(default_factory=list)

    # --- Refusal matchers (None = don't check) ---
    expect_refused: Optional[bool] = None
    refusal_reason_contains: Optional[str] = None

    # --- Grading controls ---
    # If True, skip the global hedge-consistency check for this case. Use ONLY
    # for drafting cases where requesting information from the merchant (e.g.
    # "please provide 12 months of statements") is the legitimate content of the
    # drafted reply, not a hedge/dodge. Never use it to bypass the check in the
    # factual / investigation / refusal categories.
    skip_hedge_check: bool = False

    # --- Held-out provenance (None for visible cases) ---
    paraphrase_strategy: Optional[str] = None   # "lexical" | "structural" | "adversarial"
    paraphrase_of: Optional[str] = None         # source visible case id

    # --- Free-form provenance for reviewers ---
    notes: str = ""


# ---------------------------------------------------------------------------
# Grader
# ---------------------------------------------------------------------------


# Hedge phrases that signal "I don't have / I can't / share more / could you provide".
# Applied globally to any case where expect_refused != True: if any of these appear
# in the answer prose, refused MUST be True (otherwise the schema field is lying
# about what the prose said — vocabulary-cosplay / hedge-but-not-flagged).
#
# Curated from observed starter outputs + panel guidance (rounds 1-4).
HEDGE_PHRASES = [
    "docs don't specify",
    "docs do not specify",
    "not specified in",
    "cannot determine",
    "i cannot determine",
    "i can't determine",
    "unable to find",
    "unable to determine",
    "i don't have",
    "i do not have",
    "i can't verify",
    "i cannot verify",
    "i can't confirm",
    "i cannot confirm",
    "not clear from",
    "context doesn't",
    "context does not",
    "not enough context",
    "insufficient context",
    "based on available",
    "based on the available",
    "i don't have access",
    "i do not have access",
    "the provided excerpt",
    "the excerpt does not",
    "provided context doesn't",
    "provided context does not",
    "doesn't list",
    "does not list",
    "don't list",
    "do not list",
    "if you share",
    "if you can share",
    "if you'd share",
    "if you could share",
    "could you share",
    "could you provide",
    "please provide",
    "please share",
    "cannot confirm",
    "i'm not able to",
    "i am not able to",
]


def _norm_text(s: str) -> str:
    return " ".join(s.lower().split())


def _norm_doc_id(s: str) -> str:
    return s.lower().removesuffix(".md").strip()


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    checks: list[CheckResult]

    @property
    def failed_checks(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]


def grade(case: EvalCase, response) -> CaseResult:
    """Grade one response. `response` must be a Response (system.py) — duck-typed."""
    checks: list[CheckResult] = []
    answer = _norm_text(getattr(response, "answer", "") or "")

    # Answer text
    for s in case.answer_contains_all:
        ok = _norm_text(s) in answer
        checks.append(CheckResult(f"answer_contains_all[{s!r}]", ok))

    for group in case.answer_contains_any_of:
        ok = any(_norm_text(s) in answer for s in group)
        checks.append(CheckResult(f"answer_contains_any_of[{group!r}]", ok))

    for s in case.answer_must_not_contain:
        ok = _norm_text(s) not in answer
        checks.append(CheckResult(f"answer_must_not_contain[{s!r}]", ok))

    # Citations
    cited_raw = getattr(response, "cited_doc_ids", []) or []
    cited = {_norm_doc_id(c) for c in cited_raw}
    for required in case.must_cite:
        ok = _norm_doc_id(required) in cited
        checks.append(CheckResult(f"must_cite[{required!r}]", ok))
    for group in case.must_cite_any_of:
        ok = any(_norm_doc_id(d) in cited for d in group)
        checks.append(CheckResult(f"must_cite_any_of[{group!r}]", ok))
    for forbidden in case.forbidden_cites:
        ok = _norm_doc_id(forbidden) not in cited
        checks.append(CheckResult(f"forbidden_cites[{forbidden!r}]", ok))

    # Tool calls
    tcs = getattr(response, "tool_calls", []) or []
    called_names = [getattr(tc, "name", "") for tc in tcs]
    for expected in case.must_call_tools:
        matched = False
        for tc in tcs:
            if getattr(tc, "name", "") != expected.name:
                continue
            args = getattr(tc, "args", {}) or {}
            if all(args.get(k) == v for k, v in expected.args_subset.items()):
                matched = True
                break
        checks.append(CheckResult(
            f"must_call_tools[{expected.name}({expected.args_subset!r})]",
            matched,
        ))
    for fname in case.forbidden_tools:
        ok = fname not in called_names
        checks.append(CheckResult(f"forbidden_tools[{fname!r}]", ok))

    # Hedge ↔ refused consistency
    # If the case expects a real answer (not a refusal) and the prose contains
    # a hedge phrase, then the structured `refused` flag MUST be True. This
    # catches "vocabulary cosplay" — a refusal that smuggles topical doc tokens
    # into the prose, where substring matching alone would pass it as success.
    # Panel round 4 fix.
    if case.expect_refused is not True and not case.skip_hedge_check:
        raw_answer = (getattr(response, "answer", "") or "").lower()
        # Use raw lowercase (not _norm_text) so apostrophe variants are handled
        # uniformly — _norm_text only collapses whitespace.
        hit = next((h for h in HEDGE_PHRASES if h in raw_answer), None)
        if hit is not None:
            refused = bool(getattr(response, "refused", False))
            checks.append(CheckResult(
                "hedge_consistency: hedge prose requires refused=True",
                refused,
                detail=f"hedge_phrase={hit!r}, refused={refused}",
            ))

    # Refusal
    if case.expect_refused is not None:
        actual = bool(getattr(response, "refused", False))
        ok = actual == case.expect_refused
        checks.append(CheckResult(
            f"refused == {case.expect_refused}",
            ok,
            detail=f"actual={actual}",
        ))
    if case.refusal_reason_contains is not None:
        rr = getattr(response, "refusal_reason", "") or ""
        ok = _norm_text(case.refusal_reason_contains) in _norm_text(rr)
        checks.append(CheckResult(
            f"refusal_reason_contains[{case.refusal_reason_contains!r}]",
            ok,
        ))

    return CaseResult(
        case_id=case.id,
        passed=all(c.passed for c in checks),
        checks=checks,
    )
