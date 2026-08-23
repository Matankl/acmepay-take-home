"""Visible multi_doc_synthesis eval cases.

Authoring rule (locked, consistent with factual_lookup methodology):

    Every case must turn on a fact that lives in TWO OR MORE canonical docs
    and cannot be answered correctly from a single chunk. The discriminator is
    whether the system retrieves + fuses across documents, not whether it can
    read one fact off the page. `must_cite` therefore requires BOTH source docs
    (the grader ANDs `must_cite`), so a single-doc answer fails the citation
    check even if the prose token happens to match.

Composition (13 cases):
  - All require synthesis across >=2 policy docs.
  - Answer matchers are deterministic Acmepay-specific tokens (numbers, named
    thresholds), never tone-dependent prose.
  - Hedge enforcement is global (evals/schema.py): a hedged answer with
    refused=False fails regardless of token matches.

Every asserted fact traces to _internal/world.md + the policy docs.
"""
from __future__ import annotations

from .schema import EvalCase


CASES: list[EvalCase] = [

    EvalCase(
        id="multi_doc_synthesis_001",
        category="multi_doc_synthesis",
        question="A brand-new Standard-plan merchant just got approved. On a $200 card charge, what fee do they pay and when do the funds settle?",
        answer_contains_any_of=[
            ["2.9%", "2.9 percent"],
            ["t+5", "t + 5", "5 business days", "five business days"],
        ],
        answer_contains_all=["$0.30"],
        must_cite=["fees_and_pricing", "settlement_timing"],
        notes="Synthesis: per-transaction fee (fees_and_pricing) + new-merchant T+5 settlement (settlement_timing). Two any-of/all groups force both facts.",
    ),

    EvalCase(
        id="multi_doc_synthesis_002",
        category="multi_doc_synthesis",
        question="A customer files a chargeback on an $850 charge. What gets debited right away, and if the merchant wins, what comes back and what doesn't?",
        answer_contains_all=["$15"],
        answer_contains_any_of=[
            ["60-75", "60–75", "60 to 75", "60 - 75"],
            ["non-refundable", "not refunded", "not returned", "stays gone"],
        ],
        must_cite_any_of=[["chargeback_policy", "fees_and_pricing"]],
        notes="Synthesis: $15 chargeback fee (fees_and_pricing) + funds-handling/60-75 day return + fee non-refundable (chargeback_policy).",
    ),

    EvalCase(
        id="multi_doc_synthesis_003",
        category="multi_doc_synthesis",
        question="Lumen Travel is on extended settlement because they're high-risk. What settlement schedule and reserve are they on, and what would it take to move them to standard T+2?",
        answer_contains_any_of=[
            ["t+5", "t + 5", "5 business days"],
            ["15%", "15 percent"],
        ],
        answer_contains_all=["0.7%"],
        must_cite=["settlement_timing", "chargeback_policy"],
        notes="Synthesis: high-risk T+5 + 15% reserve (settlement_timing) + the move-off conditions sustained <0.7% for 6+ months (chargeback_policy).",
    ),

    EvalCase(
        id="multi_doc_synthesis_004",
        category="multi_doc_synthesis",
        question="A nutraceutical supplement company wants to sell through Acmepay. Can they onboard normally, and if they get in through review, what terms do they start on?",
        answer_contains_any_of=[
            ["restricted", "rejected", "not accepted", "not onboarded", "prohibited"],
            ["t+5", "t + 5", "15%", "pro plan", "extended settlement"],
        ],
        must_cite=["onboarding_playbook"],
        notes="Synthesis: nutraceuticals restricted/appeal -> Pro + T+5 + 15% (onboarding_playbook) + the high-risk settlement config (settlement_timing).",
    ),

    EvalCase(
        id="multi_doc_synthesis_005",
        category="multi_doc_synthesis",
        question="A merchant got a chargeback ratio warning. At what ratio did that trigger, and is there an API event I can subscribe to so I catch the next one automatically?",
        answer_contains_all=["1.0%"],
        answer_contains_any_of=[["account.warning_issued", "warning_issued"]],
        must_cite=["chargeback_policy", "api_reference"],
        notes="Synthesis: 1.0% monitoring threshold (chargeback_policy) + account.warning_issued webhook (api_reference).",
    ),

    EvalCase(
        id="multi_doc_synthesis_006",
        category="multi_doc_synthesis",
        question="A chargeback was just filed. How long does the merchant have to respond, and which API endpoint do they use to submit the evidence?",
        answer_contains_any_of=[["7 day", "7 calendar day", "7-day", "seven day"]],
        answer_contains_all=["/v1/disputes"],
        must_cite=["chargeback_policy", "api_reference"],
        notes="Synthesis: 7-day response window (chargeback_policy) + /v1/disputes/{id}/evidence endpoint (api_reference).",
    ),

    EvalCase(
        id="multi_doc_synthesis_007",
        category="multi_doc_synthesis",
        question="When should a merchant move from Standard to Pro, and once they do, what settlement perk can they request?",
        answer_contains_any_of=[["$50,000", "$50k", "50,000", "50k"]],
        answer_contains_all=["weekly"],
        must_cite=["fees_and_pricing", "settlement_timing"],
        notes="Synthesis: Pro at $50K/mo (fees_and_pricing) + Pro weekly batch settlement (settlement_timing).",
    ),

    EvalCase(
        id="multi_doc_synthesis_008",
        category="multi_doc_synthesis",
        question="A merchant fully refunds a $100 charge. Is there a refund fee, what happens to the processing fee already taken, and which endpoint issues the refund?",
        answer_contains_any_of=[
            ["not returned", "not refunded", "is kept", "acmepay keeps", "non-refundable", "is retained"],
        ],
        answer_contains_all=["/v1/refunds"],
        answer_must_not_contain=["may be credited", "manually credited"],
        must_cite=["fees_and_pricing", "api_reference"],
        notes="Synthesis: no refund fee but original fee kept (fees_and_pricing) + /v1/refunds endpoint (api_reference). Forbids carry the additive-fabrication guard from factual_lookup_001.",
    ),

    EvalCase(
        id="multi_doc_synthesis_009",
        category="multi_doc_synthesis",
        question="A new low-risk merchant is on day 30. What settlement and reserve are they on now, and what happens at day 90 if there are no risk events?",
        answer_contains_any_of=[
            ["t+5", "t + 5", "5 business days"],
            ["10%", "10 percent"],
        ],
        answer_contains_all=["t+2"],
        must_cite_any_of=[["settlement_timing", "onboarding_playbook"]],
        notes="Synthesis across the new-merchant lifecycle: T+5 + 10% now, auto-transition to T+2 at 90 days. Both source docs describe it; either citation is acceptable for the boundary fact but the answer must fuse current + future state.",
    ),

    EvalCase(
        id="multi_doc_synthesis_010",
        category="multi_doc_synthesis",
        question="A merchant's payout failed because their bank account was closed. Where do the funds sit, how fast does Acmepay retry, and can they update banking themselves?",
        answer_contains_any_of=[["24 hour", "24-hour", "24h", "within 24"]],
        answer_contains_all=["balance"],
        must_cite_any_of=[["settlement_timing", "merchant_faq"]],
        notes="Synthesis: failed-settlement handling, funds stay in Acmepay balance + 24h retry (settlement_timing) + self-serve banking change (merchant_faq).",
    ),

    EvalCase(
        id="multi_doc_synthesis_011",
        category="multi_doc_synthesis",
        question="What's the difference between a refund and a chargeback in terms of cost to the merchant and impact on their chargeback ratio?",
        answer_contains_all=["$15"],
        answer_contains_any_of=[["only chargebacks", "do not count", "don't count", "not count against", "refunds don't", "refunds do not"]],
        must_cite_any_of=[["merchant_faq", "chargeback_policy", "fees_and_pricing"]],
        notes="Synthesis: $15 chargeback fee (fees_and_pricing/chargeback_policy) + refunds don't affect ratio (merchant_faq). At least one of the three source docs must be cited.",
    ),

    EvalCase(
        id="multi_doc_synthesis_012",
        category="multi_doc_synthesis",
        question="A merchant crossed 1.5% chargebacks. What can happen to their account at that level, and how does that compare to the 1.0% threshold?",
        answer_contains_all=["1.5%", "1.0%"],
        answer_contains_any_of=[["suspension", "account hold", "suspend", "hold"]],
        must_cite=["chargeback_policy"],
        notes="Within-doc multi-hop: contrasts the two thresholds and their consequences. Single doc but requires fusing two separated sections; kept here as a synthesis floor case.",
    ),

    EvalCase(
        id="multi_doc_synthesis_013",
        category="multi_doc_synthesis",
        question="An international card is used for a $200 charge on the Standard plan. What total fee does the merchant pay, and who actually bears the surcharge?",
        answer_contains_all=["merchant"],
        answer_contains_any_of=[["1.5%", "1.5 percent"]],
        answer_must_not_contain=[
            "surcharge is paid by the cardholder",
            "surcharge is paid by the customer",
            "cardholder pays the surcharge",
            "customer pays the surcharge",
        ],
        must_cite=["fees_and_pricing"],
        notes="Fee arithmetic + direction-of-surcharge. Single doc (fees_and_pricing) but combines base fee + international surcharge + payer; synthesis floor case.",
    ),
]
