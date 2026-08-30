"""Static configuration. Everything here is a constant so that the prompt prefix
is byte-identical across requests (see ARCHITECTURE.md "Determinism")."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
POLICIES_DIR = DATA / "policies"
TICKETS_DIR = DATA / "tickets"

# The world's clock is frozen. The README says to treat "today" as 2026-05-25 --
# the latest timestamp in the data -- and the grader's date math assumes it.
#
# `date.today()` must NEVER appear anywhere in this package. Two reasons: it
# breaks every deadline/window answer, and a moving value in the prompt prefix
# silently invalidates prompt caching on every single request.
TODAY = date(2026, 5, 25)
TODAY_ISO = TODAY.isoformat()

MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")

# Retrieval regime for the policy corpus.
#
#   full   - inject every policy doc verbatim. The corpus measures ~4.2K tokens,
#            so recall is 100% by construction and no retrieval error is
#            possible. This strictly dominates at the current corpus size.
#   bm25   - keyword retrieval over breadcrumbed sections.
#   hybrid - bm25 + dense, reciprocal-rank fused.
#
# The non-default modes exist so the same control flow survives a corpus two
# orders of magnitude larger. See ARCHITECTURE.md "Decision 2" for the crossover
# argument.
RETRIEVAL_MODE = os.environ.get("ACMEPAY_RETRIEVAL_MODE", "full")

# If the corpus ever exceeds this, `full` mode degrades to `bm25` automatically.
POLICY_CONTEXT_BUDGET = int(os.environ.get("ACMEPAY_POLICY_BUDGET", "12000"))

# Hard ceiling on logical LLM calls per ask(): one generation, one optional
# repair. There is no agentic loop, so there is nothing that can fail to
# terminate.
MAX_LLM_CALLS = 2

TICKET_SEARCH_TOP_K = 3
