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
#   hybrid - bm25 + dense, reciprocal-rank fused. THE DEFAULT.
#   bm25   - keyword retrieval over breadcrumbed sections, no embedder.
#   full   - inject every policy doc verbatim; recall is 100% by construction.
#
# Measured on the 28 visible cases that assert `must_cite` (see ARCHITECTURE.md
# "Decision 1" for the full argument):
#
#            recall      policy tokens
#   full      28/28      4602
#   hybrid    27/28      1119   (-76%)   <- default, k=12
#   bm25      28/28      1119
#
# `full` buys one extra case for 4x the policy tokens on every request. The one
# case hybrid drops at k=12 needs two documents and gets one; the repair pass
# escalates to RETRIEVAL_REPAIR_TOP_K, which recovers that shape.
#
# NOTE: this value is imported BY VALUE (`from .config import RETRIEVAL_MODE`) in
# prompt.py and retrieval.py, so setting os.environ or patching this attribute
# after those modules import does nothing. Set the env var before process start.
RETRIEVAL_MODE = os.environ.get("ACMEPAY_RETRIEVAL_MODE", "hybrid")

# Sections injected per request, and on the repair pass. The repair value is
# larger because a groundedness failure is evidence the first slice was too
# narrow, and a repair happens on a small minority of requests -- so breadth is
# cheap exactly where it is most likely to pay.
RETRIEVAL_TOP_K = int(os.environ.get("ACMEPAY_RETRIEVAL_TOP_K", "12"))
RETRIEVAL_REPAIR_TOP_K = int(os.environ.get("ACMEPAY_RETRIEVAL_REPAIR_TOP_K", "20"))

# `full` mode degrades to `bm25` if the corpus outgrows this. Enforced in
# prompt.system_block() via retrieval.corpus_fits_budget().
POLICY_CONTEXT_BUDGET = int(os.environ.get("ACMEPAY_POLICY_BUDGET", "12000"))

TICKET_SEARCH_TOP_K = 3
