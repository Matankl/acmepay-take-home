"""Visible drafting eval cases.

Authoring rule:

    A drafting case asks the system to compose a merchant-facing reply. Tone is
    NOT graded. We grade that the draft contains the substantive, correct,
    policy-grounded facts (deterministic tokens) and does NOT contain the
    known counter-intuitive traps (wrong fee direction, false suspension
    alarm, fabricated escape valves). expect_refused=False on every case — a
    drafting request is legitimate work, never a refusal.

Trap inventory (from _internal/world.md + HANDOFF):
    - Customers do NOT pay processing fees; merchants do.
    - Original processing fee is NOT returned on refund.
    - M-1003 is in the 1.0% monitoring band (1.3%), NOT the 1.5% suspension band.
    - M-1004 is a new merchant in the 90-day T+5 + 10% window.
    - M-1006 (nutraceuticals) was rejected; appeal path exists.

Hedge enforcement is global (expect_refused=False here), so a draft that hedges
with refused=False still fails — drafts must commit to the grounded fact.
"""
from __future__ import annotations

from .schema import EvalCase


CASES: list[EvalCase] = [

    EvalCase(
        id="drafting_001",
        category="drafting",
        question="Draft a reply to Bright Bean explaining why the processing fee on their refunded $220 charge (T-99814) wasn't returned.",
        expect_refused=False,
        answer_contains_any_of=[
            ["not returned", "not refunded", "is kept", "acmepay keeps", "non-refundable", "is retained",
             "not given back", "isn't given back", "won't be returned", "will not be returned",
             "doesn't come back", "does not come back", "kept by acmepay"],
        ],
        answer_must_not_contain=[
            "fee is returned", "fee is refunded",
        ],
        must_cite=["fees_and_pricing"],
        notes="TKT-209 scenario. Counter-intuitive fee-retention fact + additive-fabrication guard.",
    ),

    EvalCase(
        id="drafting_002",
        category="drafting",
        question="Draft a response to Lumen Travel about the chargeback ratio warning email they received. They're at 1.3%.",
        expect_refused=False,
        answer_contains_all=["1.0%"],
        answer_contains_any_of=[["monitoring", "monitored", "warning", "watched"]],
        answer_must_not_contain=[
            "suspended", "about to be suspended",
        ],
        must_cite=["chargeback_policy"],
        notes="TKT-203 scenario. TRAP: 1.3% is in the 1.0% monitoring band, NOT the 1.5% suspension band. False-alarm language fails.",
    ),

    EvalCase(
        id="drafting_003",
        category="drafting",
        question="Draft a reply to Maple & Mortar explaining why their first payout is taking longer than they expected.",
        expect_refused=False,
        answer_contains_any_of=[
            ["t+5", "t + 5", "5 business days", "five business days"],
            ["90 day", "90-day", "new merchant", "new-merchant"],
        ],
        must_cite_any_of=[["settlement_timing", "onboarding_playbook"]],
        notes="TKT-204 scenario. New-merchant T+5 + 90-day window explanation.",
    ),

    EvalCase(
        id="drafting_004",
        category="drafting",
        question="Draft a reply to Verdant Wellness, who is appealing their application rejection. They sell nutraceutical supplements.",
        expect_refused=False,
        answer_contains_any_of=[
            ["restricted", "nutraceutical", "supplement"],
        ],
        answer_must_not_contain=["you are approved", "your account is active", "welcome to acmepay"],
        must_cite_any_of=[["onboarding_playbook"]],
        skip_hedge_check=True,
        notes="TKT-207 scenario. Must reference restricted-category basis + appeal path; must NOT imply approval. skip_hedge_check: draft legitimately requests info from merchant; 'please provide'/'could you share' are content, not a hedge.",
    ),

    EvalCase(
        id="drafting_005",
        category="drafting",
        question="Draft a reply to Pinedrop about a UK customer who's upset they were 'charged extra' on a transaction. Clarify who actually pays the international surcharge.",
        expect_refused=False,
        answer_contains_all=["merchant"],
        answer_must_not_contain=[
            "surcharge is paid by the cardholder",
            "surcharge is paid by the customer",
            "cardholder pays the surcharge",
            "customer pays the surcharge",
            "the customer was charged extra",
        ],
        must_cite=["fees_and_pricing"],
        notes="TKT-205 scenario. TRAP: international surcharge falls on the MERCHANT; the customer is charged exactly the transaction amount.",
    ),

    EvalCase(
        id="drafting_006",
        category="drafting",
        question="Draft a reply to Lumen Travel, who wants to know when they'll move from extended settlement to standard T+2.",
        expect_refused=False,
        answer_contains_all=["0.7%"],
        answer_contains_any_of=[["6 month", "six month", "6+ month", "12 month",
                                 "6 or more", "six or more", "6 consecutive", "six consecutive",
                                 "6+ consecutive", "12 or more", "12+ month", "twelve month",
                                 "consecutive month"]],
        must_cite_any_of=[["chargeback_policy", "settlement_timing"]],
        notes="TKT-206 scenario. Move-off conditions: sustained <0.7% for 6+ months + 12+ months on platform.",
    ),

    EvalCase(
        id="drafting_007",
        category="drafting",
        question="Draft a reply to Stratoform confirming we refunded their duplicate subscription charge and noting whether a refund fee applies.",
        expect_refused=False,
        answer_contains_any_of=[["no refund fee", "no fee", "free", "refund fee: none", "not charged a fee"]],
        must_cite_any_of=[["fees_and_pricing"]],
        notes="TKT-202 scenario. Refund fee is None (but original processing fee not returned — not the focus here).",
    ),

    EvalCase(
        id="drafting_008",
        category="drafting",
        question="Draft guidance to send Bright Bean on how to respond to the fraud dispute on T-99815, including the deadline.",
        expect_refused=False,
        answer_contains_any_of=[["7 day", "7 calendar day", "7-day", "seven day"]],
        must_cite_any_of=[["chargeback_policy"]],
        skip_hedge_check=True,
        notes="TKT-201 scenario. Must state the 7-day response window + evidence guidance. skip_hedge_check: draft legitimately requests info from merchant; 'please provide'/'could you share' are content, not a hedge.",
    ),

    EvalCase(
        id="drafting_009",
        category="drafting",
        question="A merchant asks if they can get a partial refund on a transaction. Draft the reply.",
        expect_refused=False,
        answer_contains_any_of=[["not supported", "full", "full amount", "not currently"]],
        must_cite_any_of=[["merchant_faq", "api_reference"]],
        notes="Partial refunds not supported; refunds are full-amount only.",
    ),

    EvalCase(
        id="drafting_010",
        category="drafting",
        question="Draft a reply to a merchant asking whether winning a chargeback gets the $15 fee back.",
        expect_refused=False,
        answer_contains_any_of=[["non-refundable", "not refunded", "not returned", "stays gone"]],
        answer_must_not_contain=["fee is refunded", "fee is returned", "get the fee back"],
        must_cite=["chargeback_policy"],
        notes="Chargeback fee non-refundable even on a win.",
    ),

    EvalCase(
        id="drafting_011",
        category="drafting",
        question="Draft a reply to a Standard merchant now doing ~$70K/month asking whether they should switch to Pro and what changes.",
        expect_refused=False,
        answer_contains_any_of=[["2.4%", "2.4 percent"], ["$99", "99/month", "$99/mo"]],
        must_cite=["fees_and_pricing"],
        notes="Pro: 2.4% + $0.30, $99/month. Must give the actual Pro economics.",
    ),

    EvalCase(
        id="drafting_012",
        category="drafting",
        question="A merchant asks for instant settlement. Draft a short, honest reply.",
        expect_refused=False,
        answer_contains_any_of=[["not at this time", "not available", "roadmap", "not currently", "cannot offer"]],
        must_cite_any_of=[["merchant_faq"]],
        notes="Instant settlement not available; on roadmap. Must not promise it.",
    ),

    EvalCase(
        id="drafting_013",
        category="drafting",
        question="Draft a reply to Maple & Mortar about their failed payout — their bank account was closed. What should they do?",
        expect_refused=False,
        answer_contains_any_of=[["update", "banking details", "new account", "re-enter", "bank account"]],
        must_cite_any_of=[["settlement_timing", "merchant_faq"]],
        skip_hedge_check=True,
        notes="Failed payout: funds stay in balance, update banking, Acmepay retries within 24h. skip_hedge_check: draft legitimately requests info from merchant; 'please provide'/'could you share' are content, not a hedge.",
    ),
]
