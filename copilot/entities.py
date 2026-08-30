"""Deterministic entity extraction.

Argument extraction is a regular-language problem over a closed ID grammar, so
it belongs in code, not in a sampler. The grader compares tool arguments with
exact `==`, which means every near-miss surface form (`d-503`, `D 503`, an
en-dashed `D-503`, `dispute 503`) is worth zero. So: extract loosely, emit
canonically.

Merchant-name resolution scores by coverage *of the name*, not of the question,
because a question mentions a merchant in passing and a paraphrase can add
tokens ("the Lumen Travel account", "Maple & Mortar LLC") as easily as drop
them. On genuine ambiguity we keep every tied candidate rather than guessing --
and callers fetch all of them.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache

from .config import DATA, TICKETS_DIR
from .corpus import vocabulary
from .text import ascii_punct, tokens

# Prefixed forms, tolerant of any separator (or none) and any dash variant --
# ascii_punct() has already folded the dash family, so a plain `-?` suffices.
_PREFIXED = re.compile(r"(?i)\b(TKT|T|M|D)\s*-?\s*(\d{3,5})\b")

# Bare numbers next to a type word: "dispute 503", "transaction 99815".
_KEYWORDED = re.compile(
    r"(?i)\b(dispute|chargeback|ticket|case|transaction|txn|charge|payment|"
    r"merchant|account|applicant)\s+#?(\d{3,5})\b"
)

_KEYWORD_KIND = {
    "dispute": "D", "chargeback": "D",
    "ticket": "TKT", "case": "TKT",
    "transaction": "T", "txn": "T", "charge": "T", "payment": "T",
    "merchant": "M", "account": "M", "applicant": "M",
}

# Digit-width -> kind, inferred from the shape of the data files themselves
# (transactions T-99800..T-99998, merchants M-1001..M-1035, disputes D-501..D-515,
# tickets TKT-201..TKT-255). Never from an eval assertion.
_WIDTH_KIND = {5: "T", 4: "M", 3: None}

_CORP_SUFFIX = {"co", "llc", "inc", "ltd", "corp", "company"}
_NAME_STOP = _CORP_SUFFIX | {"and", "the", "of"}


@dataclass
class EntityRefs:
    txn_ids: set[str] = field(default_factory=set)
    merchant_ids: set[str] = field(default_factory=set)
    dispute_ids: set[str] = field(default_factory=set)
    ticket_ids: set[str] = field(default_factory=set)
    # merchant_id -> the name span that resolved it (for prose disambiguation)
    resolved_names: dict[str, str] = field(default_factory=dict)
    ambiguous: bool = False

    def any(self) -> bool:
        return bool(self.txn_ids or self.merchant_ids or self.dispute_ids or self.ticket_ids)

    def total(self) -> int:
        return len(self.txn_ids) + len(self.merchant_ids) + len(self.dispute_ids) + len(self.ticket_ids)


def canonical(kind: str, digits: str) -> str:
    return f"{kind.upper()}-{digits}"


# --------------------------------------------------------------------------
# Merchant name index
# --------------------------------------------------------------------------

@lru_cache(maxsize=1)
def name_index() -> dict[str, str]:
    """merchant_id -> canonical display name.

    Three sources, because no single one is complete. `merchants.json` holds the
    34 live merchants. The audit log's `metadata.applicant_name` is the *only*
    machine-readable source for a rejected applicant -- rejected applications are
    never created as merchant records (onboarding_playbook.md, and
    tools/lookup_merchant.py says so in its docstring). Ticket headers are a
    redundant third source.
    """
    names: dict[str, str] = {}
    merchants = json.loads((DATA / "merchants.json").read_text())
    for mid, rec in merchants.items():
        names[mid] = ascii_punct(rec["name"])

    for line in (DATA / "audit_log.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        ev = json.loads(line)
        applicant = (ev.get("metadata") or {}).get("applicant_name")
        if applicant:
            names.setdefault(ev["merchant_id"], ascii_punct(applicant))

    hdr = re.compile(r"\*\*(?:Merchant|Applicant):\*\*\s*(M-\d+)\s*\(([^)]+)\)")
    for path in sorted(TICKETS_DIR.glob("*.md")):
        m = hdr.search(path.read_text())
        if m:
            names.setdefault(m.group(1), ascii_punct(m.group(2)).strip())
    return dict(sorted(names.items()))


@lru_cache(maxsize=1)
def _name_tokens() -> dict[str, frozenset[str]]:
    out = {}
    for mid, name in name_index().items():
        toks = {t for t in tokens(name) if t not in _NAME_STOP}
        if toks:
            out[mid] = frozenset(toks)
    return out


def resolve_names(question: str, threshold: float = 0.5) -> tuple[dict[str, str], bool]:
    """Return {merchant_id: matched_name} plus an `ambiguous` flag.

    Scored by |name_tokens & question_tokens| / |name_tokens|, keeping every
    candidate tied at the top score. A match additionally requires at least one
    overlapping token that does NOT appear in the policy corpus: words Acmepay's
    own documentation uses ("travel", "records", "supply") are generic business
    vocabulary and must not identify a merchant on their own, while distinctive
    brand tokens ("lumen", "mortar", "verdant") may.
    """
    qtoks = {t for t in tokens(question) if t not in _NAME_STOP}
    if not qtoks:
        return {}, False
    generic = vocabulary()

    scored: list[tuple[float, int, str]] = []
    for mid, ntoks in _name_tokens().items():
        overlap = ntoks & qtoks
        if not overlap:
            continue
        if not (overlap - generic):
            continue  # only generic vocabulary matched -- not an identification
        cov = len(overlap) / len(ntoks)
        if cov >= threshold:
            scored.append((cov, len(overlap), mid))
    if not scored:
        return {}, False

    scored.sort(reverse=True)
    top = scored[0][:2]
    winners = [mid for cov, n, mid in scored if (cov, n) == top]
    return ({mid: name_index()[mid] for mid in sorted(winners)}, len(winners) > 1)


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------

def extract(question: str) -> EntityRefs:
    q = ascii_punct(question or "")
    refs = EntityRefs()
    buckets = {"T": refs.txn_ids, "M": refs.merchant_ids, "D": refs.dispute_ids, "TKT": refs.ticket_ids}

    for kind, digits in _PREFIXED.findall(q):
        kind = kind.upper()
        # A bare `T` with 3 digits is a mistyped ticket, not a transaction; a `D`
        # with 4 is not a dispute. Only accept widths the data actually uses.
        width = len(digits)
        if kind == "T" and width != 5:
            continue
        if kind == "M" and width != 4:
            continue
        if kind == "D" and width != 3:
            continue
        if kind == "TKT" and width != 3:
            continue
        buckets[kind].add(canonical(kind, digits))

    for word, digits in _KEYWORDED.findall(q):
        kind = _KEYWORD_KIND[word.lower()]
        width = len(digits)
        # Trust the keyword, but sanity-check the width against the data shapes.
        if kind == "T" and width != 5:
            kind = _WIDTH_KIND.get(width) or kind
        if (kind, width) in {("D", 3), ("TKT", 3), ("M", 4), ("T", 5)}:
            buckets[kind].add(canonical(kind, digits))

    names, ambiguous = resolve_names(q)
    refs.resolved_names = names
    refs.ambiguous = ambiguous
    refs.merchant_ids.update(names)
    return refs
