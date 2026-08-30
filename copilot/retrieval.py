"""Policy retrieval: BM25 + dense, reciprocal-rank fused. The default path.

The corpus is ~4.6K tokens, so injecting all of it is *possible* -- and that was
the original design. Measured against it on the 28 visible cases that assert
`must_cite`, retrieving 12 of 59 breadcrumbed sections holds 27/28 of the recall
for 24% of the policy tokens. `full` buys the last case at 4x the cost on every
single request; see ARCHITECTURE.md "Decision 1".

Set ACMEPAY_RETRIEVAL_MODE=full to get the old behaviour back, or =bm25 to drop
the embedder entirely (which loses nothing on this corpus -- the domain
vocabulary `T+5`, `1.5%`, `sk_live_`, reason codes is exactly where exact-term
matching beats dense similarity, and where dense fusion actually *displaces* a
needed section at mid-k).

Design notes:
  * Chunks are breadcrumbed sections, so every chunk carries its heading path --
    cheap, and a large recall win over blind fixed-width slicing. It also makes
    the retrieved set self-labelling, which is why no separate table of contents
    is injected.
  * Keyword and dense scores are fused by reciprocal rank, which needs no score
    normalisation between two incomparable scorers.
  * What was actually injected is accumulated in a `RetrievedContext` and read
    back by cite.py. Under `full` those two sets were identical, so attribution
    could search the whole corpus; under retrieval they diverge, and citing a
    document the model never saw would make `cited_doc_ids` unfalsifiable.
"""
from __future__ import annotations

import hashlib
import threading
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

from tools.search_policies import _bm25_score, _tokenize

from .config import (
    POLICY_CONTEXT_BUDGET,
    RETRIEVAL_MODE,
    RETRIEVAL_REPAIR_TOP_K,
    RETRIEVAL_TOP_K,
    ROOT,
)
from .corpus import Section, sections

_CACHE_DIR = ROOT / ".cache"
_RRF_K = 60
_TOP_K = RETRIEVAL_TOP_K
_REPAIR_TOP_K = RETRIEVAL_REPAIR_TOP_K
_EMBED_MODEL = "all-MiniLM-L6-v2"

_embedder = None
# SentenceTransformer.encode is not thread-safe: concurrent forward passes
# through the same torch module segfault the interpreter rather than raising.
# scripts/sweep.py defaults to --workers 8, so serialising the dense path is
# required, not defensive. Encoding is milliseconds against a network call, so
# the lost parallelism is not measurable.
_EMBED_LOCK = threading.Lock()


@dataclass
class RetrievedContext:
    """The policy sections actually injected for one ask(), across both passes.

    Constructed once per request and passed by reference, the same way ToolLedger
    and Evidence are -- not a thread-local. The telemetry thread-local in
    system.py is for observability read after ask() returns; this is graded data
    flow: cite.py reads it to scope attribution to what the model could actually
    see.

    Keyed by section label, so `add` is idempotent and the accumulated order is
    first-seen retrieval rank. That makes the pass-1 + repair union exact without
    assuming a top-20 ranking contains the top-12 one.
    """

    sections: dict[str, Section] = field(default_factory=dict)

    def add(self, secs) -> None:
        for s in secs:
            self.sections.setdefault(s.label, s)

    def doc_ids(self) -> set[str]:
        return {s.doc_id for s in self.sections.values()}

    def render(self) -> str:
        return "\n\n".join(s.render() for s in self.sections.values())

    def __bool__(self) -> bool:
        return bool(self.sections)


def _get_embedder():
    """Loaded lazily and never on the default path.

    On `full` mode this function is never called, which is worth roughly a 90 MB
    model download and several seconds of import time per process.
    """
    global _embedder
    if _embedder is None:
        with _EMBED_LOCK:
            if _embedder is None:                    # re-check inside the lock
                from sentence_transformers import SentenceTransformer
                _embedder = SentenceTransformer(_EMBED_MODEL)
    return _embedder


@lru_cache(maxsize=1)
def _keyword_index():
    docs, lengths, df = {}, {}, Counter()
    for i, s in enumerate(sections()):
        toks = _tokenize(f"{s.doc_id} {s.breadcrumb}\n{s.body}")
        docs[i] = Counter(toks)
        lengths[i] = len(toks)
        for term in set(toks):
            df[term] += 1
    n = len(docs) or 1
    return docs, lengths, df, n, sum(lengths.values()) / n


@lru_cache(maxsize=1)
def _dense_index() -> np.ndarray:
    """Row-normalised embedding matrix, content-hash keyed on disk.

    One matmul per query against a pre-normalised matrix, rather than a Python
    loop recomputing vector norms for every chunk of every query.
    """
    payload = "\n".join(s.render() for s in sections())
    digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
    path = _CACHE_DIR / f"policy-{_EMBED_MODEL}-{digest}.npy"
    if path.exists():
        try:
            return np.load(path)
        except (OSError, ValueError):
            pass                    # truncated or corrupt cache -- recompute
    embedder = _get_embedder()
    with _EMBED_LOCK:
        matrix = np.asarray(embedder.encode([s.render() for s in sections()]), dtype=np.float32)
    matrix /= np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-8
    # Persisting is an optimisation, not a requirement. On a read-only or
    # sandboxed filesystem (CI, container) an unguarded save raises out of
    # retrieve(), through ask()'s handler, and into _fallback() -- which answers
    # with refused=False and buries the real cause. Degrade to in-memory instead.
    try:
        _CACHE_DIR.mkdir(exist_ok=True)
        np.save(path, matrix)
    except OSError:
        pass
    return matrix


def _keyword_ranking(query: str) -> list[int]:
    docs, lengths, df, n, avgdl = _keyword_index()
    q = _tokenize(query)
    scored = [
        (_bm25_score(q, docs[i], lengths[i], df, n, avgdl), i) for i in docs
    ]
    scored = [(s, i) for s, i in scored if s > 0]
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [i for _, i in scored]


def _dense_ranking(query: str) -> list[int]:
    matrix = _dense_index()
    embedder = _get_embedder()
    with _EMBED_LOCK:
        q = np.asarray(embedder.encode([query])[0], dtype=np.float32)
    q /= np.linalg.norm(q) + 1e-8
    scores = matrix @ q
    return list(np.argsort(-scores))


def retrieve(query: str, top_k: int = _TOP_K):
    rankings = [_keyword_ranking(query)]
    if RETRIEVAL_MODE == "hybrid":
        rankings.append(_dense_ranking(query))

    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (_RRF_K + rank + 1)
    order = sorted(fused, key=lambda i: (-fused[i], i))
    all_sections = sections()
    return [all_sections[i] for i in order[:top_k]]


def render_retrieved(query: str, top_k: int = _TOP_K, ctx: "RetrievedContext | None" = None) -> str:
    """Retrieve and render. With a `ctx`, renders the ACCUMULATED union.

    Rendering the union rather than just this call's slice is what makes the
    repair pass strictly additive: the second, wider retrieval can only add
    sections to what the first pass already showed, never silently drop one that
    an earlier answer was grounded in.
    """
    secs = retrieve(query, top_k=top_k)
    if ctx is None:
        return "\n\n".join(s.render() for s in secs)
    ctx.add(secs)
    return ctx.render()


def render_context(ctx: "RetrievedContext | None") -> str:
    """Re-render what was already injected, with no new scoring pass.

    Used by the repair prompt when the failure was not policy-shaped: the model
    still needs the policy text in front of it to rewrite, but there is no reason
    to pay for a wider search it will not benefit from.
    """
    return ctx.render() if ctx else ""


def relevant_labels(query: str, top_k: int = 5) -> list[str]:
    """Breadcrumbs of the sections most likely to matter for this question.

    Used ONLY under `full` mode, where the whole corpus is in context: a wrong
    hint costs nothing there and a right one focuses attention on the paragraph
    carrying the figure. Only labels are emitted -- the bodies are already
    present.

    Deliberately not used under hybrid/bm25. Retrieved sections are rendered with
    their own breadcrumb label, so the injected set already says what it is;
    naming sections whose bodies were NOT retrieved would invite the model to
    reference text it cannot see.
    """
    ranked = _keyword_ranking(query)[:top_k]
    all_sections = sections()
    return [all_sections[i].label for i in ranked]


@lru_cache(maxsize=1)
def effective_mode() -> str:
    """The regime actually in force, after the budget check.

    `full` is the only mode that can be overridden: it is the one that scales with
    corpus size rather than with top_k, so it is the one that can stop fitting.
    Degrading to `bm25` rather than `hybrid` is deliberate -- if the corpus just
    grew past the budget the dense index is stale and rebuilding it is the most
    expensive thing available, so the cheap keyword path is the safer landing.

    Cached: called from the lru_cached system_block() and from user_block() on
    every request, and token-counting the whole corpus is not free.
    """
    if RETRIEVAL_MODE == "full" and not corpus_fits_budget():
        return "bm25"
    return RETRIEVAL_MODE


def corpus_fits_budget() -> bool:
    from litellm import token_counter
    from .corpus import render_all
    try:
        n = token_counter(model="gpt-4o-mini", text=render_all())
    except Exception:
        n = len(render_all()) // 4
    return n <= POLICY_CONTEXT_BUDGET
