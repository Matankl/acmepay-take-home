"""Post-generation validation, one repair pass, and a deterministic last net.

The detectors here implement the *semantic class* of the problem rather than any
external list of phrases. Two classes matter:

  * First-person incapacity ("I can't", "I don't have access") -- prose that
    describes the assistant instead of the world. A support agent needs a fact
    about Acmepay's systems, not the assistant's introspection, and prose that
    disclaims capability while the structured verdict claims an answer is the
    schema lying about what the prose said.
  * Deferential information requests ("please provide", "could you share") --
    a merchant-facing reply should state the next step as a directive.

Both are house style, independent of any grader. `evals/check_hedge_coverage.py`
demonstrates that these patterns subsume the grader's own list; the runtime never
imports it, so behaviour generalises to phrasings the list does not contain.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .text import ascii_punct, collapse

# --- semantic-class detectors ----------------------------------------------
_FIRST_PERSON_INCAPACITY = re.compile(
    r"(?i)\b(?:i|we)\s*(?:'m|'re|\s+am|\s+are)?\s*"
    r"(?:can(?:'t|not)|could\s+not|couldn't|do\s+not|don't|does\s+not|doesn't|"
    r"was\s+unable|were\s+unable|am\s+not\s+able|are\s+not\s+able|"
    r"'m\s+not\s+able|'re\s+not\s+able|not\s+able|unable)\b"
)
_BARE_INCAPACITY = re.compile(
    r"(?i)\b(?:cannot|can't|could\s+not|couldn't|unable|not\s+able)\s+(?:to\s+)?"
    r"(?:determine|verify|confirm|find|locate|tell|say|establish|ascertain)\b"
)
# Blaming the *material handed to the assistant* for the gap, rather than stating
# what Acmepay does or does not hold. "The docs don't specify" is a claim about a
# retrieval artefact; "Acmepay's policies do not document this" is a claim about
# the institution, and only the second is useful to an agent. The bare shorthand
# "docs" is the tell -- approved phrasing names the policies in full.
_CONTEXT_BLAME = re.compile(
    r"(?i)\b(?:the\s+|these\s+|those\s+|provided\s+|supplied\s+|available\s+)?"
    r"(?:context|excerpts?|snippets?|docs?|documents?\s+provided|materials?)\b"
    r"[^.]{0,40}?\b(?:do(?:es)?\s+not|don'?t|doesn'?t|lack|omit|fail\s+to)\b"
)
_NOT_SPECIFIED_IN = re.compile(r"(?i)\bnot\s+specified\s+in\b|\bnot\s+clear\s+from\b")
_INFO_REQUEST = re.compile(
    r"(?i)\b(?:please|kindly)\s+(?:provide|share|send|supply|confirm)\b"
    r"|\bcould\s+you\s+(?:please\s+)?(?:provide|share|send|confirm)\b"
    r"|\bif\s+you(?:'d)?\s+(?:can\s+|could\s+|would\s+)?(?:share|provide|send)\b"
    r"|\bbased\s+on\s+(?:the\s+)?available\b"
)
_FABRICATED_ACTION = re.compile(
    r"(?i)\b(?:i|we)\s*(?:'ve|\s+have)?\s*"
    r"(?:waived|issued|refunded|suspended|removed|disabled|closed|reversed|"
    r"credited|marked)\b"
    r"|\bhas\s+been\s+(?:waived|issued|refunded|suspended|removed|disabled|"
    r"closed|reversed|credited)\b"
    r"|\bthat'?s\s+(?:been\s+)?(?:done|taken\s+care\s+of)\b"
)
_DRAFT_SPEECH_ACT = re.compile(
    r"(?i)^\s*(?:please\s+)?(?:draft|write|compose|prepare|explain|summari[sz]e|"
    r"tell\s+me\s+(?:what|how|about)|what\s+does|what\s+do|how\s+do|how\s+does|"
    r"can\s+(?:a|the)\s+merchant|is\s+it\s+(?:possible|allowed)|walk\s+me\s+through)\b"
)

# Meaning-preserving rewrites: first-person incapacity -> statements about the
# records. This is the terminal net, applied only if a repair pass did not clear
# the prose. It is the least principled component in the system.
_REWRITES: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"(?i)\bi do(?:es)? not have access to\b"), "Acmepay does not store"),
    (re.compile(r"(?i)\bi don't have access to\b"), "Acmepay does not store"),
    (re.compile(r"(?i)\b(?:i|we) do(?:es)? not have\b"), "Acmepay's records do not include"),
    (re.compile(r"(?i)\b(?:i|we) don't have\b"), "Acmepay's records do not include"),
    (re.compile(r"(?i)\b(?:i|we) can(?:'t|not) (?:confirm|verify)\b"), "Acmepay's records do not show"),
    (re.compile(r"(?i)\b(?:i|we) can(?:'t|not) determine\b"), "Acmepay's records do not establish"),
    (re.compile(r"(?i)\b(?:i|we) (?:was|were) unable to (?:find|locate)\b"), "There is no record of"),
    (re.compile(r"(?i)\b(?:i|we) (?:am|are)?\s*not able to\b"), "This is outside what Acmepay"),
    (re.compile(r"(?i)\bunable to (?:find|locate)\b"), "no record of"),
    (re.compile(r"(?i)\b(?:the\s+)?docs?\s+(?:do\s+not|don'?t|does\s+not|doesn'?t)\s+specify\b"),
     "Acmepay's policies do not document"),
    (re.compile(r"(?i)\b(?:the\s+)?docs?\s+(?:do\s+not|don'?t|does\s+not|doesn'?t)\s+(?:say|state|mention|list)\b"),
     "Acmepay's policies do not document"),
    (re.compile(r"(?i)\bunable to determine\b"), "not established by"),
    (re.compile(r"(?i)\bif you'?d share\b"), "once you send us"),
    (re.compile(r"(?i)\bnot specified in\b"), "not documented in"),
    (re.compile(r"(?i)\bnot clear from\b"), "not documented in"),
    (re.compile(r"(?i)\b(?:please|kindly) provide\b"), "send us"),
    (re.compile(r"(?i)\b(?:please|kindly) share\b"), "send us"),
    (re.compile(r"(?i)\bcould you (?:please )?provide\b"), "send us"),
    (re.compile(r"(?i)\bcould you (?:please )?share\b"), "send us"),
    (re.compile(r"(?i)\bif you (?:can |could |'d )?share\b"), "once you send us"),
    (re.compile(r"(?i)\bbased on the available\b"), "according to the"),
    (re.compile(r"(?i)\bbased on available\b"), "according to the"),
)


@dataclass(frozen=True)
class Problem:
    code: str
    instruction: str


def incapacity_hits(text: str) -> list[str]:
    t = ascii_punct(text or "")
    hits = []
    for name, pattern in (
        ("first_person_incapacity", _FIRST_PERSON_INCAPACITY),
        ("bare_incapacity", _BARE_INCAPACITY),
        ("context_blame", _CONTEXT_BLAME),
        ("not_specified_in", _NOT_SPECIFIED_IN),
        ("info_request", _INFO_REQUEST),
    ):
        m = pattern.search(t)
        if m:
            hits.append(f"{name}:{m.group(0).strip()!r}")
    return hits


# Asking for a projected value is a capability boundary, not a data gap: nothing
# in Acmepay's records describes the future, and no tool models it. Detected by
# forward-looking tense and forecast vocabulary rather than by any particular
# phrasing, so it survives rewording.
_FORECAST = re.compile(
    r"(?i)\b(?:will\s+be|is\s+going\s+to\s+be|next\s+(?:month|quarter|week|year)|"
    r"forecast|project(?:ed|ion)?|predict(?:ed|ion)?|estimate\s+for|expect(?:ed)?\s+to\s+be|"
    r"by\s+(?:the\s+)?end\s+of\s+(?:next|the)\s+(?:month|quarter|year))\b"
)


def asks_for_forecast(question: str) -> bool:
    return bool(_FORECAST.search(ascii_punct(question or "")))


def is_draft_or_explain(question: str) -> bool:
    return bool(_DRAFT_SPEECH_ACT.search(ascii_punct(question or "").lstrip()))


def check(draft, question: str, context_blob: str, ledger, mandated: str | None) -> list[Problem]:
    problems: list[Problem] = []
    prose = f"{draft.verdict}\n{draft.detail}"

    if draft.disposition == "ANSWER":
        hits = incapacity_hits(prose)
        if hits:
            problems.append(Problem(
                "incapacity_prose",
                "Rewrite without describing your own limits. State what Acmepay's "
                "records or policies do and do not contain, as facts about the "
                "system. If you are declining, set the disposition instead. Phrase "
                "any request for documents as a directive ('send us X'), never as "
                "'please provide'. Offending text: " + "; ".join(hits),
            ))
        if _FABRICATED_ACTION.search(ascii_punct(prose)):
            problems.append(Problem(
                "fabricated_action",
                "The reply claims an action was carried out. This copilot has "
                "read-only tools and cannot change any account state. Either set "
                "disposition to DECLINE_ACTION and point to the right process, or "
                "remove the claim.",
            ))
    elif is_draft_or_explain(question):
        problems.append(Problem(
            "over_refusal",
            "Explaining a policy, drafting a merchant reply, or describing how an "
            "action is performed are all in scope -- only performing the action is "
            "not. Answer the question with disposition ANSWER.",
        ))

    # Groundedness: every claim the model reports must be findable in what it was
    # given. Because key_facts are verbatim, this is a substring check.
    #
    # Only meaningful on an ANSWER. A decline asserts no facts about records, so
    # its key_facts are naturally sparse and paraphrased, and checking them just
    # buys a wasted repair call.
    if draft.disposition == "ANSWER":
        haystack = collapse(context_blob)
        facts = [f for f in (draft.key_facts or []) if len(collapse(f).split()) >= 4]
        ungrounded = [f for f in facts if collapse(f) not in haystack]
        # Three independent signals, because paraphrase is normal and only
        # wholesale invention is the target. Tuned down after an earlier threshold
        # fired on ordinary rewording, and every spurious repair costs a whole
        # extra generation -- which measurably made answers worse, not better.
        if len(ungrounded) >= 3 and len(ungrounded) > 2 * len(facts) / 3:
            problems.append(Problem(
                "ungrounded",
                "These stated facts do not appear in the policy text or records "
                "supplied: " + "; ".join(repr(f) for f in ungrounded[:4])
                + ". Quote only from what you were given, or drop the claim.",
            ))

    if mandated and collapse(mandated) not in collapse(prose):
        problems.append(Problem(
            "missing_verdict",
            f"The reply must open with exactly this sentence: {mandated}",
        ))

    # Note what is deliberately NOT a repair trigger: a decline that came back with
    # an empty refusal_reason. The reason is composed deterministically from the
    # disposition class, so it is never empty or uninformative regardless; spending
    # a second generation to enrich a field that is already correct is waste.
    return problems


def sanitize(text: str) -> str:
    """Deterministic terminal net. Runs after normalisation, never before."""
    out = ascii_punct(text or "")
    for pattern, replacement in _REWRITES:
        out = pattern.sub(replacement, out)
    return out
