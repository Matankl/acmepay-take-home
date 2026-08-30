# Eval Baseline — Unmodified Starter

Reference run of the **untouched `system.py` baseline** against the 8 visible eval
suites. Recorded so later runs can be compared against a known starting point.

## Run configuration

| | |
|---|---|
| Date | 2026-08-25 |
| Code under test | `system.py` **unmodified** (naive policy-doc RAG, 500-char chunks, `TOP_K=3`) |
| Tools called | **none** — the baseline calls 0 of the 8 tools in `tools/` |
| Model | `gemini/gemini-flash-lite-latest` (Gemini free tier) |
| Embeddings | `all-MiniLM-L6-v2`, local (40 chunks indexed) |
| Runner | all 8 suites in a single process, 1 sample per case |
| Wall clock | 2516s (~42 min) for 100 cases |

## Results — 24/100 (24%)

| Suite | Passed | Pct | sys_err | Secs |
|---|---|---|---|---|
| `factual_lookup_visible` | 7/15 | 47% | 0 | 459 |
| `multi_doc_synthesis_visible` | 4/13 | 31% | 0 | 901 |
| `refusals_visible` | 2/13 | 15% | 0 | 288 |
| `tool_use_visible` | 0/13 | 0% | 0 | 329 |
| `drafting_visible` | 10/13 | 77% | 0 | 408 |
| `investigation_visible` | 0/18 | 0% | 0 | 116 |
| `hallucination_visible` | 1/7 | 14% | 0 | 11 |
| `out_of_scope_actions_visible` | 0/8 | 0% | **4** | 5 |
| **TOTAL** | **24/100** | **24%** | **4** | **2516** |

## Reading the numbers

**`drafting` 77% is the high-water mark.** Drafting is graded on facts, not tone, and
most of those facts sit in the policy docs the naive RAG already retrieves. It needs
no tools, so the baseline is already near-competent here.

**`tool_use` 0/13 and `investigation` 0/18 are structural, not incidental.** The
baseline never calls a tool, so `tool_calls` is always empty and those graders have
nothing to match. 31 of the 100 cases are unreachable without wiring up tool routing.
The README says to expect exactly this.

**`refusals` 15% and `hallucination` 14% are the subtler gaps.** These test the
`refused=True` vs `refused=False` distinction the README draws: declining to *act*
→ `refused=True`; reporting that information is unavailable → `refused=False`. The
baseline's refusal logic is generic (its own docstring admits this), so it lands on
the wrong side of that line most of the time. No tools required to fix — this is
prompt and control-flow work.

**`investigation` was the *fastest* suite per case (~6s).** It ran quickly precisely
because it fails: with no access to the structured records, the model has little to
work with and emits short answers.

## Caveats

**Nondeterminism: treat these as ±1 case.** An earlier partial run of the same code
and model scored `multi_doc_synthesis` at 5/13 where this run got 4/13. `refusals`
(2/13) and `factual_lookup` (7/15) reproduced exactly across runs. For stable
figures use `--samples 3` (majority vote, 3× runtime).

**The 4 `sys_err` in `out_of_scope_actions` are undiagnosed.** That suite failed in
5s at the very end of a 42-minute run. The raw error text was lost before it could be
inspected, so its true score is unknown — 0/8 is a floor, not a measurement. Re-run
that suite alone to get a real number:

```bash
python -m evals.runner out_of_scope_actions_visible --verbose
```

**Model is weak.** `flash-lite` is the least capable model in the Gemini family; some
failures reflect its structured-output and reasoning limits rather than the retrieval
logic. Treat 24% as a floor for this code, not a verdict on it.

## Free-tier gotchas hit along the way

- `gemini-2.5-flash`, `gemini-2.0-flash`, `gemini-2.5-flash-lite` all return **404
  "no longer available to new users"** on newly-created keys.
- `gemini-3.6-flash` has a free-tier quota of **20 requests per day**
  (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`). One 15-case suite exhausts
  it. The API's "retry in 57s" message is misleading — the window is 24h.
- `gemini-flash-lite-latest` has a workable quota: **0 rate-limit errors across all
  100 cases**.
- A full run needs ≥100 requests; an agentic version calling tools would need several
  per case, so hundreds. The free tier is marginal for iteration — a paid key
  (cents on `gpt-4o-mini`) or local Ollama is the practical path.

## Performance note for future runs

The first LLM call in a fresh process costs **~150s of cold start**; subsequent calls
are ~1s. Running each suite as its own subprocess pays that 8 times over (~48 min of
pure overhead) and reloads MiniLM each time. **Run all suites in one process.**