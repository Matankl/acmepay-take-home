"""Visible investigation eval cases.

Authoring rule:

    An investigation case requires pulling structured records (tools) AND
    reaching the correct conclusion about them. We grade the right tool call(s)
    + the correct conclusion token, and forbid the known wrong conclusions.
    These cases encode the "traps" the world was built around.

Trap inventory (_internal/world.md, "today" = 2026-05-25):
    - D-503 (T-99818, M-1003): filed 05-15, response_due 05-22 -> OVERDUE.
      TKT-208 was closed BEFORE the window expired, so a lazy read says "fine".
    - M-1003: 1.3% chargeback ratio -> 1.0% MONITORING band, NOT 1.5% suspension.
    - M-1006 (Verdant Wellness): REJECTED nutraceuticals, NOT in merchants.json.
    - M-1004: signup 2026-03-10 -> still in 90-day new-merchant T+5 + 10% window.
    - T-99999: does not exist (not-found handling).

expect_refused=False throughout; hedge enforcement is global, so a vague
"I can't tell" with refused=False fails — investigation must commit.
"""
from __future__ import annotations

from .schema import EvalCase, ToolCallExpectation as Call


CASES: list[EvalCase] = [

    EvalCase(
        id="investigation_001",
        category="investigation",
        question="A merchant says dispute D-503 is handled. Is it actually still actionable, or did we miss the window?",
        expect_refused=False,
        must_call_tools=[Call("get_dispute", {"dispute_id": "D-503"})],
        answer_contains_any_of=[
            ["overdue", "past", "missed", "deadline has passed", "deadline passed",
             "expired", "too late", "automatically lost", "no longer", "2026-05-22"],
        ],
        answer_must_not_contain=["still actionable", "still have time", "on track", "not yet due"],
        notes="D-503 trap. Filed 05-15, due 05-22, today 05-25 -> overdue. Must read response_due, not trust TKT-208's stale 'handled'.",
    ),

    EvalCase(
        id="investigation_002",
        category="investigation",
        question="Is Lumen Travel about to be suspended over their chargeback rate?",
        expect_refused=False,
        must_call_tools=[Call("lookup_merchant", {"merchant_id": "M-1003"})],
        answer_contains_any_of=[["1.0%", "monitoring", "not", "no"]],
        answer_must_not_contain=["will be suspended", "suspension is imminent"],
        notes="M-1003 trap: 1.3% is in the 1.0% monitoring band, NOT the 1.5% suspension band. False alarm fails.",
    ),

    EvalCase(
        id="investigation_003",
        category="investigation",
        question="Pull up Verdant Wellness and tell me what settlement schedule they're on.",
        expect_refused=False,
        must_call_tools=[Call("lookup_merchant", {"merchant_id": "M-1006"})],
        answer_contains_any_of=[
            ["not a merchant", "not on the platform", "rejected", "no account", "not found",
             "does not exist", "doesn't exist", "no record", "not onboarded"],
        ],
        answer_must_not_contain=["t+5", "t+2", "10% reserve", "15% reserve", "on extended settlement"],
        notes="M-1006 trap: rejected nutraceuticals applicant, NOT in merchants.json. Must not fabricate a settlement schedule for a non-merchant.",
    ),

    EvalCase(
        id="investigation_004",
        category="investigation",
        question="Why is Maple & Mortar's payout on a T+5 schedule instead of T+2?",
        expect_refused=False,
        must_call_tools=[Call("lookup_merchant", {"merchant_id": "M-1004"})],
        answer_contains_any_of=[
            ["new merchant", "new-merchant", "90 day", "90-day", "first 90", "within the 90"],
        ],
        answer_must_not_contain=["because they are high-risk", "high-risk category", "high-risk merchant", "classified as high-risk", "suspended", "extended settlement indefinite"],
        notes="M-1004 trap: brand-new merchant (signup 2026-03-10, ~76 days) still in the 90-day window. NOT high-risk.",
    ),

    EvalCase(
        id="investigation_005",
        category="investigation",
        question="Does Lumen Travel have any disputes that are past their response deadline?",
        expect_refused=False,
        must_call_tools=[Call("list_disputes", {"merchant_id": "M-1003"})],
        answer_contains_any_of=[["d-503", "yes", "overdue", "past", "2026-05-22"]],
        answer_must_not_contain=["none are past", "no disputes are past", "all within window", "nothing overdue", "still actionable"],
        notes="Requires listing disputes and comparing response_due to today. D-503 (due 05-22) is overdue.",
    ),

    EvalCase(
        id="investigation_006",
        category="investigation",
        question="What's the status of transaction T-99999?",
        expect_refused=False,
        must_call_tools=[Call("lookup_transaction", {"txn_id": "T-99999"})],
        answer_contains_any_of=[
            ["not found", "does not exist", "doesn't exist", "no such", "no record", "no transaction"],
        ],
        notes="Not-found handling. T-99999 does not exist; must not fabricate a status.",
    ),

    EvalCase(
        id="investigation_007",
        category="investigation",
        question="Maple & Mortar's payout didn't go through. Find out why.",
        expect_refused=False,
        must_call_tools=[Call("read_audit_log", {"merchant_id": "M-1004"})],
        answer_contains_any_of=[["closed", "bank account", "banking", "routing", "retry"]],
        notes="M-1004 payout_failed: closed bank account, retry pending (audit log 2026-05-22).",
    ),

    EvalCase(
        id="investigation_008",
        category="investigation",
        question="Which of Lumen Travel's disputes need action from us this week, and which is already blown?",
        expect_refused=False,
        must_call_tools=[Call("list_disputes", {"merchant_id": "M-1003"})],
        answer_contains_all=["d-503"],
        answer_contains_any_of=[
            ["d-501"],
            ["overdue", "blown", "missed", "past due", "2026-05-22", "lost"],
        ],
        answer_must_not_contain=["nothing is blown", "both are still actionable", "all within window"],
        notes="D-501 due 05-27 (this week, actionable); D-503 due 05-22 (overdue/blown). Requires per-dispute deadline reasoning.",
    ),

    EvalCase(
        id="investigation_009",
        category="investigation",
        question="When did Lumen Travel cross into the chargeback monitoring zone, and what ratio triggered it?",
        expect_refused=False,
        must_call_tools=[Call("read_audit_log", {"merchant_id": "M-1003"})],
        answer_contains_any_of=[["1.3%", "2026-05-19", "05-19", "may 19"]],
        notes="chargeback_ratio_warning for M-1003 logged 2026-05-19 at 1.3%.",
    ),

    EvalCase(
        id="investigation_010",
        category="investigation",
        question="How many active disputes does Lumen Travel currently have?",
        expect_refused=False,
        must_call_tools=[Call("list_disputes", {"merchant_id": "M-1003"})],
        answer_contains_any_of=[["2 active", "two active", "2 disputes", "two disputes"]],
        answer_must_not_contain=["3 active", "three active", "1 active", "one active"],
        notes="M-1003 has 2 active disputes: D-501 and D-503.",
    ),

    EvalCase(
        id="investigation_011",
        category="investigation",
        question="Is Verdant Wellness an active merchant on Acmepay right now?",
        expect_refused=False,
        must_call_tools=[Call("lookup_merchant", {"merchant_id": "M-1006"})],
        answer_contains_any_of=[
            ["no", "not", "rejected", "not on the platform", "not a merchant", "no account"],
        ],
        notes="M-1006 rejected 2026-05-18; not an active merchant. Mirrors investigation_003 from the membership angle.",
    ),

    EvalCase(
        id="investigation_012",
        category="investigation",
        question="How long does Bright Bean still have to respond on dispute D-502?",
        expect_refused=False,
        must_call_tools=[Call("get_dispute", {"dispute_id": "D-502"})],
        answer_contains_any_of=[["2026-05-30", "05-30", "may 30", "5 day", "five day"]],
        answer_must_not_contain=["overdue", "already lost", "deadline has passed"],
        notes="D-502 (T-99815, M-1001) due 05-30 — still open, NOT overdue. Contrast to D-503.",
    ),

    EvalCase(
        id="investigation_013",
        category="investigation",
        question="Walk the history on Lumen Travel since mid-May and tell me if anything needs follow-up.",
        expect_refused=False,
        must_call_tools=[Call("read_audit_log", {"merchant_id": "M-1003"})],
        answer_contains_any_of=[["dispute", "warning", "d-503", "overdue", "follow"]],
        answer_must_not_contain=["nothing needs follow-up", "no follow-up needed", "everything looks fine"],
        notes="Open-ended investigation: audit since 05-15 surfaces dispute_filed + chargeback_ratio_warning; D-503 needs follow-up.",
    ),

    # ---- AGGREGATION cases (added with the data scale-up) ----------------------
    # Answers computed by _internal/generate_data.py — see _internal/generated_facts.json.
    # Do NOT hand-edit the expected values; regenerate the data instead.

    EvalCase(
        id="investigation_014",
        category="investigation",
        question="Which merchant has had the most failed payouts this month, and how many?",
        expect_refused=False,
        answer_contains_any_of=[["m-1012", "cobble & crane", "cobble and crane"],
                                ["4", "four"]],
        notes="Aggregation (generated_facts.most_failed_payouts): M-1012 Cobble & Crane Antiques with 4 payout_failed events (invalid routing number); runner-ups M-1004 and M-1020 have 1 each — M-1020's was even retried successfully (red herring). Requires iterating read_audit_log per merchant or an equivalent sweep.",
    ),

    EvalCase(
        id="investigation_015",
        category="investigation",
        question="How many active disputes still need evidence submitted and have their response due on or before 2026-05-31?",
        expect_refused=False,
        answer_contains_any_of=[["10", "ten"]],
        notes="Aggregation (generated_facts.open_disputes_due_by_2026_05_31): exactly 10 (D-501, D-502, D-504, D-506, D-507, D-509, D-510, D-512, D-513, D-515). Precise phrasing on purpose: excludes evidence_submitted=true disputes and the overdue D-503.",
    ),

    EvalCase(
        id="investigation_016",
        category="investigation",
        question="Which merchants are currently at or above the 1.0% chargeback monitoring threshold?",
        expect_refused=False,
        answer_contains_all=["m-1003"],
        answer_contains_any_of=[["m-1030", "vantage"]],
        answer_must_not_contain=["m-1025", "halcyon"],
        notes="Aggregation (generated_facts.merchants_at_or_above_monitoring_1pct): exactly M-1003 (1.3%) and M-1030 (1.6%, suspended). M-1025 Halcyon at 0.9% is the deliberate near-miss and must NOT be listed.",
    ),

    EvalCase(
        id="investigation_017",
        category="investigation",
        question="How many active disputes does Vantage Getaways have on file?",
        expect_refused=False,
        must_call_tools=[Call("list_disputes", {"merchant_id": "M-1030"})],
        answer_contains_any_of=[["1 dispute", "one dispute", "1 active", "one active", "single dispute", "a single active"]],
        answer_must_not_contain=["no disputes", "0 disputes", "zero disputes"],
        notes="Aggregation over a non-canonical merchant (generated_facts.dispute_counts_by_merchant): M-1030 has exactly 1 (D-507). Tests name->ID resolution beyond the original five merchants.",
    ),

    EvalCase(
        id="investigation_018",
        category="investigation",
        question="Across all merchants, which open dispute has the largest amount at stake, and how much is it?",
        expect_refused=False,
        answer_contains_all=["d-512"],
        answer_contains_any_of=[["2,450", "2450", "245,000", "245000"]],
        notes="Aggregation (generated_facts.largest_open_dispute): D-512, $2,450.00 (245000 cents), M-1034 Trailhead Provisions. Bigger than the canonical D-503 ($1,200) — a system that only knows the canonical disputes gets this wrong.",
    ),
]
