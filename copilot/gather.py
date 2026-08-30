"""Evidence gathering -- deterministic, zero LLM calls.

Three clauses, and they are the whole of tool routing:

1. **First-hop saturation.** For every entity named in the question, call every
   tool that accepts it. No intent classification, so there is nothing for a
   paraphrase to misclassify. Extra calls are unpenalised, these tools are local
   file reads with module-level caches, and saturation earns evidence for free --
   asking only for merchant M-1006 also reads its audit log, which is where a
   rejected applicant's rejection actually lives.

2. **Bounded transitive expansion**, suppressed for single-record field lookups.
   Asking "what's the amount and currency on T-99830?" must not pull the owning
   merchant. Asking "is the dispute on transaction T-99818 still actionable?"
   must. The gate is the question's shape, not the record's contents.

3. **`search_policies` is never called.** The corpus is injected verbatim, so the
   tool is never the mechanism by which a policy fact reaches the answer.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from . import enrich
from .entities import EntityRefs
from .registry import ToolLedger

_FIELD_QUERY = re.compile(
    r"(?i)\b(amount|currency|status|plan|reason code|state|city|volume|"
    r"response deadline|response due|due date|signup|amount_cents)\b"
)
# Anything causal, evaluative or temporal means the question is an investigation,
# not a field read, and the record's neighbours are fair game.
_INVESTIGATIVE = re.compile(
    r"(?i)\b(why|still|actionable|overdue|past due|at risk|about to|blown|"
    r"missed|handled|follow.?up|history|walk|happened|cause|reason for|"
    r"need(s)? action|what'?s going on|investigate|explain)\b"
)


@dataclass
class Evidence:
    blocks: dict[str, object] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def render(self) -> str:
        if not self.blocks and not self.notes:
            return "(no structured records were named in this question)"
        out = []
        for key in sorted(self.blocks):
            out.append(f"### {key}\n{json.dumps(self.blocks[key], indent=2, sort_keys=True)}")
        if self.notes:
            out.append("### notes\n" + "\n".join(self.notes))
        return "\n\n".join(out)


def _is_single_record_field_query(question: str, refs: EntityRefs) -> bool:
    if refs.total() != 1:
        return False
    if _INVESTIGATIVE.search(question):
        return False
    return bool(_FIELD_QUERY.search(question))


def _saturate_merchant(mid: str, led: ToolLedger, ev: Evidence) -> None:
    raw = led.call_once("lookup_merchant", merchant_id=mid)
    ev.blocks[f"merchant {mid}"] = enrich.merchant(mid, raw or {})

    disputes = led.call_once("list_disputes", merchant_id=mid) or []
    ev.blocks[f"disputes of {mid}"] = [
        enrich.dispute(d["dispute_id"], d) for d in disputes
    ]

    tickets = led.call_once("list_recent_tickets", merchant_id=mid) or []
    ev.blocks[f"tickets of {mid}"] = tickets

    events = led.call_once("read_audit_log", merchant_id=mid) or []
    ev.blocks[f"audit log of {mid}"] = enrich.audit_events(events)

    if isinstance(raw, dict) and raw.get("error"):
        # Not an error -- rejected applicants are never created as merchant
        # records, so their only trace is the audit log we just read.
        kinds = {e.get("event_type") for e in events}
        if "merchant_rejected" in kinds:
            ev.notes.append(
                f"{mid} has no merchant record because the application was "
                f"rejected; the audit log above is the whole story for it."
            )
        else:
            ev.notes.append(f"{mid} is not present in Acmepay's merchant records.")
    if tickets == [] and isinstance(raw, dict) and not raw.get("error"):
        ev.notes.append(
            f"{mid} has no support tickets on file. An empty ticket history says "
            f"nothing about account health -- read the audit log and risk_band."
        )


def first_hop(question: str, refs: EntityRefs, led: ToolLedger) -> Evidence:
    ev = Evidence()
    merchants: set[str] = set(refs.merchant_ids)
    allow_transitive = not _is_single_record_field_query(question, refs)

    for txn in sorted(refs.txn_ids):
        raw = led.call_once("lookup_transaction", txn_id=txn)
        ev.blocks[f"transaction {txn}"] = enrich.transaction(txn, raw or {})
        if allow_transitive and isinstance(raw, dict) and raw.get("merchant_id"):
            merchants.add(raw["merchant_id"])

    for did in sorted(refs.dispute_ids):
        raw = led.call_once("get_dispute", dispute_id=did)
        ev.blocks[f"dispute {did}"] = enrich.dispute(did, raw or {})
        if allow_transitive and isinstance(raw, dict) and raw.get("merchant_id"):
            merchants.add(raw["merchant_id"])

    for tid in sorted(refs.ticket_ids):
        raw = led.call_once("get_ticket", ticket_id=tid)
        ev.blocks[f"ticket {tid}"] = raw
        if allow_transitive and isinstance(raw, dict) and raw.get("body"):
            m = re.search(r"\*\*(?:Merchant|Applicant):\*\*\s*(M-\d+)", raw["body"])
            if m:
                merchants.add(m.group(1))

    for mid in sorted(merchants):
        _saturate_merchant(mid, led, ev)

    if refs.ambiguous and len(refs.resolved_names) > 1:
        listed = ", ".join(f"{k} {v}" for k, v in sorted(refs.resolved_names.items()))
        ev.notes.append(
            f"The name in the question matches more than one merchant ({listed}). "
            f"Records for all of them are above. Say which is which rather than "
            f"picking one silently."
        )
    return ev


def expand(answer_text: str, led: ToolLedger, ev: Evidence) -> Evidence:
    """Second-round gathering, driven by the *validator*, not by the model.

    If a draft names a record it never looked at, fetch it and let the repair
    pass rewrite with the record in hand.
    """
    from .entities import extract
    refs = extract(answer_text)
    fresh = EntityRefs(
        txn_ids={t for t in refs.txn_ids if not led.already("lookup_transaction", txn_id=t)},
        dispute_ids={d for d in refs.dispute_ids if not led.already("get_dispute", dispute_id=d)},
        ticket_ids={k for k in refs.ticket_ids if not led.already("get_ticket", ticket_id=k)},
        merchant_ids={m for m in refs.merchant_ids if not led.already("lookup_merchant", merchant_id=m)},
    )
    if not fresh.any():
        return ev
    extra = first_hop("", fresh, led)
    ev.blocks.update(extra.blocks)
    ev.notes.extend(extra.notes)
    return ev
