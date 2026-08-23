"""
system.py — Acmepay Support Copilot (baseline)

The user of this assistant is an Acmepay support agent handling merchant tickets.
This baseline implementation does ONE thing: naive RAG over policy documents.
It ignores:
  - Transaction, merchant, dispute, ticket, and audit-log data
  - All 8 tools that are wired up but never called
  - The fact that the user is a support agent (so refusal logic is generic)
  - Anything resembling investigation or multi-step reasoning

Your job is to improve it.

Do NOT change the Response schema — the eval suite depends on it.
"""
from __future__ import annotations

import os
import json
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field
import numpy as np
from sentence_transformers import SentenceTransformer
import instructor
import litellm
from litellm import completion

# Tools are available — none are used in this baseline.
import tools  # noqa: F401

load_dotenv()

# The configured model may be a reasoning model (e.g. the Azure gpt-5.x series)
# that rejects sampling params like `temperature` (only the default value 1 is
# allowed) and requires `max_completion_tokens` instead of `max_tokens`. Letting
# litellm drop unsupported params keeps the system model-portable. NOTE: do not
# rely on this to force determinism — these models only run at temperature 1, so
# responses vary run to run; the eval runner's --samples flag smooths that out.
litellm.drop_params = True

POLICIES_DIR = Path(__file__).parent / "data" / "policies"
MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")
CHUNK_SIZE = 500   # characters (no overlap)
TOP_K = 3


# ---------------------------------------------------------------------------
# Response schema (DO NOT MODIFY)
# ---------------------------------------------------------------------------

class ToolCall(BaseModel):
    name: str
    args: dict


class Response(BaseModel):
    """Structured response contract. The eval suite depends on this schema."""
    answer: str = Field(description="Natural-language answer.")
    cited_doc_ids: list[str] = Field(
        default_factory=list,
        description="Doc IDs used as sources, e.g. ['fees_and_pricing.md']. "
                    "Also include ticket/transaction/merchant IDs when applicable, "
                    "e.g. 'TKT-203', 'T-99812', 'M-1003'.",
    )
    tool_calls: list[ToolCall] = Field(
        default_factory=list,
        description="Tool calls the system made while answering.",
    )
    refused: bool = Field(
        default=False,
        description="True if the system refused to answer.",
    )
    refusal_reason: Optional[str] = Field(default=None)


# ---------------------------------------------------------------------------
# Naive RAG — policies only
# ---------------------------------------------------------------------------

_embedder = None
_index: list[tuple[str, str, np.ndarray]] = []   # (doc_id, chunk_text, embedding)


def _get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedder


def _build_index():
    """Load policy docs, chunk them, embed each chunk."""
    global _index
    _index = []
    embedder = _get_embedder()
    for md_file in sorted(POLICIES_DIR.glob("*.md")):
        text = md_file.read_text()
        for start in range(0, len(text), CHUNK_SIZE):
            chunk = text[start:start + CHUNK_SIZE]
            emb = embedder.encode(chunk)
            _index.append((md_file.name, chunk, emb))


def _retrieve(query: str, k: int = TOP_K) -> list[tuple[str, str]]:
    """Return top-k chunks by cosine similarity."""
    if not _index:
        _build_index()
    embedder = _get_embedder()
    q_emb = embedder.encode(query)
    scored = []
    for doc_id, chunk, emb in _index:
        denom = float(np.linalg.norm(q_emb) * np.linalg.norm(emb) + 1e-8)
        score = float(np.dot(q_emb, emb) / denom)
        scored.append((score, doc_id, chunk))
    scored.sort(reverse=True, key=lambda x: x[0])
    return [(doc_id, chunk) for _, doc_id, chunk in scored[:k]]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

PROMPT = """\
You are a customer-support assistant for Acmepay. Use the policy context below \
to answer the user's question. If the answer is in the context, cite the source \
doc IDs.

Context:
{context}

User question: {question}
"""


def ask(question: str) -> Response:
    """Take a question, return a structured Response."""
    chunks = _retrieve(question)
    context = "\n\n".join(f"[{doc_id}]\n{text}" for doc_id, text in chunks)
    prompt = PROMPT.format(context=context, question=question)

    client = instructor.from_litellm(completion)
    response = client.chat.completions.create(
        model=MODEL,
        response_model=Response,
        messages=[{"role": "user", "content": prompt}],
    )
    return response


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "What's the standard transaction fee?"
    response = ask(question)
    print(json.dumps(response.model_dump(), indent=2))
