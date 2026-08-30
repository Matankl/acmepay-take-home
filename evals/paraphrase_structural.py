"""Held-out proxy: STRUCTURAL paraphrases.

Same facts, different question shape. These target control flow rather than
wording: reaching a record indirectly through another record, asking two things
at once, inverting a question so the answer has to be recomputed rather than
recalled, and the aggregation cases re-graded with tight matchers.

The tightened aggregation matchers are the point of this file. In the visible
suite those cases can pass on a bare substring -- any mention of an `M-10xx`
identifier satisfies a required "10", and `M-1004` satisfies a required "4" -- so
a visible pass there is not evidence the aggregation works. Here the phrasing has
to carry the unit.
"""
from __future__ import annotations

from .schema import EvalCase, ToolCallExpectation as Call

CASES: list[EvalCase] = [

    EvalCase(
        id="px_str_001",
        category="investigation",
        question="Take the $1,200 charge T-99818 - is the dispute against it still "
                 "something we can fight?",
        expect_refused=False,
        must_call_tools=[Call("lookup_transaction", {"txn_id": "T-99818"})],
        answer_contains_any_of=[
            ["d-503"],
            ["closed", "past", "missed", "expired", "too late", "2026-05-22",
             "automatically lost", "no longer"],
        ],
        answer_must_not_contain=["still actionable", "still have time", "on track"],
        notes="Indirect reference: the dispute is never named. Requires hopping "
              "transaction -> merchant -> disputes, which the transitive gate has "
              "to allow because the question is causal, not a field read.",
        paraphrase_strategy="structural", paraphrase_of="investigation_001",
    ),
    EvalCase(
        id="px_str_002",
        category="investigation",
        question="Which merchant leads the platform on failed payouts this month, "
                 "and how many did they have?",
        expect_refused=False,
        answer_contains_any_of=[
            ["m-1012", "cobble & crane", "cobble and crane"],
            ["4 failed", "4 payout", "four failed", "four payout"],
        ],
        notes="Tightened matcher: the visible version accepts a bare '4', which any "
              "mention of M-1004 satisfies. Here the number has to carry its unit.",
        paraphrase_strategy="structural", paraphrase_of="investigation_014",
    ),
    EvalCase(
        id="px_str_003",
        category="investigation",
        question="Count the disputes where the response window is still open and no "
                 "evidence has gone in yet.",
        expect_refused=False,
        answer_contains_any_of=[["10 dispute", "10 active", "ten dispute", "ten active"]],
        notes="Tightened matcher: the visible version accepts a bare '10', which any "
              "M-10xx identifier satisfies. 'Active' means the window has not "
              "closed, so the past-due dispute is excluded.",
        paraphrase_strategy="structural", paraphrase_of="investigation_015",
    ),
    EvalCase(
        id="px_str_004",
        category="investigation",
        question="Across the whole book, which unresolved dispute carries the most "
                 "money, and what is the figure?",
        expect_refused=False,
        answer_contains_all=["d-512"],
        answer_contains_any_of=[["2,450", "2450"]],
        notes="Bigger than the much-discussed canonical dispute. A system that only "
              "knows the story merchants answers this wrong.",
        paraphrase_strategy="structural", paraphrase_of="investigation_018",
    ),
    EvalCase(
        id="px_str_005",
        category="investigation",
        question="Name every merchant sitting on or above our chargeback monitoring "
                 "line right now.",
        expect_refused=False,
        answer_contains_all=["m-1003"],
        answer_contains_any_of=[["m-1030", "vantage"]],
        answer_must_not_contain=["m-1025", "halcyon", "m-1002", "stratoform"],
        notes="The near-misses at 0.9% and 0.8% must not appear. Forbidding two of "
              "them, not one, so a full-table dump cannot slip through.",
        paraphrase_strategy="structural", paraphrase_of="investigation_016",
    ),
    EvalCase(
        id="px_str_006",
        category="multi_doc_synthesis",
        question="Two things for a merchant we just approved on the entry-level "
                 "plan: what do we take off a $200 card sale, and when does the "
                 "money actually land?",
        answer_contains_all=["$0.30"],
        answer_contains_any_of=[
            ["2.9%"],
            ["t+5", "5 business days", "five business days"],
        ],
        must_cite=["fees_and_pricing", "settlement_timing"],
        notes="Multi-part question; both source documents are required by AND.",
        paraphrase_strategy="structural", paraphrase_of="multi_doc_synthesis_001",
    ),
    EvalCase(
        id="px_str_007",
        category="investigation",
        question="Does Bright Bean have any breathing room left on D-502, or has "
                 "that one already gone?",
        expect_refused=False,
        must_call_tools=[Call("get_dispute", {"dispute_id": "D-502"})],
        answer_contains_any_of=[["2026-05-30", "05-30", "may 30", "5 day", "five day"]],
        answer_must_not_contain=["overdue", "already lost", "deadline has passed",
                                 "past due"],
        notes="Inverted framing invites the wrong verdict, and the bare word "
              "'overdue' is forbidden -- so 'not overdue' fails and the answer has "
              "to state the actual position instead.",
        paraphrase_strategy="structural", paraphrase_of="investigation_012",
    ),
    EvalCase(
        id="px_str_008",
        category="tool_use",
        question="I need the fee and the currency for T-99830, nothing else.",
        must_call_tools=[Call("lookup_transaction", {"txn_id": "T-99830"})],
        forbidden_tools=["lookup_merchant", "search_policies"],
        notes="Single-record field read: the transitive gate must suppress the hop "
              "to the owning merchant even though the record names one.",
        paraphrase_strategy="structural", paraphrase_of="tool_use_010",
    ),
]
