"""The policy corpus: breadcrumbed sections, full-context rendering, and a
*generated* collision map.

Two jobs:

1. Split each policy doc into heading-scoped sections and prefix every one with
   its breadcrumb (`[chargeback_policy.md > Excessive Chargebacks - Thresholds]`).
   The breadcrumbs pay twice: they disambiguate facts that share a number, and
   they are the structure citation attribution needs.

2. Derive the collision map by scanning the corpus for quantities that appear
   under more than one heading. This is *generated, never curated* -- which is
   the whole point. A hand-written table of thresholds is a second source of
   truth for values already present verbatim in context, and it reads to a
   reviewer as tuning.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from .config import POLICIES_DIR
from .text import ascii_punct

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
# merchant_faq.md's atomic unit is a bold Q/A pair, not a markdown heading, so a
# heading-only splitter would produce one 800-token blob for the whole FAQ.
_FAQ_Q = re.compile(r"^\*\*Q:\s*(.+?)\*\*\s*$")

_QTY = re.compile(
    r"\d+(?:\.\d+)?%"                                     # 1.0%  2.9%
    r"|\$[\d,]+(?:\.\d+)?"                                # $15  $50,000
    r"|\bT\+\d\b"                                         # T+5
    r"|\b\d+(?:-\d+)?\+?\s+(?:calendar\s+|business\s+)?"  # 7 calendar days
    r"(?:day|days|month|months|hour|hours|year|years)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Section:
    doc_id: str          # bare basename, e.g. "chargeback_policy.md"
    breadcrumb: str      # " > "-joined heading path
    body: str

    @property
    def label(self) -> str:
        return f"[{self.doc_id} > {self.breadcrumb}]" if self.breadcrumb else f"[{self.doc_id}]"

    def render(self) -> str:
        return f"{self.label}\n{self.body.strip()}"


def _split_doc(doc_id: str, text: str) -> list[Section]:
    out: list[Section] = []
    stack: list[str] = []
    buf: list[str] = []
    faq_sub: str | None = None

    def flush() -> None:
        body = "\n".join(buf).strip()
        buf.clear()
        if not body:
            return
        crumbs = [c for c in stack[1:]]  # drop the H1 doc title; doc_id carries it
        if faq_sub:
            crumbs = crumbs + [faq_sub]
        out.append(Section(doc_id, " > ".join(crumbs), body))

    for line in text.splitlines():
        h = _HEADING.match(line)
        if h:
            flush()
            faq_sub = None
            level = len(h.group(1))
            stack[level - 1:] = [ascii_punct(h.group(2))]
            continue
        q = _FAQ_Q.match(line)
        if q:
            flush()
            faq_sub = ascii_punct(q.group(1)).rstrip("?")
            buf.append(line)
            continue
        buf.append(line)
    flush()
    return out


@lru_cache(maxsize=1)
def sections() -> tuple[Section, ...]:
    docs: list[Section] = []
    for path in sorted(POLICIES_DIR.glob("*.md")):
        docs.extend(_split_doc(path.name, ascii_punct(path.read_text())))
    return tuple(docs)


@lru_cache(maxsize=1)
def doc_ids() -> tuple[str, ...]:
    return tuple(sorted({s.doc_id for s in sections()}))


@lru_cache(maxsize=1)
def doc_text() -> dict[str, str]:
    """doc_id -> full normalised text, for literal-substring attribution."""
    return {p.name: ascii_punct(p.read_text()) for p in sorted(POLICIES_DIR.glob("*.md"))}


@lru_cache(maxsize=1)
def render_all() -> str:
    return "\n\n".join(s.render() for s in sections())


@lru_cache(maxsize=1)
def render_toc() -> str:
    """An index of the corpus: document -> section headings.

    Full injection gives perfect recall, but recall is not the same as attention.
    A small model reading 4,000 tokens of policy still has to find the right
    paragraph, and the observed failures were navigation failures -- the fact was
    present and unused. A heading index is the cheapest possible fix: it lets the
    model locate a topic by name before reading, and it costs a few hundred
    tokens of the prefix that is cached anyway.
    """
    by_doc: dict[str, list[str]] = {}
    for s in sections():
        if s.breadcrumb:
            by_doc.setdefault(s.doc_id, [])
            if s.breadcrumb not in by_doc[s.doc_id]:
                by_doc[s.doc_id].append(s.breadcrumb)
    lines = []
    for doc in sorted(by_doc):
        lines.append(f"{doc}")
        for crumb in by_doc[doc]:
            lines.append(f"    - {crumb}")
    return "\n".join(lines)


@lru_cache(maxsize=1)
def vocabulary() -> frozenset[str]:
    """Every word that occurs anywhere in the policy corpus.

    Used as a *generic-business-vocabulary* filter during merchant-name
    resolution: a token that Acmepay's own policy documents use is ordinary
    domain language and cannot by itself identify a specific merchant. Derived
    from the corpus, not hand-listed.
    """
    from .text import tokens
    vocab: set[str] = set()
    for t in doc_text().values():
        vocab.update(tokens(t))
    return frozenset(vocab)


@lru_cache(maxsize=1)
def collision_map() -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Quantities that mean different things under different headings.

    e.g. `1.0%` is both the chargeback monitoring threshold and the currency
    conversion fee; `24 hours` has three unrelated meanings. Emitted as
    disambiguation hints so a value is never resolved on its own.
    """
    seen: dict[str, set[str]] = {}
    for s in sections():
        for m in _QTY.finditer(s.body):
            key = " ".join(m.group(0).lower().split())
            seen.setdefault(key, set()).add(s.label)
        # A heading can itself carry the quantity (e.g. "Monitoring (1.0%)").
        for m in _QTY.finditer(s.breadcrumb):
            key = " ".join(m.group(0).lower().split())
            seen.setdefault(key, set()).add(s.label)
    out = [(k, tuple(sorted(v))) for k, v in seen.items() if len(v) > 1]
    return tuple(sorted(out))


def render_collisions() -> str:
    rows = collision_map()
    if not rows:
        return ""
    lines = [
        "The same quantity means different things in different sections. Never",
        "resolve one of these from the number alone -- match the section too:",
    ]
    for value, labels in rows:
        lines.append(f"  {value}  ->  " + "  |  ".join(labels))
    return "\n".join(lines)
