# Local-model run — `ollama_chat/qwen2.5:7b-instruct`

Recorded 2026-08-29. Artifacts in this directory only; the hosted-model artifacts in
`grade_artifacts/` are untouched.

| | file |
|---|---|
| copilot, visible suites | `sweep-ollama-visible.json`, `visible.log`, `visible.err` |
| starter, visible suites | `sweep-ollama-baseline.json`, `baseline.log`, `baseline.err` |
| driver | `run.sh`, `run.log` |

Both runs: all 8 visible suites, 100 cases, `--samples 1`, `--workers 1`.

---

## Headline

| System | Model | Score |
|---|---|---|
| Copilot | `qwen2.5:7b-instruct` (local) | **72 / 100** |
| Copilot | `gemini-flash-lite-latest` (hosted) | 96 / 100 |
| Starter | `qwen2.5:7b-instruct` (local) | **0 / 100** |
| Starter | `gemini-flash-lite-latest` (hosted) | 15 / 100 |

Per category, copilot on the local model:

| Category | Score |
|---|---|
| tool_use | 13/13 (100%) |
| investigation | 16/18 (89%) |
| hallucination | 6/7 (86%) |
| refusals | 10/13 (77%) |
| out_of_scope_actions | 6/8 (75%) |
| factual_lookup | 11/15 (73%) |
| multi_doc_synthesis | 5/13 (38%) |
| drafting | 5/13 (38%) |

Cost $0.00. Wall clock 3311s copilot / 546s starter, against ~44s per LLM call —
roughly 40× the hosted latency. 121 LLM calls, 25 repairs, 224 tool calls.
4 of 100 generations fell back to the deterministic path, so `valid_measurement`
is true; on the 96 clean cases the score is 70/96 (72.9%), i.e. the same rate.

---

## The starter's 0/100 is not a retrieval result

All 100 cases failed with the identical error — `InstructorRetryException: No tool
calls or function call found in response (mode: TOOLS)` — and the starter's `ask()`
has no exception boundary, so the runner scores each as a hard zero. qwen2.5 answers
in prose instead of emitting a tool call, and `instructor`'s default tool-calling mode
has nothing to parse.

Its prose was frequently *correct*. On `factual_lookup_001` the discarded completion
read "they do **not** get the original processing fee back … retained by Acmepay",
which is the right answer. So the honest reading of 0/100 is **a structured-output
compatibility failure, not a measurement of the starter's RAG quality**. Quote it as
such.

It is still a real robustness difference. The copilot hits the same provider
behaviour — 4 cases degraded — but `ask()` catches it and returns a deterministic
answer assembled from the records already fetched, so those cases are scored rather
than zeroed. Two of the four still passed.

The starter was run verbatim; nothing was adapted to make it work or to make it fail.

## Two changes were needed to measure the local model at all

1. **`num_ctx`.** Ollama truncates any prompt over its server-side context window —
   4096 tokens by default in 0.33 — and reports nothing when it does. The
   full-context design puts ~14.8K tokens in front of the model, so the first
   attempt at this sweep was silently reading a corpus with most of the policies cut
   off. `copilot/generate.py` now sends `num_ctx=16384` for `ollama*` models;
   verified via `/api/ps` reporting `context_length 16384`. **Any earlier local
   number, including my own first smoke test, was measured on a truncated prompt.**
2. **Serial execution.** Ollama queues concurrent requests rather than
   parallelising them. Three workers produced four 600s timeouts and no throughput,
   so the run is `--workers 1` with a 900s deadline.

Both are gated on the model string, so the hosted path is byte-identical to before.
The starter needed neither: its prompt is ~800 tokens and fits in 4096.

---

## Where the 28 points went

The failure list is dominated by one shape: **a specific quantity that is present in
the injected context and absent from the answer.** `$0.30`, `2.9%`, `T+5`, `1.0%`,
`0.7%`, `15%`, `$15`, `403`, `/v1/refunds`, `account.warning_issued`, `2.4%`, `$99`,
`7 day`, `24 hour`. Eleven of the thirteen `multi_doc_synthesis` and `drafting`
failures are of exactly this kind, and several are cases where the surrounding prose
is correct and only the figure is paraphrased away or omitted.

That is a recall-under-long-context failure, and it is the cost of the central design
bet. Full-context injection buys 100% recall *of the corpus*; it does not buy the
model's attention, and a 7B model at 14.8K tokens has measurably less of it than a
hosted model at the same length. The architecture's own framing — "recall ≠
attention" — predicts this direction; what the run adds is the magnitude.

**What did not move:**

- `tool_use` 13/13, unchanged from hosted. Expected: routing is deterministic
  first-hop saturation with zero LLM participation, so the model tier cannot touch
  it. 37/37 tool assertions and 0 forbidden-tool violations hold on any provider.
- `investigation` 16/18 and `hallucination` 6/7 held up, because those answers lean
  on Python-computed derived fields and on mandated verdict sentences rather than on
  the model recovering a figure from context.

**What moved most:** the three `refusals` misses (`004`, `008`, `011`) all failed
`refused == True` — the disposition judgement is the one part of the pipeline that is
genuinely delegated to the model, and it degrades with model capability. The
beneficiary-detection and liability cases are the exact ones the architecture flags
as judgement rather than mechanism.

**The reading:** the deterministic layers are provider-independent, as designed, and
they are what survives a 7B local model. The delegated layers — verbatim figure
recall and disposition judgement — are where a weaker model costs 24 of the 28
points.

---

## Caveats

- `--samples 1`. No majority-of-3, so marginal cases are single draws. The hosted
  system's 96/100 was also `--samples 1`; the `--samples 3` hosted attempt is
  quota-invalid (`sweep-visible-s3.json`, `valid_measurement: false`).
- Ollama's default sampling is not greedy across the board even at
  `temperature=0`, so a repeat run will not necessarily be byte-identical. The
  deterministic layers (`tool_calls`, derived fields, mandated verdicts) will be.
- Paraphrase suites were not re-run on this model.
