# Retrieval regime comparison — `ollama_chat/qwen2.5:7b-instruct`

Recorded 2026-08-30 on branch `v2-augmented-retrieval`.

**Question:** does switching the policy corpus from full verbatim injection to
hybrid BM25+dense top-12 retrieval change the graded score?

**Method:** same model, same harness, same flags (`--samples 1 --workers 1`,
`ACMEPAY_RPM=0`, `OMP_NUM_THREADS=1`). The *only* variable is
`ACMEPAY_RETRIEVAL_MODE`. Driver scripts are `run.sh` in each directory.

| | artifacts |
|---|---|
| `full` (baseline) | `../ollama-qwen2.5-7b/sweep-ollama-visible.json` |
| `hybrid` top-12 | `sweep-hybrid-visible.json`, `visible.log`, `visible.err` |

---

## Score: no meaningful change

| Suite | `full` | `hybrid` | Δ |
|---|---|---|---|
| `drafting` | 5/13 | 5/13 | +0 |
| `factual_lookup` | 11/15 | 10/15 | -1 |
| `hallucination` | 6/7 | 6/7 | +0 |
| `investigation` | 16/18 | 16/18 | +0 |
| `multi_doc_synthesis` | 5/13 | 6/13 | +1 |
| `out_of_scope_actions` | 6/8 | 6/8 | +0 |
| `refusals` | 10/13 | 9/13 | -1 |
| `tool_use` | 13/13 | 13/13 | +0 |
| **TOTAL** | **72/100** | **71/100** | **-1** |

Five of eight suites are identical. Three moved by exactly ±1 and partly cancel.
±1 per suite is the same nondeterminism band observed between two runs of the
*same* configuration elsewhere in this repo, so at `samples=1` there is no basis
for calling 71 different from 72. **Read this as flat, not as a regression.**

## Cost: this is where the change lands

| | `full` | `hybrid` | Δ |
|---|---|---|---|
| prompt tokens | 1,659,191 | 1,191,782 | **-28%** |
| completion tokens | 17,494 | 18,863 | +8% |
| LLM calls | 121 | 119 | -2 |
| repairs | 25 | 26 | +1 |
| errors | 4 | 7 | +3 |
| wall clock | 55 min | 72 min | +31% |

### Three findings worth carrying into the write-up

**The 76% policy-token saving becomes -28% at the whole-prompt level.**
Offline, the policy block drops 4,602 → 1,119 tokens. But policy is a minority of
the prompt: the system block also carries the portfolio digest, the precedent
index, and the role/disposition/style contract, none of which retrieval touches.
The whole-prompt figure is the honest one to quote.

**Errors rose 4 → 7, and the new ones are a specific defect.**
3 of them are qwen returning a `Draft` with a `DECLINE_*` disposition but
omitting the required `verdict` field, which `instructor` cannot repair, so the
request lands in `_fallback()` — answering with `refused=False`. Zero such
failures occurred under full injection. A narrower context appears to push a 7B
model toward declining more readily. This is a real cost of the change, not noise.

**It got slower despite sending fewer tokens** (+31%).
The dense encoder now runs once per query, competing with `llama-server` for CPU
under `OMP_NUM_THREADS=1`. On a hosted endpoint this would likely invert; locally
the embedder contention dominates the token saving. Both runs also stalled on
3 × 900s `_LOCAL_TIMEOUT_S` timeouts, so ~30 min of each wall time is
neither retrieval nor inference.

**Predicted effect that did not appear:** the repair rate was expected to climb,
since under retrieval a true corpus fact can sit outside the injected slice and
trip the `ungrounded` validator, which was structurally impossible under full
injection. It moved 25 → 26.

## Limits of this measurement

- One model, and a weak one: 7B local, scoring 71/100 where the hosted model
  scored 96/100. Conclusions may not transfer.
- `samples=1`, n=100. Supports "no large accuracy change"; does **not** support
  "equivalent" at any precision.
- Offline retrieval recall was measured separately and is exact: **27/28 at k=12,
  28/28 at k=20** on the 28 visible cases asserting `must_cite`. The one k=12 miss
  is `multi_doc_synthesis_007`.
- A hosted-model run is needed before the write-up claims parity.
