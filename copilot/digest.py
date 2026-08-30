"""The dataset digest: a deterministic, always-in-context view of the portfolio.

`read_audit_log` is hard-scoped to a single merchant by design, so any
cross-merchant question would otherwise need 34 tool calls plus arithmetic in the
model. The digest replaces both with pre-derived rows.

Two shaping decisions matter as much as the content:

* **Bands, not raw ratios.** A merchant just below the monitoring threshold lands
  in `ok`, so it is *structurally absent* from any "at or above 1.0%" answer
  rather than being a near-miss the model has to remember to leave out. Exact
  ratios still reach the model for merchants the question actually names -- via
  the tool result, where they belong.
* **No volume or category columns.** An always-on roster carrying volumes and
  recognisable brand names is exactly the material that makes "list the other
  merchants in this category with their volumes" answerable -- and that request
  should be declined. There is no category field and no bulk-listing tool; the
  digest must not erode that floor.

The provenance test every field here has to pass: *its definition traces to a
policy document or a schema field, never to an eval assertion.* So
`days_to_response_due` ships and the model applies whatever bound the question
states; a field pre-filtered to a specific calendar date would not.
"""
from __future__ import annotations

import json
from collections import Counter
from functools import lru_cache

from .config import DATA, TODAY, TODAY_ISO
from .enrich import MONITORING, SUSPENSION, days_from_today, risk_band
from .text import pct, usd

_NON_ROUTINE = (
    "payout_failed",
    "chargeback_ratio_warning",
    "merchant_suspended",
    "merchant_rejected",
    "appeal_filed",
    "transaction_refunded",
    "dispute_filed",
)


@lru_cache(maxsize=1)
def _load():
    merchants = json.loads((DATA / "merchants.json").read_text())
    disputes = json.loads((DATA / "disputes.json").read_text())
    events = [
        json.loads(line)
        for line in (DATA / "audit_log.jsonl").read_text().splitlines()
        if line.strip()
    ]
    return merchants, disputes, events


def _name(mid: str) -> str:
    merchants, _, _ = _load()
    rec = merchants.get(mid)
    return rec["name"] if rec else "(no merchant record)"


@lru_cache(maxsize=1)
def dispute_rows() -> tuple[dict, ...]:
    _, disputes, _ = _load()
    rows = []
    for did, d in sorted(disputes.items()):
        days = days_from_today(d["response_due"])
        if d["evidence_submitted"]:
            state = "evidence_filed"
        elif days < 0:
            state = "past_due"
        else:
            state = "open"
        rows.append({
            "dispute_id": did,
            "merchant_id": d["merchant_id"],
            "merchant": _name(d["merchant_id"]),
            "transaction_id": d["transaction_id"],
            "filed_at": d["filed_at"],
            "reason_code": d["reason_code"],
            "response_due": d["response_due"],
            "days_to_response_due": days,
            "evidence_submitted": d["evidence_submitted"],
            "amount": usd(d["disputed_amount_cents"]),
            "amount_cents": d["disputed_amount_cents"],
            "deadline_state": state,
        })
    return tuple(rows)


@lru_cache(maxsize=1)
def merchant_rows() -> tuple[dict, ...]:
    merchants, _, _ = _load()
    rows = []
    for mid, m in sorted(merchants.items()):
        age = -days_from_today(m["signup_date"])
        rows.append({
            "merchant_id": mid,
            "name": m["name"],
            "plan": m["plan"],
            "status": m["status"],
            "risk_band": risk_band(m.get("chargeback_ratio_30d", 0.0)),
            "days_since_signup": age,
            "new_merchant_window": "inside" if age < 90 else "graduated",
            "extended_settlement": m.get("on_extended_settlement", False),
            "rolling_reserve": pct(m.get("rolling_reserve_pct", 0.0)),
        })
    return tuple(rows)


@lru_cache(maxsize=1)
def event_rows() -> tuple[dict, ...]:
    _, _, events = _load()
    total: Counter = Counter()
    current: Counter = Counter()
    month = TODAY_ISO[:7]
    for ev in events:
        et = ev.get("event_type")
        if et not in _NON_ROUTINE:
            continue
        key = (ev["merchant_id"], et)
        total[key] += 1
        if ev["timestamp"][:7] == month:
            current[key] += 1
    rows = [
        {
            "merchant_id": mid,
            "merchant": _name(mid),
            "event_type": et,
            "total": n,
            f"in_{month}": current[(mid, et)],
        }
        for (mid, et), n in total.items()
    ]
    # Descending count within event type: the maximum is row one, so "who has the
    # most" is a read rather than a scan.
    rows.sort(key=lambda r: (r["event_type"], -r["total"], r["merchant_id"]))
    return tuple(rows)


def _table(rows, cols) -> str:
    head = " | ".join(cols)
    body = "\n".join(" | ".join(str(r[c]) for c in cols) for r in rows)
    return f"{head}\n{body}"


@lru_cache(maxsize=1)
def render() -> str:
    d_rows = dispute_rows()
    m_rows = merchant_rows()
    e_rows = event_rows()

    open_actionable = [r for r in d_rows if r["deadline_state"] == "open"]
    past_due = [r for r in d_rows if r["deadline_state"] == "past_due"]
    largest_open = max(
        (r for r in d_rows if not r["evidence_submitted"]),
        key=lambda r: r["amount_cents"],
        default=None,
    )
    at_monitoring = [r for r in m_rows if r["risk_band"] != "ok"]

    parts = [
        f"## PORTFOLIO ROLLUP  (today = {TODAY_ISO})",
        "Standing risk metrics. Definitions come from chargeback_policy.md and",
        "settlement_timing.md; counts are computed over the whole dataset.",
        f"- active disputes on file: {len(d_rows)}",
        f"- disputes with the response window still open: {len(open_actionable)}",
        f"- disputes whose response window has closed: {len(past_due)}"
        + (f" ({', '.join(r['dispute_id'] for r in past_due)})" if past_due else ""),
        f"- disputes with evidence already filed: "
        f"{sum(1 for r in d_rows if r['evidence_submitted'])}",
    ]
    if largest_open:
        parts.append(
            f"- largest dispute still awaiting evidence: {largest_open['dispute_id']} "
            f"{largest_open['amount']} ({largest_open['merchant_id']} "
            f"{largest_open['merchant']})"
        )
    parts.append(
        f"- merchants at or above the {pct(MONITORING)} monitoring threshold: "
        + (", ".join(f"{r['merchant_id']} {r['name']} [{r['risk_band']}]" for r in at_monitoring)
           or "none")
    )
    parts.append(
        f"  (thresholds: monitoring at or above {pct(MONITORING)}; suspension "
        f"review at or above {pct(SUSPENSION)}. Every other merchant is below "
        f"monitoring and is not in that set.)"
    )

    parts += [
        "",
        "## DISPUTE ROSTER  (all active disputes)",
        "days_to_response_due is signed: negative means the window has closed.",
        _table(d_rows, ["dispute_id", "merchant_id", "merchant", "response_due",
                        "days_to_response_due", "evidence_submitted", "amount",
                        "reason_code", "deadline_state"]),
        "",
        "## MERCHANT ROSTER",
        "risk_band is derived from chargeback_policy.md's thresholds. Exact",
        "chargeback ratios are supplied per-merchant in the RECORDS section when a",
        "question names one.",
        _table(m_rows, ["merchant_id", "name", "plan", "status", "risk_band",
                        "days_since_signup", "new_merchant_window",
                        "extended_settlement", "rolling_reserve"]),
        "",
        f"## NON-ROUTINE EVENT COUNTS  (audit log; current month = {TODAY_ISO[:7]})",
        "Routine transaction/payout events are omitted. Sorted by count, highest",
        "first within each event type.",
        _table(e_rows, ["event_type", "merchant_id", "merchant", "total",
                        f"in_{TODAY_ISO[:7]}"]),
    ]
    return "\n".join(parts)
