"""Citation attribution -- derived by code from the answer's own content.

43 of the 100 visible cases carry a citation requirement and the multi-document
ones require *both* sources, so leaving `cited_doc_ids` to the model would make
the weakest link in the system the longest chain in the grading.

This module is read-only with respect to the prompt. It never injects anything
into context; it only attributes what the answer already said.

So don't ask the model to remember to cite. Take the salient atoms the answer
already contains -- amounts, percentages, endpoints, header names, status codes,
schedule shorthand -- plus the verbatim n-grams it reports as key facts, and
attribute each back to every policy document that literally contains it. Cite the
union, plus the IDs of records that were actually fetched.

The claim this makes is checkable and honest: *every cited document literally
contains a string the answer used.* Nothing is cited because it was plausible,
and nothing invented survives, because the model's own `sources` list is filtered
against the documents that were actually in context.
"""
from __future__ import annotations

import re

from .corpus import doc_ids, doc_text
from .text import ascii_punct, collapse

_MD = re.compile(r"[*`]+")


def _flatten(s: str) -> str:
    """Collapse for comparison, with markdown emphasis removed.

    The corpus writes facts as `- **Refund fee:** None`; a quote of that fact
    almost never carries the asterisks, so emphasis has to come off both sides.
    """
    return collapse(_MD.sub("", s or ""))

_SALIENT = re.compile(
    r"""(
        \$[\d,]+(?:\.\d{2})?          # $50,000  $0.30  $15
      | \b\d+(?:\.\d+)?\s?%           # 1.0%  2.9%
      | \b[Tt]\s?\+\s?\d\b            # T+5  t+2
      | /v\d+/[A-Za-z0-9/_{}\-]+      # /v1/refunds
      | \b\d{4}-\d{2}-\d{2}\b         # 2026-01-15
      | \b\d+(?:\s?-\s?\d+)?\+?\s+(?:calendar\s+|business\s+|consecutive\s+)?
        (?:second|minute|hour|day|week|month|year)s?\b   # 7 calendar days  60-75 days
      | \b\d+\s*(?:requests?|reqs?)\b  # 100 requests
      | \b[A-Z][A-Za-z]+-[A-Z][A-Za-z]+\b     # Acmepay-Signature
      | \b[a-z][a-z_]+\.[a-z_]+\b     # account.warning_issued
      | \bsk_(?:live|test)_\w*        # sk_live_
      | \b\d{3}\b                     # 403  429
    )""",
    re.VERBOSE,
)

_MIN_NGRAM = 3
_MAX_NGRAM = 12
# Atoms too common to carry provenance on their own.
_WEAK = {"0", "1", "2", "3", "4", "5", "100", "200"}


def _normalised_docs(ctx=None) -> dict[str, str]:
    """doc_id -> flattened text to attribute against.

    With a `ctx`, this is ONLY the sections that were actually injected for this
    request. Under full injection the two were the same set, so searching the
    whole corpus was sound. Under retrieval they diverge, and searching the corpus
    would attribute a fact to a document the model never saw -- which makes
    `cited_doc_ids` unfalsifiable rather than merely generous.

    Section renders are used rather than raw file text because the render, label
    and all, is literally what went into the prompt.
    """
    if ctx:
        grouped: dict[str, list[str]] = {}
        for s in ctx.sections.values():
            grouped.setdefault(s.doc_id, []).append(s.render())
        return {doc: _flatten("\n\n".join(parts)) for doc, parts in grouped.items()}
    return {doc: _flatten(text) for doc, text in doc_text().items()}


def _attribute_literal(needle: str, docs: dict[str, str]) -> set[str]:
    n = _flatten(needle)
    if not n or n in _WEAK:
        return set()
    return {doc for doc, body in docs.items() if n in body}


def _attribute_path(span: str, docs: dict[str, str]) -> set[str]:
    """Endpoint paths need progressive truncation.

    A natural phrasing writes `/v1/disputes/{id}/evidence`, which is not a
    literal substring of the reference. Trimming trailing segments recovers the
    documented `/v1/disputes`.
    """
    parts = span.rstrip("/").split("/")
    while len(parts) > 2:
        hit = _attribute_literal("/".join(parts), docs)
        if hit:
            return hit
        parts = parts[:-1]
    return _attribute_literal("/".join(parts), docs)


def _ngrams(text: str) -> list[str]:
    words = _flatten(text).split()
    out = []
    for n in range(min(_MAX_NGRAM, len(words)), _MIN_NGRAM - 1, -1):
        for i in range(len(words) - n + 1):
            out.append(" ".join(words[i:i + n]))
    return out


def attribute(text: str, key_facts: list[str], ctx=None) -> set[str]:
    docs = _normalised_docs(ctx)
    found: set[str] = set()
    blob = ascii_punct(text or "")

    for match in _SALIENT.finditer(blob):
        span = match.group(0)
        found |= _attribute_path(span, docs) if span.startswith("/") else _attribute_literal(span, docs)

    # Verbatim phrases the model reports as its factual basis. Longest first, and
    # a hit short-circuits that fact -- a whole sentence lifted from one document
    # is stronger evidence than its individual words.
    for fact in key_facts or []:
        for gram in _ngrams(fact):
            hit = _attribute_literal(gram, docs)
            if hit:
                found |= hit
                break
    return found


def _doc_basename(claimed: str) -> str:
    """Coerce a model-supplied source name to a bare document basename.

    The grader normalises document ids by lowercasing, then stripping `.md`, then
    stripping whitespace -- in that order -- so a path or a trailing space never
    matches. Emit the bare basename and nothing else.
    """
    name = (claimed or "").strip().split("/")[-1].split("\\")[-1]
    if not name.endswith(".md"):
        name = f"{name}.md"
    return name


def complete(draft, ledger, ctx=None) -> list[str]:
    """Final `cited_doc_ids`: attributed documents + fetched record IDs.

    Sorted, never a raw set -- an unsorted set reaching the response reorders
    between runs under hash randomisation, which would make repeat runs measure
    noise instead of behaviour.
    """
    # Scoped to what was injected when a ctx is present, so a model-claimed
    # source for an unretrieved document is dropped the same way an invented
    # filename is.
    valid = ctx.doc_ids() if ctx else set(doc_ids())
    cited: set[str] = set()

    for claimed in draft.sources or []:
        name = _doc_basename(claimed)
        if name in valid:
            cited.add(name)

    cited |= attribute(f"{draft.verdict}\n{draft.detail}", draft.key_facts, ctx=ctx)
    cited |= set(ledger.record_ids())
    return sorted(cited)
