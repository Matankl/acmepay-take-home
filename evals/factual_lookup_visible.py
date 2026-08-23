"""Visible factual_lookup eval cases.

Authoring rule (locked after two rounds of empirical calibration + a 3-reviewer
panel reconsult):

    Every case must turn on a fact whose authoritative chunk does NOT share
    salient keywords with a natural phrasing of the question. Verify by
    running the question through the starter's retriever; if the answer chunk
    IS reliably retrieved AND the starter's answer contains the required
    token, REJECT the case or rephrase to widen the lexical gap.

The reframing: factual_lookup measures **retrieval robustness under
lexical/semantic gap**, not knowledge. Modern small LLMs with naive RAG over
6 short well-indexed policy docs read facts off the page reliably when the
question keywords lexically overlap the answer chunk. Discrimination signal
comes from questions where they don't.

Composition (15 cases):
  8 baseline / counter-intuitive cases — establish the floor; mostly pass
  7 verified retrieval-gap cases — starter empirically fails them
  Predicted starter pass rate: 8-10 / 15

Round-3 panel reconsult (2026-05-26): asked whether to push harder via
panel-named patterns (2) chunk-boundary and (5) multi-hop within one doc.
Empirical loop on this substrate (6 short docs, k=3) showed those patterns
do NOT discriminate — the retriever is forgiving enough that even sentence-
split or section-split facts are still recovered when k=3. The two new cases
(014, 015) therefore exploit the same root pathology as the other B-types
(vocab gap → retriever misses the right doc entirely), but cover previously
untouched policy domain: restricted-categories + appeal-process config.

Hedge enforcement is now a GLOBAL grader check (evals/schema.py): for any case
where expect_refused != True, hedge phrases in the answer prose require the
structured `refused` field to be True. This catches "vocabulary cosplay" — a
hedged refusal that smuggles topical doc tokens into the prose, where pure
substring matching would pass it as success. Panel round 4 fix.

For the B-type retrieval-gap cases (009-015), the starter empirically fails
either by missing required tokens OR by hedging-with-refused=False — the
global rule catches the second mode; the token requirements catch the first.
"""
from __future__ import annotations

from .schema import EvalCase


# Note: hedge-phrase forbids used to live here as a per-case `_HEDGE_PHRASES`
# list. They were promoted to a global grader check (HEDGE_PHRASES in
# evals/schema.py) after panel round 4 — that check fires for any case where
# expect_refused is not True, so we no longer need to wire them per case.


CASES: list[EvalCase] = [

    # ============================================================
    # BASELINE / COUNTER-INTUITIVE CASES
    # Expected: starter passes ~all of these.
    # Their job is to (a) catch a candidate whose changes regressed
    # the basics and (b) provide a credible floor for the category.
    # ============================================================

    EvalCase(
        id="factual_lookup_001",
        category="factual_lookup",
        question="If a merchant fully refunds a transaction, do they get the original processing fee back?",
        answer_contains_any_of=[
            ["not returned", "not refunded", "is kept", "we keep", "acmepay keeps",
             "still applies", "non-refundable", "is retained", "we retain", "do not get"],
        ],
        answer_must_not_contain=[
            "fee is returned", "fee is refunded", "processing fee back",
            "including fees", "yes, the fee", "yes the fee",
        ],
        must_cite=["fees_and_pricing"],
        notes="Counter-intuitive: original transaction fee NOT returned on refund. Industry prior strongly says yes. Retrieval reliable; hedge enforced globally. Forbid list specifically targets the additive-fabrication pattern observed in panel round 4 (starter invented an 'Acmepay-side error' escape valve).",
    ),

    EvalCase(
        id="factual_lookup_002",
        category="factual_lookup",
        question="Who pays the international card surcharge — the merchant or the cardholder?",
        answer_contains_any_of=[["merchant"]],
        answer_must_not_contain=[
            "surcharge is paid by the cardholder",
            "surcharge is paid by the customer",
            "cardholder pays the surcharge",
            "customer pays the surcharge",
            "cardholder pays the 1.5",
            "customer pays the 1.5",
            "surcharge is charged to the cardholder",
            "surcharge is charged to the customer",
        ],
        must_cite=["fees_and_pricing"],
        notes="Reverses industry intuition. Forbids target ONLY phrases that say the surcharge falls on the cardholder/customer — not the generic 'customer is charged $100' which is correct (and quoted from the doc's example). Hedge enforced globally.",
    ),

    EvalCase(
        id="factual_lookup_003",
        category="factual_lookup",
        question="At what chargeback ratio does Acmepay's monitoring threshold trigger?",
        answer_contains_all=["1.0%"],
        answer_contains_any_of=[["monitoring", "monitored", "warning", "watched"]],
        must_cite=["chargeback_policy"],
        notes="Acmepay-specific number. Retrieval reliable; hedge enforced globally.",
    ),

    EvalCase(
        id="factual_lookup_004",
        category="factual_lookup",
        question="Are nutraceutical supplement merchants accepted through Acmepay's standard onboarding flow?",
        answer_contains_any_of=[
            ["restricted", "rejected", "not accepted", "not onboarded",
             "not allowed", "do not onboard", "prohibited"],
        ],
        must_cite=["onboarding_playbook"],
        notes="Acmepay-specific restricted-category policy. Supports M-1006 narrative downstream. Hedge enforced globally — the panel-round-4 false-pass was a hedged answer with 'restricted categories' parroted from the doc; the global hedge-consistency check now catches that.",
    ),

    EvalCase(
        id="factual_lookup_005",
        category="factual_lookup",
        question="Which HTTP header carries the webhook signature for verifying inbound Acmepay events?",
        answer_contains_all=["Acmepay-Signature"],
        answer_must_not_contain=[
            "X-Signature", "Stripe-Signature", "Webhook-Signature",
        ],
        must_cite=["api_reference"],
        notes="Ungueessable Acmepay-specific string. Retrieval reliable on this one (api_reference chunks rank high for 'webhook signature header'). Hedge enforced globally; forbid covers competitor header names.",
    ),

    EvalCase(
        id="factual_lookup_006",
        category="factual_lookup",
        question="What settlement timeline and rolling reserve apply to a brand-new low-risk merchant on day 30?",
        answer_contains_any_of=[
            ["T+5", "T + 5", "five business days", "5 business days"],
            ["10%", "10 percent"],
        ],
        answer_must_not_contain=[
            # Defined-term-of-art misuse forbids (panel round 4 — starter called
            # a brand-new LOW-risk merchant's setup a specific HIGH-risk/
            # appeal-process status).
            "high risk category", "high-risk category",
            "appeal-process",
        ],
        must_cite_any_of=[["settlement_timing", "onboarding_playbook"]],
        notes="Compound: settlement timing + reserve in one answer. Both facts are in canonical docs. Two any-of groups means both groups must each match at least once. Forbid list catches (a) wrong-term-of-art use ('extended settlement' for a low-risk merchant) and (b) fabricated reserve-release mechanism — both observed in panel round 4.",
    ),

    EvalCase(
        id="factual_lookup_007",
        category="factual_lookup",
        question="What's Acmepay's current stable API version string?",
        answer_contains_all=["2026-01-15"],
        must_cite=["api_reference"],
        notes="Ungueessable date string. Retrieval succeeds because 'API version' lexically matches api_reference doc. Hedge enforced globally.",
    ),

    EvalCase(
        id="factual_lookup_008",
        category="factual_lookup",
        question="If a merchant wins a chargeback dispute, do they get the $15 chargeback fee back?",
        answer_contains_any_of=[
            ["non-refundable", "not refunded", "not returned", "stays gone",
             "fee is not", "non refundable", "do not get"],
        ],
        answer_must_not_contain=[
            "fee is refunded", "fee is returned", "get the fee back",
            "yes, the fee", "yes the fee",
        ],
        must_cite=["chargeback_policy"],
        notes="Counter-intuitive: chargeback fee non-refundable even on win. Retrieval reliable. Hedge enforced globally.",
    ),

    # ============================================================
    # B-TYPE RETRIEVAL-GAP CASES
    # Expected: starter empirically fails these.
    # The right doc/chunk isn't reliably surfaced; the model either
    # honestly hedges or confidently misses the fact.
    # NO hedge forbid — honest hedging is acceptable; the discriminator
    # is the required Acmepay-specific token being absent.
    # ============================================================

    EvalCase(
        id="factual_lookup_009",
        category="factual_lookup",
        question="How many calls per second can the merchant dashboard make before getting throttled?",
        answer_contains_all=["100"],
        answer_contains_any_of=[["per second", "/s", "req/s", "requests per second"]],
        must_cite=["api_reference"],
        notes="B-type. Vocab gap: 'throttled' / 'dashboard' don't lexically match 'Rate Limits' header. Starter empirically fails to retrieve api_reference at all.",
    ),

    EvalCase(
        id="factual_lookup_010",
        category="factual_lookup",
        question="How long does the identity verification step usually take for a new applicant?",
        answer_contains_any_of=[
            ["1-3", "1 to 3", "one to three", "1–3"],
        ],
        answer_contains_all=["business days"],
        must_cite=["onboarding_playbook"],
        notes="B-type. Starter retrieves onboarding_playbook but the chunk it retrieves blends 'identity verification' with the 7-10 day overall-review timeline. Tests disambiguation between KYC (1-3 days) and full appeal review (7-10 days).",
    ),

    EvalCase(
        id="factual_lookup_011",
        category="factual_lookup",
        question="If I retry a failed payment request with the same safety key, how long does Acmepay remember it?",
        answer_contains_any_of=[["24 hour", "24-hour", "24h", "twenty-four hour"]],
        must_cite=["api_reference"],
        notes="B-type. Vocab gap: 'safety key' is a stand-in for idempotency key. Starter retrieves api_reference but the wrong chunk; the model says 'context doesn't specify' even though the doc states 24-hour caching.",
    ),

    EvalCase(
        id="factual_lookup_012",
        category="factual_lookup",
        question="Is there an automatic notification I can subscribe to when one of my merchants crosses the warning threshold?",
        answer_contains_any_of=[["account.warning_issued", "warning_issued"]],
        must_cite=["api_reference"],
        notes="B-type. Vocab gap: 'notification I can subscribe to' doesn't match 'webhook events'. Starter empirically misses api_reference and answers only from chargeback_policy (which describes the email warning but not the webhook event).",
    ),

    EvalCase(
        id="factual_lookup_013",
        category="factual_lookup",
        question="What status code comes back if I try to upload dispute evidence after the response deadline has passed?",
        answer_contains_all=["403"],
        must_cite=["api_reference"],
        notes="B-type. Vocab gap: 'status code' + 'deadline passed' should match api_reference's error-codes table (which lists '403 — Action not permitted (e.g. submitting evidence after the 7-day window)') but starter retrieves chargeback_policy instead and hedges.",
    ),

    EvalCase(
        id="factual_lookup_014",
        category="factual_lookup",
        question="We have a cryptocurrency exchange business that successfully petitioned Acmepay's review path. What settlement and reserve setup do they start on?",
        answer_contains_any_of=[
            ["T+5", "T + 5", "5 business days"],
            ["15%", "15 percent"],
        ],
        must_cite=["onboarding_playbook"],
        notes="B-type. Multi-hop in spirit (hop 1: crypto is restricted [chunk 2]; hop 2: appeal-process exit config = T+5+15% [chunk 4] — both in onboarding_playbook). Empirically the starter doesn't retrieve onboarding_playbook at all because 'petitioned'/'review path' lexically mismatch 'appeal'/'exception process'. Starter returns empty or hedged answer.",
    ),

    EvalCase(
        id="factual_lookup_015",
        category="factual_lookup",
        question="Can a coin-trading platform sign up for Acmepay through the normal application?",
        answer_contains_any_of=[
            ["restricted", "rejected", "not accepted", "not onboarded",
             "not allowed", "do not onboard", "prohibited", "cannot",
             "can't sign up", "not eligible"],
        ],
        must_cite=["onboarding_playbook"],
        notes="B-type. Vocab gap: 'coin-trading platform' doesn't lexically match 'Cryptocurrency exchanges' in the restricted-categories list (chunk 2 of onboarding_playbook). Starter retrieves api_reference/fees/merchant_faq and hedges 'docs don't say'.",
    ),
]
