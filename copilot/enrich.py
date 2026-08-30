"""Derived fields, computed deterministically at the tool boundary.

The model reads facts; it never derives them. Date deltas against a frozen
today, threshold-band comparisons and counting are all single-correct-answer
computations, and a small model is unreliable at every one of them.

One rule governs the field *names*: never name the negative condition. A payload
carrying `is_overdue: false` teaches the model to write "not overdue", and
introducing an adverse label in order to deny it is both bad support writing and
a trap. So states are named positively -- `deadline_state: "open"` -- and the
raw ISO date is always restated alongside any computed day count.
"""
from __future__ import annotations

import json
from datetime import date
from functools import lru_cache

from .config import DATA, TODAY, TODAY_ISO
from .text import pct, usd

MONITORING = 0.010
SUSPENSION = 0.015
NEW_MERCHANT_DAYS = 90
DISPUTE_RESPONSE_DAYS = 7

# Every derived value in this package has to pass one test: its definition
# traces to a policy document or a schema field, never to an eval assertion.
# This table is that trace, machine-checked by evals/check_provenance.py -- if
# the policy text changes, the check fails instead of the system silently
# drifting onto a stale threshold.
#
# Note what is deliberately absent: nothing keyed to a particular calendar date
# or a particular merchant. A field pre-filtered to "due on or before <date>"
# would encode a question rather than a policy, so the digest ships signed day
# counts and lets the question supply its own bound.
PROVENANCE = {
    "MONITORING": (
        "chargeback_policy.md",
        "Excessive Chargebacks",
        "at or above 1.0% triggers automated email warnings",
    ),
    "SUSPENSION": (
        "chargeback_policy.md",
        "Excessive Chargebacks",
        "at or above 1.5% may result in account hold",
    ),
    "NEW_MERCHANT_DAYS": (
        "settlement_timing.md",
        "New Merchant Settlement",
        "For the first **90 days** after Acmepay approval",
    ),
    "DISPUTE_RESPONSE_DAYS": (
        "chargeback_policy.md",
        "Merchant Response Window",
        "you have **7 calendar days** from notification",
    ),
}


def _d(iso: str) -> date:
    return date.fromisoformat(iso[:10])


def days_from_today(iso: str) -> int:
    return (_d(iso) - TODAY).days


def risk_band(ratio: float) -> str:
    if ratio >= SUSPENSION:
        return "suspension_review"
    if ratio >= MONITORING:
        return "monitoring"
    return "ok"


@lru_cache(maxsize=1)
def _merchants() -> dict:
    return json.loads((DATA / "merchants.json").read_text())


def merchant_name(merchant_id: str) -> str | None:
    rec = _merchants().get(merchant_id)
    return rec["name"] if rec else None


def merchant(merchant_id: str, raw: dict) -> dict:
    if not raw or raw.get("error"):
        return dict(raw or {})
    signup_age = -days_from_today(raw["signup_date"])
    ratio = raw.get("chargeback_ratio_30d", 0.0)
    out = dict(raw)
    out["merchant_id"] = merchant_id
    out["chargeback_ratio_30d_pct"] = pct(ratio)
    out["risk_band"] = risk_band(ratio)
    out["monitoring_threshold_pct"] = pct(MONITORING)
    out["suspension_threshold_pct"] = pct(SUSPENSION)
    out["days_since_signup"] = signup_age
    if signup_age < NEW_MERCHANT_DAYS:
        out["new_merchant_window"] = "inside"
        out["new_merchant_window_ends"] = date.fromordinal(
            _d(raw["signup_date"]).toordinal() + NEW_MERCHANT_DAYS
        ).isoformat()
    else:
        out["new_merchant_window"] = "graduated"
    out["rolling_reserve_pct_display"] = pct(raw.get("rolling_reserve_pct", 0.0))
    return out


def dispute(dispute_id: str, raw: dict) -> dict:
    if not raw or raw.get("error"):
        return dict(raw or {})
    out = dict(raw)
    # disputes.json is keyed by ID and the value does not repeat it; get_dispute
    # returns the bare value, so the ID has to be put back.
    out["dispute_id"] = dispute_id
    days = days_from_today(raw["response_due"])
    out["response_due"] = raw["response_due"]
    out["days_to_response_due"] = days
    if raw.get("evidence_submitted"):
        out["deadline_state"] = "evidence_filed"
    elif days < 0:
        out["deadline_state"] = "past_due"
        out["days_since_due"] = -days
    else:
        out["deadline_state"] = "open"
        out["days_remaining"] = days
    out["disputed_amount"] = usd(raw["disputed_amount_cents"])
    # The window length itself, so a reply can state the figure without having to
    # re-derive it from the policy prose. Provenance-checked like every other
    # threshold: chargeback_policy.md > Merchant Response Window.
    out["response_window"] = f"{DISPUTE_RESPONSE_DAYS} calendar days from notification"
    name = merchant_name(raw.get("merchant_id", ""))
    if name:
        out["merchant_name"] = name
    out["today"] = TODAY_ISO
    return out


def transaction(txn_id: str, raw: dict) -> dict:
    if not raw or raw.get("error"):
        return dict(raw or {})
    out = dict(raw)
    out["txn_id"] = txn_id
    out["amount"] = usd(raw["amount_cents"])
    name = merchant_name(raw.get("merchant_id", ""))
    if name:
        out["merchant_name"] = name
    return out


def audit_events(events: list[dict]) -> list[dict]:
    out = []
    for ev in events or []:
        row = dict(ev)
        row["days_ago"] = -days_from_today(ev["timestamp"])
        out.append(row)
    return out
