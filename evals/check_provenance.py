"""Provenance check: every derived constant still matches its source document.

The rule this enforces is the one that keeps the system from being tuned to the
evals: a derived field is legitimate only if its definition traces to a policy
document or a schema field. Here that trace is executable. If a policy sentence
is reworded, this fails loudly rather than letting the system keep computing a
band from a threshold the docs no longer state.

Exit code = number of failures, matching evals/runner.py's convention so it gates
in CI without adding a test dependency.
"""
from __future__ import annotations

import sys

from copilot.corpus import doc_text, sections
from copilot.enrich import PROVENANCE
from copilot.text import collapse


def main() -> int:
    docs = doc_text()
    failures = 0
    for name, (doc_id, heading_fragment, quote) in sorted(PROVENANCE.items()):
        if doc_id not in docs:
            print(f"FAIL {name}: no such policy document {doc_id!r}")
            failures += 1
            continue
        if collapse(quote) not in collapse(docs[doc_id]):
            print(f"FAIL {name}: quote not found in {doc_id}: {quote!r}")
            failures += 1
            continue
        in_section = any(
            heading_fragment.lower() in s.breadcrumb.lower()
            and collapse(quote) in collapse(s.body)
            for s in sections()
            if s.doc_id == doc_id
        )
        if not in_section:
            print(f"FAIL {name}: quote found in {doc_id} but not under a heading "
                  f"matching {heading_fragment!r}")
            failures += 1
            continue
        print(f"ok   {name:22} {doc_id} > ...{heading_fragment}...")
    print(f"\n{len(PROVENANCE) - failures}/{len(PROVENANCE)} constants traced")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
