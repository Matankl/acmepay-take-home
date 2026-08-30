"""Held-out proxy: LEXICAL paraphrases.

Same facts, different words. These target the mechanisms most likely to be keyed
on surface form: ID canonicalisation (typographic dashes, spaced separators, bare
numbers next to a type word), merchant-name resolution under added tokens
("Lumen Travel Inc.", "the Maple & Mortar account"), and vocabulary gaps between
how an agent asks and how the policy documents write.

The visible suites are the dev set; the graded set is a paraphrase of them. The
gap between this file's score and the visible score is the overfitting
measurement, and it is the number worth watching.
"""
from __future__ import annotations

from .schema import EvalCase, ToolCallExpectation as Call

CASES: list[EvalCase] = [

    EvalCase(
        id="px_lex_001",
        category="tool_use",
        question="Give me the current state of txn T–99815.",   # en dash
        must_call_tools=[Call("lookup_transaction", {"txn_id": "T-99815"})],
        notes="Typographic dash. Exact-arg matching means a raw en dash scores zero.",
        paraphrase_strategy="lexical", paraphrase_of="tool_use_001",
    ),
    EvalCase(
        id="px_lex_002",
        category="tool_use",
        question="Pull the file on dispute 503 for me.",
        must_call_tools=[Call("get_dispute", {"dispute_id": "D-503"})],
        notes="Bare number next to a type word, no prefix letter.",
        paraphrase_strategy="lexical", paraphrase_of="tool_use_004",
    ),
    EvalCase(
        id="px_lex_003",
        category="tool_use",
        question="What tier and standing is account M 1003 on?",
        must_call_tools=[Call("lookup_merchant", {"merchant_id": "M-1003"})],
        forbidden_tools=["lookup_transaction"],
        notes="Space separator plus synonyms for plan/status.",
        paraphrase_strategy="lexical", paraphrase_of="tool_use_002",
    ),
    EvalCase(
        id="px_lex_004",
        category="investigation",
        question="Is Lumen Travel Inc. close to being shut off over their dispute rate?",
        expect_refused=False,
        must_call_tools=[Call("lookup_merchant", {"merchant_id": "M-1003"})],
        answer_contains_any_of=[["1.0%", "monitoring", "good standing"]],
        answer_must_not_contain=["will be suspended", "suspension is imminent"],
        notes="Added corporate suffix must not break name resolution; and the "
              "1.3% figure sits in the monitoring band, not the suspension band.",
        paraphrase_strategy="lexical", paraphrase_of="investigation_002",
    ),
    EvalCase(
        id="px_lex_005",
        category="investigation",
        question="The Maple & Mortar account is settling on a five-business-day "
                 "cycle rather than two. What's driving that?",
        expect_refused=False,
        must_call_tools=[Call("lookup_merchant", {"merchant_id": "M-1004"})],
        answer_contains_any_of=[["new merchant", "new-merchant", "90 day", "90-day", "first 90"]],
        answer_must_not_contain=["high-risk category", "high-risk merchant", "classified as high-risk"],
        notes="T+5/T+2 never named in the question; name carries a leading article.",
        paraphrase_strategy="lexical", paraphrase_of="investigation_004",
    ),
    EvalCase(
        id="px_lex_006",
        category="factual_lookup",
        question="How many calls a second can a merchant's integration fire before "
                 "we start rejecting them?",
        answer_contains_all=["100"],
        must_cite=["api_reference"],
        notes="Vocabulary gap: the docs say 'Rate Limits' and 'requests/second'.",
        paraphrase_strategy="lexical", paraphrase_of="factual_lookup_009",
    ),
    EvalCase(
        id="px_lex_007",
        category="factual_lookup",
        question="If we replay a payment request with the same dedupe token, how "
                 "long do we remember the first answer?",
        answer_contains_any_of=[["24 hour", "24-hour", "24h"]],
        must_cite=["api_reference"],
        notes="Vocabulary gap: the doc says 'Idempotency-Key' and 'caches responses'.",
        paraphrase_strategy="lexical", paraphrase_of="factual_lookup_011",
    ),
    EvalCase(
        id="px_lex_008",
        category="hallucination",
        question="A coin-trading platform wants to know our published availability "
                 "commitment. What is it?",
        expect_refused=False,
        skip_hedge_check=True,
        answer_contains_any_of=[
            # Widened after measurement: the system answered "Acmepay does not
            # publish an availability commitment or uptime SLA" -- correct, but the
            # first version of this list only anticipated a few surface forms and
            # rejected other correct phrasings. Matcher narrowness is a defect in
            # the test, not in the answer; the discriminator that matters is that
            # the absence is stated and no figure is invented.
            ["not published", "does not publish", "do not publish", "no published",
             "not documented", "does not document", "do not contain",
             "does not contain", "not contain", "no uptime", "no sla",
             "not stated", "does not have", "do not include", "does not include",
             "no availability commitment", "not offer", "does not offer"],
        ],
        answer_must_not_contain=["99.9", "99.95", "99.99"],
        notes="No uptime or SLA figure exists anywhere in the corpus. Must report "
              "the absence as a fact rather than invent a 99.9%-style number -- "
              "which is now forbidden explicitly, since that is the actual failure "
              "mode rather than the choice of negation verb.",
        paraphrase_strategy="lexical", paraphrase_of="hallucination_005",
    ),
    EvalCase(
        id="px_lex_009",
        category="drafting",
        question="Write the merchant back explaining why we kept our cut on the "
                 "$220 charge we reversed for Bright Bean.",
        expect_refused=False,
        answer_contains_any_of=[
            ["not returned", "not refunded", "is kept", "acmepay keeps", "non-refundable",
             "is retained", "won't be returned", "will not be returned", "kept by acmepay"],
        ],
        answer_must_not_contain=["fee is returned", "fee is refunded",
                                 "may be credited", "manually credited"],
        must_cite=["fees_and_pricing"],
        notes="Hedge check is live here: a draft that says 'please provide' or "
              "'I don't have' fails outright. Also must not volunteer the "
              "Acmepay-side-error exception the merchant has not qualified for.",
        paraphrase_strategy="lexical", paraphrase_of="drafting_001",
    ),
]
