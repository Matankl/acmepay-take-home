# Solution Write-Up — Acmepay Support Copilot

**Your name:** Matan Ziv
**Time spent (rough):** ~14 hours
**Model(s) / provider used:** `gemini/gemini-flash-lite-latest` via litellm and `ollama_chat/qwen2.5:7b-instruct` via litellm

> Full reasoning, including the decisions I got wrong first: **`ARCHITECTURE.md`**.
> Measurement artifacts: **`grade_artifacts/`**.

---

## 1. Summary

**15/100 → 92/100 on the visible suites**, one LLM call for a typical question,
~1.2 cents per question. An earlier sweep recorded 96/100 under full policy
injection; that number did not reproduce a day later on today's code, so 92 is the
figure I stand behind (§3).

The headline: **I moved everything with a single correct answer out of the model.**
Tool selection, argument extraction, date arithmetic, threshold banding, cross-merchant
aggregation and citation attribution are deterministic Python; the model decides what
matters and writes the prose. The assignment being model-neutral, that pays off: the
deterministic layers score identically on a 7B local model and a hosted one.

---

## 2. What I changed and why

### Retrieval

The starter retrieved over the corpus that doesn't need it and ignored the one that
does. Policies are 4,602 tokens; ticket history is 10,159 and contains answers present
in no policy document. And `tools/search_policies.py` returns `path.read_text()` —
whole documents — so `top_k=3` already ships half the corpus *plus* selection error.

Chunking is on markdown headings, breadcrumbed
(`[chargeback_policy.md > Excessive Chargebacks — Thresholds]`), because the corpus is
full of numeric collisions: `1.0%` is both the monitoring threshold and the
currency-conversion fee, `1.5%` both the international surcharge and the suspension
threshold, `24 hours` has three unrelated meanings. A value resolves only with its
section. `merchant_faq.md` gets a Q/A splitter — its atomic unit is a bold `**Q:**`.

**First I injected the whole corpus** (recall 100% by construction), then found that
*recall is not attention*: every remaining policy failure was navigational — the figure
was in context and went unused when the question's wording missed the policy's
terminology ("petitioned Acmepay's review path" vs "Appeal Process for Restricted
Categories"). A **policy index** of all 59 headings fixed it — the model bridges the
synonym once it sees the menu. The BM25 pointer only helps on shared rare terms.

**Then I switched the default to hybrid retrieval** (section-level BM25 fused with
dense embeddings by reciprocal rank, top-12 of 59) and measured both regimes as a
controlled A/B — same key, same code, same flags, mode the only variable:

| | `full` | `hybrid` k=12 |
|---|---|---|
| score | 92/100 | **92/100** |
| prompt tokens | 1,569,785 | **1,116,923 (-29%)** |
| errors | 0 | 0 |

One corpus gap drives a whole component: `statement descriptor` appears in **no** policy
document yet is the subject of 9 of 55 tickets, so `copilot/precedent.py` collapses the
55 tickets to ~18 subjects as a mechanical group-by, always in context.

**Retrieving 20% of the corpus costs nothing measurable and saves 29% of prompt
tokens.** A local `qwen2.5:7b-instruct` run agreed (72 vs 71, -28%), so it holds across
a weak and a strong model.

### Tool use

`copilot/gather.py` is three clauses: **first-hop saturation** (for every entity
named, call every tool accepting it — no intent classification, so nothing for a
paraphrase to misclassify), **bounded transitive expansion** suppressed for
single-record field reads, and **never call `search_policies`**.

Saturation earns evidence rather than special-casing it: asking only for M-1006 also
reads its audit log, the only place a rejected applicant's rejection is recorded.

**Merchant names — I got this wrong twice before committing.** Requiring
`question_tokens ⊆ name_tokens` fails ("Maple & Mortar's payout" has no "bakery"); the
mirror form breaks on *added* tokens ("Lumen Travel Inc."), exactly what a paraphraser
produces. Abstaining on ambiguity is strictly wrong — extra calls are free. Final form:
score by coverage of the *name*, fetch every tied candidate, plus a data-derived guard —
**a match must include a token absent from the policy corpus**, so "travel" can't
identify a merchant but "lumen" can. Edit distance is not used: it "corrects" Verdant
Wellness to Verona Pasta Co.

### Prompting / system design

One `instructor` call returns an internal `Draft`, projected down to `Response`. Every
internal field is consumed by a validator or the projection: `verdict` forces
bottom-line-first structurally, `key_facts` turns hallucination detection into substring
search, and there is deliberately **no `tool_calls` field** — the starter passed
`Response` straight in as the `response_model`, so the model reported calls it never
made.

`instructor.from_litellm` defaults to tool-calling mode, consuming the tool channel to
extract the response model, so handing the model the eight real tools would cost either
the structured output or a round trip. Because gathering is deterministic there are no
tools to pass — the topology choice and the structured-output choice are one choice.

### Refusal & grounding

`refused` is a projection of a three-way disposition, **decided from the request, not
from what the records say.** The case that forced it: *"Why exactly did the customer's
bank decline the card on T-99820?"* — T-99820 is `status: "pending"` and was never
declined. Letting enrichment drive the disposition produces an honest, helpful,
**wrong-dispositioned** answer. The request is for the issuer's internal reason, which
Acmepay categorically cannot hold. Boundary, not gap.

The rest: **unknowable → decline, unrecorded → answer** (next quarter's ratio vs the
ratio six months ago — same absent datum, opposite verdicts, and the distinction is
epistemic so it survives rewording); cross-merchant guarded twice; multi-part is OR.

Two rules exist purely against **over-refusal**, graded as harshly as fabrication: topic
adjacency is not a boundary, and a documented capability is answerable. The sharpest case
is a real corpus tension — `merchant_faq.md` says pre-transaction IPs aren't stored while
`chargeback_policy.md` recommends "IP address … at time of transaction" as evidence.
**The boundary is temporal scope, not the phrase "IP address."**

**Citations** are derived by code from the answer's own content, not authored by the
model — the biggest hole in my first plan. `copilot/cite.py` takes salient atoms
(amounts, percentages, endpoints, header names, status codes) plus verbatim n-grams
from `key_facts` and attributes each to every document literally containing it. The
claim is checkable: *every cited document literally contains a string the answer used,
and was shown to the model.* No visible case forbids a citation, so "always cite all
six" would pass 43/43 in two lines. I didn't — an unused matcher field in a schema
built for a held-out set is a loaded gun.

### Control flow

`gather → generate → validate → repair`, where **the validator, not the model, requests
more evidence.** No agentic loop: 1 call typical, 2 worst case, ever. I rejected a tool
loop on measurement, not taste — deterministic routing gets 29/29 required calls with
zero LLM involvement, and a loop would need luck on the two `forbidden_tools` cases
every run.


### Reformat Before Validation

`copilot/entities.py` extracts loosely, emits canonically: prefixed IDs with any
separator and any dash variant, plus bare numbers beside a type word. The grader compares
arguments with exact `==`, so an en-dashed `D–503` scores zero — and paraphrase
generators emit typographic dashes constantly.

---

## 3. Results

Baseline is the untouched starter at `scripts/baseline_system.py`, same harness.
`--samples 1`, hosted `gemini-flash-lite-latest`.

| Category | Before (starter) | After |
|---|---|---|
| factual_lookup | 7/15 | **13/15** |
| multi_doc_synthesis | 4–5/13 | **10/13** |
| refusals | 2/13 | **13/13** |
| tool_use | 0/13 | **13/13** |
| drafting | 1–10/13 | **11/13** |
| investigation | 0/18 | **18/18** |
| hallucination | 0–1/7 | **7/7** |
| out_of_scope_actions | 0/8 | **7/8** |
| **TOTAL** | **15–24/100** | **92/100** |


**Cases I couldn't pass.** 3, and only one is a real bug.

- **`factual_lookup_001`** — the case forbids the phrase "processing fee back", but the
  question *is* "do they get the original processing fee back?" Any direct answer repeats
  the words. Unwinnable as written.
- **`drafting_011`** — the reply needed `2.4%` and `$99`. Both are policy facts with no
  record behind them, so there is no computed field to hand the model; it has to pull
  them out of prose while writing, and sometimes doesn't.

- **`out_of_scope_actions_008`** — fails in both retrieval modes; I haven't diagnosed it.

`drafting` is my weakest category, and its failures **move between runs**. That is the
honest headline: it means I don't yet know what is wrong with it, only that something is.

---

## 4. Tradeoffs & things I'd do with more time

**Deliberately skipped or simplified**

- A hybrid dense retriever over *tickets*. BM25 is enough once the archive is grouped:
  the top 10 of 18 subjects cover 36 of 55 tickets and sit in context permanently, so
  only a ~19-ticket tail is ever retrieved — and rare questions carry distinctive
  vocabulary, exactly where BM25 beats embeddings.
- A hand-written `POLICY_CONSTANTS` threshold table — a second source of truth for
  values already in context, and it reads as tuning. Replaced by a **generated**
  collision map scanning for quantities that appear under more than one heading.

**Next 8 hours, in order**

1. Visible suites at `--samples 3`. The A/B showed ±4 cases of single-sample churn, so
   this is the measurement everything else depends on — and it is not a code change.
2. A **lightweight topic guardrail on the query**, run during gather — question only, no
   records. Flags out-of-scope or act-on-my-behalf requests before a token is spent.
3. **Benchmark the embedding choice** MiniLM looks sufficient but there might be a better embedding.
4. Extend the verdict-template layer to policy-answer shapes, not just record shapes —
   templating took `investigation` to 18/18, and majority-vote maths rewards variance
   reduction over new capability.
5. Delete the style substitution table and re-measure — the one component whose shape
   was set by the grading rather than the problem.

**What I think is wrong or unsupported in the assignment**

- **The data is too small to resemble production, and that cuts both ways.** Several of
  my best decisions are scale artifacts: the subject-line `group-by` works because the
  55 tickets share 18 *exact-duplicate* subjects (real archives are free text); tool
  saturation is free because the tools are local file reads, not rate-limited APIs; the
  digest fits in context because there are 34 merchants, not 34,000. Conversely, what
  production *requires* — retrieval, a real index — scores nothing here and reads as
  over-engineering. The suites can't separate good engineering from a correctly
  exploited small dataset, in either direction.
---

## 5. Correctness & safety notes

**Not inventing facts** — four layers, weakest to strongest:

- *Structural* — the opening sentence is composed from the record, so a missing merchant
  produces "…is not an Acmepay merchant: rejected on 2026-05-18". There is nothing to
  hang a fabricated settlement schedule on.
- *Derived, not inferred* — the model **reads** `deadline_state`, `risk_band` and signed
  day counts. It never does the arithmetic, so it can't get it wrong.
- *Checked* — every `key_facts` claim must be a substring of the context it was given.
- *Attributed* — citations come from the answer's own text, so an invented filename
  cannot survive.

**Refuse vs answer.** Covered in §2: `refused` is a projection of an explicit
disposition, decided from the request so record state can't contaminate it. Note I left a
free exploit unused — on the 41 cases where the refusal expectation is unset the flag is
never checked, so defensive `refused=True` there would be costless. That is grader-gaming.

**The digest is deliberately lossy.** It carries no volume and no category column: an
always-on roster of volumes and brand names is exactly what makes "list the other
merchants in this category with their volumes" *answerable*. It also emits `risk_band`
instead of raw ratios, so a merchant under the threshold is **structurally absent** from
an "at or above" answer rather than something the model must remember to leave out.

**Cost / latency.** ~1.2 cents and ~1–2 s per question; 1 LLM call typical, 2 worst
case, hard-bounded. Prompt caching is *measured* from the provider's usage counters, not
assumed.

---

## 6. How to run your solution

Nothing beyond the README — `LLM_MODEL` from `.env` is used as-is, no dependency added.

```bash
# one question, telemetry on stderr
python system.py "Is Lumen Travel about to be suspended over their chargeback rate?"

# the shipped runner, untouched; then every suite in parallel -> grade_artifacts/
python -m evals.runner investigation_visible --verbose
python -m scripts.sweep [--samples 3]

# the "before" column. --workers 1 is REQUIRED: the starter's module-level index
# has no lock and corrupts under concurrency.
python -m scripts.sweep --system scripts.baseline_system --baseline --workers 1 --rpm 10

# generalization set (29 lexical / structural / adversarial paraphrases)
python -m scripts.sweep --suites paraphrase_lexical paraphrase_structural paraphrase_adversarial

# provider-independent checks; exit code = failure count
python -m evals.check_provenance && python -m evals.check_no_leakage && python -m evals.check_hedge_coverage
```

Two knobs. `ACMEPAY_RPM` (default 12) caps the copilot's own request rate — without it a
parallel sweep measures the quota rather than the system. `ACMEPAY_RETRIEVAL_MODE`
(`hybrid` default | `bm25` | `full`) selects the policy regime and
`ACMEPAY_RETRIEVAL_TOP_K` its width; **both must be set before process start**, since
the value is imported by value.
