"""Ticket history as a first-class knowledge source.

The policy corpus has one real hole: `statement descriptor` appears in no policy
document at all, yet it is the single largest question cluster in the ticket
archive. Worse, settlement_timing.md contains the phrase "settlement statement",
so a keyword search for a descriptor question returns a confident wrong document.
Any system treating data/policies/ as the whole knowledge base gets the most
frequently asked real question wrong.

The fix applies the same insight as the policy layer, twice: when the distinct
*answer* space is tiny, summarise deterministically instead of retrieving. 55
tickets collapse to ~18 subjects, and a handful of clusters cover most of them.
So the precedent index is a mechanical group-by -- the earliest resolved reply
per subject, verbatim -- always in context, no retrieval step to miss.

BM25 over the bodies handles the long tail. Keyword search works *better* on
tickets than on policies here, because tickets are written in merchant language,
so the vocabulary gap that defeats keyword search on the policy docs is largely
absent. The implementation is the one already in tools/search_policies.py,
generalised over a directory rather than rewritten.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

# Reusing the working BM25 from the shipped tool rather than writing a second one.
from tools.search_policies import _bm25_score, _tokenize

from .config import TICKETS_DIR, TICKET_SEARCH_TOP_K
from .text import ascii_punct

_HEAD = re.compile(r"#\s*(TKT-\d+)\s*-\s*(.*)")
_MERCHANT = re.compile(r"\*\*(?:Merchant|Applicant):\*\*\s*(M-\d+)")
_OPENED = re.compile(r"\*\*Opened:\*\*\s*([\d-]+)")
_BLOCK = re.compile(r"^\*\*([^*(]+?)\s*\(([^)]*)\):\*\*\s*$", re.MULTILINE)
_INTERNAL = re.compile(r"\n---\s*\n\s*\*\*Internal note", re.IGNORECASE)


@dataclass(frozen=True)
class Ticket:
    ticket_id: str
    subject: str
    merchant_id: str | None
    opened_at: str
    body: str          # internal notes stripped
    agent_reply: str


def _strip_internal(text: str) -> str:
    """Remove trailing internal agent notes.

    get_ticket's own docstring warns that bodies carry internal notes and to
    treat them carefully when drafting merchant-facing replies. The `---` before
    `**Internal note` is the reliable boundary.
    """
    m = _INTERNAL.search(text)
    return text[: m.start()] if m else text


def _first_agent_reply(text: str) -> str:
    marks = list(_BLOCK.finditer(text))
    for i, mark in enumerate(marks):
        speaker = mark.group(1).strip().lower()
        if speaker in {"merchant", "applicant"} or speaker.startswith("internal"):
            continue
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        chunk = text[mark.end():end]
        chunk = re.split(r"\n\s*-\s*[A-Z]\s*$", chunk, maxsplit=1, flags=re.MULTILINE)[0]
        return " ".join(chunk.split())
    return ""


@lru_cache(maxsize=1)
def tickets() -> tuple[Ticket, ...]:
    out = []
    for path in sorted(TICKETS_DIR.glob("*.md")):   # sorted: reproducibility
        raw = ascii_punct(path.read_text())
        head = _HEAD.search(raw)
        merchant = _MERCHANT.search(raw)
        opened = _OPENED.search(raw)
        body = _strip_internal(raw)
        out.append(Ticket(
            ticket_id=head.group(1) if head else path.stem,
            subject=(head.group(2).strip() if head else ""),
            merchant_id=merchant.group(1) if merchant else None,
            opened_at=opened.group(1) if opened else "",
            body=body,
            agent_reply=_first_agent_reply(body),
        ))
    return tuple(out)


@lru_cache(maxsize=1)
def clusters() -> tuple[tuple[str, int, str], ...]:
    """(subject, ticket_count, canonical_reply) sorted by frequency."""
    groups: dict[str, list[Ticket]] = {}
    for t in tickets():
        key = " ".join(t.subject.lower().split())
        if key:
            groups.setdefault(key, []).append(t)
    rows = []
    for subject, members in groups.items():
        members.sort(key=lambda t: (t.opened_at, t.ticket_id))
        reply = next((m.agent_reply for m in members if m.agent_reply), "")
        if reply:
            rows.append((subject, len(members), reply))
    rows.sort(key=lambda r: (-r[1], r[0]))
    return tuple(rows)


@lru_cache(maxsize=1)
def render_index(max_clusters: int = 10, max_chars: int = 420) -> str:
    lines = [
        "How Acmepay agents have answered the most common merchant questions.",
        "These are resolved precedents from the ticket archive, not policy text.",
        "Some topics -- statement descriptors, for one -- appear here and in no",
        "policy document, so this is the authoritative source for them. Cite the",
        "ticket id when you rely on a precedent.",
    ]
    for subject, count, reply in clusters()[:max_clusters]:
        snippet = reply if len(reply) <= max_chars else reply[:max_chars].rsplit(" ", 1)[0] + " ..."
        lines.append(f"- [{count} tickets] {subject}: {snippet}")
    return "\n".join(lines)


@lru_cache(maxsize=1)
def _index():
    docs, lengths, df = {}, {}, Counter()
    for t in tickets():
        toks = _tokenize(t.subject + "\n" + t.body)
        docs[t.ticket_id] = Counter(toks)
        lengths[t.ticket_id] = len(toks)
        for term in set(toks):
            df[term] += 1
    n = len(docs) or 1
    return docs, lengths, df, n, sum(lengths.values()) / n


def search(query: str, top_k: int = TICKET_SEARCH_TOP_K) -> list[dict]:
    """BM25 over ticket bodies. Exposed as a tool so its use is recorded."""
    docs, lengths, df, n, avgdl = _index()
    q = _tokenize(query)
    by_id = {t.ticket_id: t for t in tickets()}
    scored = []
    for tid, counts in docs.items():
        s = _bm25_score(q, counts, lengths[tid], df, n, avgdl)
        if s > 0:
            scored.append((round(s, 3), tid))
    scored.sort(key=lambda x: (-x[0], x[1]))     # deterministic tie-break
    return [
        {
            "ticket_id": tid,
            "score": score,
            "subject": by_id[tid].subject,
            "merchant_id": by_id[tid].merchant_id,
            "resolution": by_id[tid].agent_reply,
        }
        for score, tid in scored[:top_k]
    ]


def select(question: str, refs) -> str:
    """Precedent context for one question: the always-on index plus, when the
    question is not already answered by policy vocabulary, the BM25 tail."""
    parts = [render_index()]
    hits = search(question)
    if hits:
        parts.append("Closest individual tickets:")
        for h in hits:
            parts.append(f"- {h['ticket_id']} ({h['subject']}): {h['resolution'][:300]}")
    return "\n".join(parts)
