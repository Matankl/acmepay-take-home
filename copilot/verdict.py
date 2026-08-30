"""Deterministic verdict sentences for high-value question shapes.

Guards are subtractive: they catch a bad answer after the fact. This is the
additive half -- for the shapes where the correct opening sentence is fully
determined by the records, compose that sentence in code and let the model write
only the explanation around it.

Two reasons this matters more than it looks. The grader takes a strict majority
across repeated runs, so pushing a shaky case toward certainty is worth more than
adding capability elsewhere. And the configured model is a small, fast tier, for
which "read this field and restate it" is reliable while "compare these dates and
decide" is not.

Templates are keyed on *question shape x record type*. Nothing here is keyed on a
question's wording.
"""
from __future__ import annotations

import re

from .config import TODAY_ISO
from .text import ascii_punct

_COUNT_Q = re.compile(r"(?i)\bhow many\b|\bcount\b|\bnumber of\b")
_DISPUTE_Q = re.compile(r"(?i)\bdisputes?\b|\bchargebacks?\b")
_DEADLINE_Q = re.compile(
    r"(?i)\bdeadline\b|\bdue\b|\brespond\b|\bresponse\b|\bwindow\b|\bhow long\b"
    r"|\bactionable\b|\bstill\b|\bmiss(ed)?\b|\bhandled\b|\btime (left|remaining)\b"
)

_KIND_WORD = {"transaction": "transaction", "merchant": "merchant",
              "dispute": "dispute", "ticket": "ticket"}


def _missing(block: object) -> bool:
    return isinstance(block, dict) and bool(block.get("error"))


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def mandate(question: str, refs, evidence) -> str | None:
    """Return the sentence the answer must open with, or None.

    None means the question has no mechanically determined verdict and the model
    writes its own opening.
    """
    q = ascii_punct(question or "")
    blocks = evidence.blocks

    # ---- 1. A named record does not exist -------------------------------------
    # "There is no such record" is an ANSWER, not a refusal, and it must state a
    # fact about the world rather than about the assistant's reach.
    for key in sorted(blocks):
        if not _missing(blocks[key]):
            continue
        kind, _, ident = key.partition(" ")
        if kind not in _KIND_WORD:
            continue
        if kind == "merchant":
            events = blocks.get(f"audit log of {ident}") or []
            rejected = next(
                (e for e in events if e.get("event_type") == "merchant_rejected"), None
            )
            if rejected:
                meta = rejected.get("metadata") or {}
                who = meta.get("applicant_name") or ident
                when = rejected["timestamp"][:10]
                reason = str(meta.get("reason", "")).replace("_", " ")
                tail = f" ({reason})" if reason else ""
                return (
                    f"{who} is not an Acmepay merchant: the application was "
                    f"rejected on {when}{tail}, so there is no account and no "
                    f"account configuration."
                )
            return (
                f"There is no merchant record for {ident} in Acmepay's systems, "
                f"and no audit-log history for it either."
            )
        return f"There is no record of {_KIND_WORD[kind]} {ident} in Acmepay's systems."

    # ---- 2. Count of a merchant's active disputes -----------------------------
    if _COUNT_Q.search(q) and _DISPUTE_Q.search(q) and len(refs.merchant_ids) == 1:
        mid = next(iter(refs.merchant_ids))
        rows = blocks.get(f"disputes of {mid}")
        merchant = blocks.get(f"merchant {mid}") or {}
        if isinstance(rows, list) and not _missing(merchant):
            name = merchant.get("name", mid)
            if not rows:
                return f"{name} ({mid}) has no disputes on file."
            ids = ", ".join(sorted(r["dispute_id"] for r in rows))
            return (f"{name} ({mid}) has {_plural(len(rows), 'active dispute')} "
                    f"on file: {ids}.")

    # ---- 3. One dispute's response window -------------------------------------
    if _DEADLINE_Q.search(q) and len(refs.dispute_ids) == 1 and not refs.txn_ids:
        did = next(iter(refs.dispute_ids))
        d = blocks.get(f"dispute {did}")
        if isinstance(d, dict) and not _missing(d) and d.get("deadline_state"):
            state = d["deadline_state"]
            due = d["response_due"]
            if state == "past_due":
                return (
                    f"{did}'s response window closed on {due}, "
                    f"{_plural(d['days_since_due'], 'day')} before today "
                    f"({TODAY_ISO}), and no evidence was filed."
                )
            if state == "evidence_filed":
                return (f"{did} already has its evidence filed; the response "
                        f"window runs to {due}.")
            return (
                f"{did}'s response window is open until {due} -- "
                f"{_plural(d['days_remaining'], 'day')} from today ({TODAY_ISO})."
            )
    return None
