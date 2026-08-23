"""BM25 search over the policy documents in data/policies/."""
import math
import re
from collections import Counter
from pathlib import Path
from typing import Iterable


_POLICIES_DIR = Path(__file__).resolve().parents[1] / "data" / "policies"
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9'+%$.\-]*")
_INDEX: dict | None = None


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _build_index() -> dict:
    docs = {}
    doc_lengths = {}
    df: Counter = Counter()
    for path in sorted(_POLICIES_DIR.glob("*.md")):
        tokens = _tokenize(path.read_text())
        docs[path.name] = Counter(tokens)
        doc_lengths[path.name] = len(tokens)
        for term in set(tokens):
            df[term] += 1
    n_docs = len(docs)
    avgdl = (sum(doc_lengths.values()) / n_docs) if n_docs else 0
    return {
        "docs": docs,
        "doc_lengths": doc_lengths,
        "df": df,
        "n_docs": n_docs,
        "avgdl": avgdl,
    }


def _bm25_score(
    query_tokens: Iterable[str],
    doc_tokens: Counter,
    doc_length: int,
    df: Counter,
    n_docs: int,
    avgdl: float,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    score = 0.0
    for term in query_tokens:
        if term not in doc_tokens:
            continue
        n_q = df.get(term, 0)
        idf = math.log(((n_docs - n_q + 0.5) / (n_q + 0.5)) + 1)
        tf = doc_tokens[term]
        norm = 1 - b + b * (doc_length / avgdl if avgdl else 1)
        score += idf * (tf * (k1 + 1)) / (tf + k1 * norm)
    return score


def search_policies(query: str, top_k: int = 3) -> list[dict]:
    """BM25 keyword search over policy documents.

    Args:
        query: Free-form search query, e.g. "chargeback dispute window evidence".
        top_k: Max number of policy docs to return (default 3).

    Returns:
        A list of dicts, ranked by relevance, each with:
        - doc_id: filename, e.g. "chargeback_policy.md"
        - score: BM25 score (higher is more relevant)
        - body: full document text

    Note: This is keyword-based BM25, not semantic search. Useful when
    you know domain-specific terminology (e.g. "T+5", "rolling reserve").
    Less useful for paraphrased or conceptual queries.
    """
    global _INDEX
    if _INDEX is None:
        _INDEX = _build_index()
    q_tokens = _tokenize(query)
    scored = []
    for doc_id, doc_tokens in _INDEX["docs"].items():
        s = _bm25_score(
            q_tokens,
            doc_tokens,
            _INDEX["doc_lengths"][doc_id],
            _INDEX["df"],
            _INDEX["n_docs"],
            _INDEX["avgdl"],
        )
        if s > 0:
            scored.append((s, doc_id))
    scored.sort(reverse=True)
    results = []
    for score, doc_id in scored[:top_k]:
        path = _POLICIES_DIR / doc_id
        results.append({"doc_id": doc_id, "score": round(score, 3), "body": path.read_text()})
    return results
