"""Visible tool_use eval cases.

Authoring rule:

    A tool_use case turns on calling the RIGHT structured tool with the RIGHT
    arguments. The grader matches each ToolCallExpectation by tool name + an
    args subset (exact key/value). The starter only ever calls
    lookup_transaction, so every case that needs another tool fails on the
    baseline by construction.

Tool signatures (tools/__init__.py):
    lookup_transaction(txn_id)            lookup_merchant(merchant_id)
    list_disputes(merchant_id)            get_dispute(dispute_id)
    list_recent_tickets(merchant_id)      get_ticket(ticket_id)
    read_audit_log(merchant_id, since=, event_type=)
    search_policies(query, top_k=)

Cases that assert an arg value use an explicit ID in the question so grading is
deterministic (no name->ID resolution dependency). Cases phrased with a
merchant *name* assert the tool name only. forbidden_tools guards against
spurious extra calls. All IDs trace to _internal/world.md.
"""
from __future__ import annotations

from .schema import EvalCase, ToolCallExpectation as Call


CASES: list[EvalCase] = [

    EvalCase(
        id="tool_use_001",
        category="tool_use",
        question="What's the current status of transaction T-99815?",
        must_call_tools=[Call("lookup_transaction", {"txn_id": "T-99815"})],
        notes="Direct lookup_transaction. Even the starter can pass this — category floor.",
    ),

    EvalCase(
        id="tool_use_002",
        category="tool_use",
        question="What plan and account status is merchant M-1003 on?",
        must_call_tools=[Call("lookup_merchant", {"merchant_id": "M-1003"})],
        forbidden_tools=["lookup_transaction"],
        notes="Requires lookup_merchant — starter never calls it.",
    ),

    EvalCase(
        id="tool_use_003",
        category="tool_use",
        question="List the open disputes on merchant M-1003's account.",
        must_call_tools=[Call("list_disputes", {"merchant_id": "M-1003"})],
        notes="list_disputes by merchant.",
    ),

    EvalCase(
        id="tool_use_004",
        category="tool_use",
        question="Pull the full details of dispute D-503.",
        must_call_tools=[Call("get_dispute", {"dispute_id": "D-503"})],
        notes="get_dispute by id. D-503 is the overdue one (investigation-relevant downstream).",
    ),

    EvalCase(
        id="tool_use_005",
        category="tool_use",
        question="What recent support tickets exist for merchant M-1001?",
        must_call_tools=[Call("list_recent_tickets", {"merchant_id": "M-1001"})],
        notes="list_recent_tickets by merchant.",
    ),

    EvalCase(
        id="tool_use_006",
        category="tool_use",
        question="Open ticket TKT-203 and tell me what it's about.",
        must_call_tools=[Call("get_ticket", {"ticket_id": "TKT-203"})],
        notes="get_ticket by id.",
    ),

    EvalCase(
        id="tool_use_007",
        category="tool_use",
        question="Show me the payout_failed events in merchant M-1004's audit log.",
        must_call_tools=[Call("read_audit_log", {"merchant_id": "M-1004"})],
        notes="read_audit_log with event_type filter. M-1004 had a payout_failed (closed bank account).",
    ),

    EvalCase(
        id="tool_use_008",
        category="tool_use",
        question="When was the chargeback ratio warning logged for merchant M-1003?",
        must_call_tools=[Call("read_audit_log", {"merchant_id": "M-1003"})],
        notes="read_audit_log with event_type. M-1003 hit 1.3%, warning logged 2026-05-19.",
    ),

    EvalCase(
        id="tool_use_009",
        category="tool_use",
        question="Look up merchant M-1006 and tell me their account status.",
        must_call_tools=[Call("lookup_merchant", {"merchant_id": "M-1006"})],
        notes="M-1006 (Verdant Wellness) was rejected and is NOT in merchants.json. The correct move is still to call lookup_merchant; handling the not-found result is graded in investigation.",
    ),

    EvalCase(
        id="tool_use_010",
        category="tool_use",
        question="What's the amount and currency on transaction T-99830?",
        must_call_tools=[Call("lookup_transaction", {"txn_id": "T-99830"})],
        forbidden_tools=["lookup_merchant", "search_policies"],
        notes="Single-tool answer; forbid spurious merchant/policy calls.",
    ),

    EvalCase(
        id="tool_use_011",
        category="tool_use",
        question="List the disputes filed against merchant M-1001.",
        must_call_tools=[Call("list_disputes", {"merchant_id": "M-1001"})],
        notes="list_disputes by merchant.",
    ),

    EvalCase(
        id="tool_use_012",
        category="tool_use",
        question="Get me dispute D-501's reason code and response deadline.",
        must_call_tools=[Call("get_dispute", {"dispute_id": "D-501"})],
        notes="get_dispute by id.",
    ),

    EvalCase(
        id="tool_use_013",
        category="tool_use",
        question="Show all of merchant M-1003's audit-log activity since 2026-05-15.",
        must_call_tools=[Call("read_audit_log", {"merchant_id": "M-1003"})],
        notes="read_audit_log with since filter.",
    ),
]
