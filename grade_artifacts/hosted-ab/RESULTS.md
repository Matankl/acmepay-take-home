# Hosted A/B — retrieval regime, `gemini/gemini-flash-lite-latest`

Recorded 2026-08-30, branch `v2-augmented-retrieval`.

**Question:** does hybrid top-12 retrieval cost graded accuracy versus full
verbatim injection?

**Method:** same key, same code, same flags (`--samples 1`, sweep default
`--workers 8`), back to back. `ACMEPAY_RETRIEVAL_MODE` is the only variable.
Drivers: `run-hybrid.sh`, `run-full.sh`. Zero rate-limit and zero schema errors in
both arms.

## Result: no accuracy difference, 29% cheaper

| Suite | `full` (B) | `hybrid` k=12 (A) | Δ |
|---|---|---|---|
| drafting | 11/13 | 11/13 | +0 |
| factual_lookup | 13/15 | 13/15 | +0 |
| hallucination | 7/7 | 7/7 | +0 |
| investigation | 17/18 | 18/18 | +1 |
| multi_doc_synthesis | 11/13 | 10/13 | -1 |
| out_of_scope_actions | 7/8 | 7/8 | +0 |
| refusals | 13/13 | 13/13 | +0 |
| tool_use | 13/13 | 13/13 | +0 |
| **TOTAL** | **92/100** | **92/100** | **+0** |

| Metric | `full` | `hybrid` | Δ |
|---|---|---|---|
| prompt tokens | 1,569,785 | 1,116,923 | **-29%** |
| cost | $0.17 | $0.12 | -27% |
| LLM calls | 108 | 111 | +3 |
| repairs | 8 | 11 | +3 |
| errors | 0 | 0 | 0 |
| wall clock | 9.1 min | 9.7 min | +7% |

**Retrieving 20% of the corpus costs nothing measurable and saves 29% of prompt
tokens.** That is the finding.

## Why the control arm mattered

Arm A alone read as a 4-case regression, because the only available comparator was
a **96/100 recorded under older code**. With the control run on identical code,
`full` also scores 92 — so the apparent regression was never the retrieval switch.
Two possibilities remain for the 96→92 gap, and this A/B cannot separate them:
other changes made in the same session, or the documented 92/88/96 run-to-run band
(92 sits inside it). **The recorded 96/100 did not reproduce today.**

## Per-case churn: the real noise floor

Totals are identical, but the *cases* are not:

- failed only under `hybrid`: drafting_006, drafting_011, multi_doc_synthesis_007, multi_doc_synthesis_008
- failed only under `full`: drafting_001, drafting_007, investigation_015, multi_doc_synthesis_011
- failed under both: factual_lookup_001, factual_lookup_014, multi_doc_synthesis_003, out_of_scope_actions_008

Four cases each way at an identical total. **That is the honest measure of
single-sample noise on this provider: ±4 cases of churn with zero net movement.**
Any conclusion drawn from a delta smaller than that is unsupported.

## The one pre-registered prediction that held

Offline recall analysis identified `multi_doc_synthesis_007` as the single k=12
miss (it needs `fees_and_pricing` and `settlement_timing`, retrieves only the
latter). It **failed under `hybrid` and passed under `full`** — the predicted
mechanism, observed. But it is one case inside a ±4 churn band, and
`multi_doc_synthesis` overall moved only 11/13 → 10/13. Directionally consistent,
not statistically established.

`bm25` k=12 and `hybrid` k=20 both reach 28/28 offline recall and would close that
case. `bm25` additionally drops the embedder entirely (no 90 MB load, no thread
lock). Untested end-to-end.

## Limits

- `samples=1` on both arms. The churn above shows why `--samples 3` is needed to
  resolve anything finer than ~4 cases.
- One model, one provider, n=100.
- Supports "no measurable accuracy cost for 29% fewer tokens". Does **not** support
  "identical" — it supports "indistinguishable at this sample size".
