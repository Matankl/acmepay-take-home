"""Eval suite for the Acmepay Support Copilot.

Visible eval cases live here (shipped to candidates so they can iterate).
Held-out cases live in `_internal/evals_holdout/` and are not shipped.

The grader is deterministic and structured-output based:
  - substring matches over the `answer` field
  - subset checks over `cited_doc_ids`
  - tool-call expectations (name + args subset)
  - refusal flag + reason

No LLM-as-judge. Per-case scoring is binary.
"""
