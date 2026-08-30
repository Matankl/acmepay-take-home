"""Policy retrieval for corpora that do not fit the context budget.

Not on the default path, and that is a measured decision rather than an omission.
The corpus is ~4.2K tokens, and the shipped `search_policies` returns *whole
documents*, so a top-3 keyword search already ships about half the corpus while
adding document-selection error on top. At this size, injecting everything is
both cheaper and strictly more accurate: recall is 100% by construction.

This module is what makes that a regime choice instead of a lucky break. Set
ACMEPAY_RETRIEVAL_MODE=bm25 or =hybrid and the same control flow runs unchanged
over a corpus two orders of magnitude larger. `full` mode also degrades here
automatically if the corpus ever outgrows POLICY_CONTEXT_BUDGET.

Design notes for the scaled-up case:
  * Chunks are breadcrumbed sections, so every chunk carries its heading path --
    cheap, and a large recall win over blind fixed-width slicing.
  * Keyword and dense scores are fused by reciprocal rank, which needs no score
    normalisation between two incomparable scorers.
  * Keyword search is not optional here. The domain vocabulary (`T+5`, `1.5%`,
    `sk_live_`, reason codes) is exactly where dense embeddings are weakest and
    exact-term matching is strongest.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from functools import lru_cache

import numpy as np

from tools.search_policies import _bm25_score, _tokenize

from .config import POLICY_CONTEXT_BUDGET, RETRIEVAL_MODE, ROOT
from .corpus import sections

_CACHE_DIR = ROOT / ".cache"
_RRF_K = 60
_TOP_K = 8
_EMBED_MODEL = "all-MiniLM-L6-v2"

_embedder = None


def _get_embedder():
    """Loaded lazily and never on the default path.

    On `full` mode this function is never called, which is worth roughly a 90 MB
    model download and several seconds of import time per process.
    """
    global _embedder
    if _embedder is None:
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
        return np.load(path)
    matrix = np.asarray(_get_embedder().encode([s.render() for s in sections()]), dtype=np.float32)
    matrix /= np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-8
    _CACHE_DIR.mkdir(exist_ok=True)
    np.save(path, matrix)
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
    q = np.asarray(_get_embedder().encode([query])[0], dtype=np.float32)
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


def render_retrieved(query: str) -> str:
    return "\n\n".join(s.render() for s in retrieve(query))


def relevant_labels(query: str, top_k: int = 5) -> list[str]:
    """Breadcrumbs of the sections most likely to matter for this question.

    A *precision hint layered on full-recall injection*, not a substitute for it.
    The whole corpus is still in context, so a wrong hint costs nothing and a
    right one focuses attention on the paragraph that carries the figure. Only
    the labels are emitted -- the bodies are already present.
    """
    ranked = _keyword_ranking(query)[:top_k]
    all_sections = sections()
    return [all_sections[i].label for i in ranked]


def corpus_fits_budget() -> bool:
    from litellm import token_counter
    from .corpus import render_all
    try:
        n = token_counter(model="gpt-4o-mini", text=render_all())
    except Exception:
        n = len(render_all()) // 4
    return n <= POLICY_CONTEXT_BUDGET
