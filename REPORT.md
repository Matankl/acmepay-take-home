# Solution Write-Up — Acmepay Support Copilot

**Your name:** Matan Ziv
**Time spent (rough):** ~10 hours
**Model(s) / provider used:** `gemini/gemini-flash-lite-latest` via litellm.

> Deep dive on every decision, including the ones I got wrong first: **`ARCHITECTURE.md`**.

---

## 1. Summary

**15/100 → 96/100 on the visible suites**, with one LLM call for a typical question
and roughly 1.6 ¢ per question.

The headline: **I moved everything with a single correct answer out of the model.**
Tool selection, argument extraction, date arithmetic, threshold banding,
cross-merchant aggregation and citation attribution are all deterministic Python.
The model does two jobs — decide what matters, and write the prose. That mattered
more than usual here because the assignment is model-neutral so small week models should work as well.

[//]: # (Three structural consequences:)

[//]: # ()
[//]: # (- **29/29 required tool calls and 0/2 forbidden-tool violations are satisfied with)

[//]: # (  zero LLM involvement** &#40;37/37 including my own paraphrase suites&#41;. Tool routing)

[//]: # (  is a regular-language problem, not a reasoning problem.)

[//]: # (- **The policy corpus is 4,227 tokens, so it is injected whole.** Retrieval over it)

[//]: # (  can only subtract. The retrieval effort went where it pays instead.)

[//]: # (- **`tool_calls` is recorded from execution, never authored by the model.** The)

[//]: # (  starter passed `Response` straight in as `instructor`'s `response_model`, so the)

[//]: # (  model filled that field in — it reported calls it never made.)

---

## 2. What I changed and why

### Retrieval — measure the corpus, then put the work where it pays

The starter retrieved over the corpus that doesn't need retrieval and ignored the
one that does. Policies: 4,227 tokens. Tickets: 10,159 tokens, containing answers
that exist in no policy document.

And `tools/search_policies.py` returns `"body": path.read_text()` — **whole
documents, no chunking** — so `top_k=3` already ships ~50 % of the corpus *plus*
document-selection error. It pays half the price of full injection to deliver half
the corpus, chosen by exactly the mechanism the vocabulary-gap cases defeat.

So: inject all six documents verbatim, split on markdown headings and breadcrumbed
(`[chargeback_policy.md > Excessive Chargebacks — Thresholds]`). `merchant_faq.md`
gets a Q/A splitter because its atomic unit is a bold `**Q:**`, not a heading.
Recall becomes 100 % by construction and the embedding model is never loaded.

**Recall is not attention, though** — and this was the single most instructive
measurement of the exercise. At 92/100, *every* remaining policy failure was a
navigation failure: the figure was in context and went unused, typically when the
question's wording missed the policy's own terminology ("petitioned Acmepay's
review path" vs "Appeal Process for Restricted Categories"). Two cheap additions,
both in the cached prefix, took `factual_lookup` to 15/15 and `multi_doc_synthesis`
to 13/13:

- a **policy index** — every document with its section headings (~500 tokens), so
  the model can locate a topic by name before reading;
- a **relevance pointer** — keyword-ranked breadcrumbs of the five likeliest
  sections, *labels only*, since the bodies are already present.

That second one is the honest version of the retrieval story: **a precision hint
layered on full-recall injection, not a substitute for it.** A wrong hint costs
nothing; a right one focuses attention on the paragraph carrying the figure.

`copilot/retrieval.py` is real — chunk-level BM25 fused with dense embeddings by
reciprocal rank, disk-cached content-hash-keyed matrix, one matmul per query — and
`ACMEPAY_RETRIEVAL_MODE=bm25|hybrid` runs the same control flow over a corpus two
orders of magnitude larger, with `full` degrading into it automatically past a
token budget. That makes injection a **measured regime choice with a switch as
proof** rather than a lucky break.

**The corpus has one genuine hole, and it isn't a retrieval problem.**
`statement descriptor` appears in **no** policy document, yet it is the subject of
9 of 55 tickets — the largest question cluster. Worse, `settlement_timing.md`
contains "settlement **statement**", so a keyword search returns a confident wrong
document. `copilot/precedent.py` applies the same insight twice: 55 tickets collapse
to ~18 subjects, so the index is a mechanical group-by (earliest resolved reply per
subject, verbatim, always in context) with BM25 over the bodies for the tail,
reusing the implementation already in `tools/search_policies.py`. Internal agent
notes are stripped, per `get_ticket`'s own warning.

**What I cut:** a hybrid dense retriever over tickets. Zero graded cases need
ticket *bodies*, and arguing retrieval is unnecessary at 4.2 K tokens while
spending a third of the budget on an unused retriever would turn my best argument
into my worst exhibit.

### Tool use — deterministic extraction, then saturation

`copilot/entities.py` extracts loosely and emits canonically: prefixed IDs with any
separator or none and any dash variant, plus bare numbers next to a type word,
widths sanity-checked against the shapes the data files actually use. The grader
compares arguments with exact `==`, so `D 503` and an en-dashed `D–503` are worth
zero, and paraphrase generators emit typographic dashes constantly.

`copilot/gather.py` then applies three clauses: **first-hop saturation** (for every
entity named, call every tool that accepts it — no intent classification, so nothing
for a paraphrase to misclassify), **bounded transitive expansion** suppressed for
single-record field reads, and **never call `search_policies`** (the corpus is
already in context; no case requires it and one forbids it).

Saturation earns evidence rather than special-casing it: asking only for merchant
M-1006 also reads its audit log, which is the only place a rejected applicant's
rejection is recorded. Same code path yields "rejected applicant, declined
2026-05-18" for M-1006 and a clean "no such merchant" for M-1099.

**Merchant names — I prototyped this before committing and got it wrong twice.**
Requiring `question_tokens ⊆ name_tokens` fails ("Maple & Mortar's payout" has no
"bakery"), and the mirror form breaks on *added* tokens ("Lumen Travel Inc."), which
is precisely what a lexical paraphraser produces. And abstaining on ambiguity is
strictly wrong — extra calls are free, while abstaining misses the tool assertion
*and* produces "I can't tell which merchant" prose, which is itself a failure. Final
form: score by coverage of the *name*, keep every tied candidate and fetch all of
them, plus one data-derived guard — **a match must include a token that does not
appear in the policy corpus**, so "travel" and "records" cannot identify a merchant
but "lumen" and "mortar" can. Edit-distance matching is *not* used: it "corrects"
Verdant Wellness to Verona Pasta Co.

### Prompting / structured output

One `instructor` call returns an internal `Draft`, projected down to `Response`.
Every internal field is consumed by a validator or the projection — `verdict`
forces bottom-line-first structurally, `key_facts` turns hallucination detection
into substring search, and there is deliberately **no `tool_calls` field**.

`instructor.from_litellm` defaults to tool-calling mode, so it consumes the tool
channel to extract the response model. A design that also handed the model the eight
real tools would have to give up either the structured output or a round trip.
Because gathering is deterministic there are no tools to pass — the topology choice
and the structured-output choice turn out to be the same choice, and this is also
the most portable option across providers.

### Refusal & grounding

`refused` is a projection of a three-way disposition, **decided from the request,
not from what the records say.** The case that forced that rule: *"Why exactly did
the customer's bank decline the card on T-99820?"* — T-99820 is `status: "pending"`
and was never declined. A system that lets enrichment drive the disposition produces
the honest, helpful, **wrong-dispositioned** answer. The request is for the issuer's
internal reason, which Acmepay categorically cannot hold (its transaction schema has
no decline field at all). Boundary, not gap.

The rest of the procedure: **unknowable → decline, unrecorded → answer** (next
quarter's ratio vs the ratio six months ago — same absent datum, opposite verdicts,
and the distinction is epistemic so it survives rewording); categorical
non-custody grounded in the *tool docstrings* as much as the FAQ; cross-merchant
guarded twice over, by beneficiary detection *and* by a capability floor (no
bulk-listing tool exists); and multi-part is OR — decline, but still explain the
answerable part.

Two rules exist purely against over-refusal, which is graded as harshly as
fabrication: **topic adjacency is not a boundary**, and **a documented capability is
answerable**. The sharpest case is a real tension in the corpus — `merchant_faq.md`
says pre-transaction IPs are not stored while `chargeback_policy.md` recommends "IP
address … at time of transaction" as dispute evidence. Both are correct; **the
boundary is temporal scope, not the phrase "IP address."**

Grounding is enforced by six invariants with at most one repair pass, and
`ask()` never raises — the runner turns any exception into a hard failure, so the
boundary falls back to a deterministic response built from records already on disk.

### Citations

43 cases carry a citation requirement and the multi-document ones AND both sources.
My first design left that to the model; it was the biggest hole in the plan.
`copilot/cite.py` instead derives citations **from the answer's own content** —
salient atoms (amounts, percentages, endpoints, header names, status codes) plus the
verbatim n-grams in `key_facts`, attributed to every document that literally
contains them, with markdown emphasis flattened and progressive truncation for
endpoint paths. The claim is checkable: *every cited document literally contains a
string the answer used.* Measured 41/43 offline with realistic quotes; the two
remainders attribute correctly when probed directly.

No visible case forbids a citation, so "always cite all six" would pass 43/43 in two
lines. I didn't — an unused matcher field in a schema built for a held-out set is a
loaded gun, and the README says the code gets read.

### Control flow

`gather → generate → validate → repair`, where **the validator, not the model,
requests more evidence.** No agentic loop: 1 call typical, 2 worst case, ever. I
rejected a tool loop on measurement, not taste — deterministic routing gets 29/29,
a loop would need luck on the two `forbidden_tools` cases every single run, and
sweep wall-clock *is* the iteration budget.

---

## 3. Results

Baseline is the untouched starter, preserved verbatim at `scripts/baseline_system.py`
and run through the same harness (`--system scripts.baseline_system`). `--samples 1`.

**The starter's score is itself unstable, so I report the range rather than the
number that flatters the delta.** My run measured 15/100; an earlier run of the same
unmodified starter recorded in `EVAL_BASELINE.md` measured 24/100. **The table below uses the
higher, more conservative 24/100 observation as the headline baseline**.

| Category | Before (starter) | After |
|---|---|---|
| factual_lookup | 7/15 (47 %) | **14/15 (93 %)** |
| multi_doc_synthesis | 4–5/13 (~35 %) | **13/13 (100 %)** |
| refusals | 2/13 (15 %) | **12/13 (92 %)** |
| tool_use | 0/13 (0 %) | **13/13 (100 %)** |
| drafting | 1/13 (8 %) | **11/13 (85 %)** |
| investigation | 0/18 (0 %) | **18/18 (100 %)** |
| hallucination | 0/7 (0 %) | **7/7 (100 %)** |
| out_of_scope_actions | 0/8 (0 %) | **8/8 (100 %)** |
| **TOTAL** | **15–24/100** | **96/100** |

The four categories the starter scores exactly zero on are the ones the README
predicts it cannot fake — tool use, investigation, hallucination handling and
action refusal — and they are where the deterministic layers do the work.

Cost and shape of the "after" run: 108 LLM calls for 100 cases (8 repairs),
1.52 M prompt tokens, 22.7 K completion tokens, **$0.16 total** — about 1.6 ¢ per
question. Artifacts in `grade_artifacts/`.


### Cases that failed more, and why

 While no test fails consistently, these represent the most frequent failure modes. 

**1. `factual_lookup_001`** — failed `answer_must_not_contain['processing fee back']`.
The question is *"do they get the original processing fee back?"*, so the forbidden
phrase **is in the question** and a correct answer contains it by construction.

**2. `drafting_008`** — failed `answer_contains_any_of[['7 day', '7 calendar day',
...]]`. The draft gave the deadline *date* but never the window *length*, because the
figure lived only in policy prose and the model had to retrieve it while composing a
merchant reply.

**3. `drafting_011`** — failed `answer_contains_any_of` on both `2.4%` and `$99`. Same
root cause as `drafting_008` and the one I have *not* fixed: those are policy facts
with no record to attach them to, so there is no enrichment field to hold them.
`drafting` is my weakest category (10–11/13) and its failures move between runs, which
by my own variance analysis means **I do not yet know what is actually wrong with
it.**

**What they have in common.** All 3 are cases where the answer is a judgement about
what Acmepay does or does not hold, graded on a single boolean or on whether the prose
lands on one of N accepted phrasings. So those kinds of failures do not reflect the agent's quality.

---

## 4. Tradeoffs & things I'd do with more time

**Deliberately skipped or cut:**

- The hybrid dense retriever over tickets, cut for the reason above. BM25 plus a
  deterministic subject index does the job at a tenth of the cost.
- A hand-written `POLICY_CONSTANTS` threshold table, cut because it was a second
  source of truth for values already in context and reads as tuning. Replaced by a
  **generated** collision map that scans for quantities appearing under more than
  one heading — which found the real hazards: `1.0%` is both the monitoring
  threshold and the currency-conversion fee, `1.5%` both the international surcharge
  and the suspension threshold, `24 hours` has three unrelated meanings.
- No response caching across `--samples` runs. It would make a majority vote
  unanimous by construction and turn a reproducibility measure into a lie. Tool
  layer, corpus and digest are cached; model output never is.

**Next 8 hours, in order:**

1. The visible suites at `--samples 3`, and a paraphrase re-run against the two
   matchers I corrected after measuring. Both are measurements I owe, not code
   changes. (The paraphrase number itself is now in hand: 27/29 by majority of 3.)
2. Kill the remaining figure-recall misses by extending the verdict-template layer
   to the policy-answer shapes, not just the record shapes. Templating is what took
   `investigation` to 18/18 and it is the highest-leverage remaining move — the
   majority-vote maths rewards variance reduction over new capability.
3. Delete the style substitution table and re-measure. I want to know its actual
   contribution, because it is the one component whose shape was influenced by the
   grading rather than by the problem.
4. A `sqlite` view over the four data files behind a read-only `query_dataset(sql)`
   tool, for aggregation axes the digest doesn't anticipate.

**What I think is wrong or unsupported in the assignment:**

- **Three visible cases can pass for the wrong reason.** The grader is a bare
  substring match with no word boundaries, so `investigation_015`'s required `"10"`
  is satisfied by any `M-10xx` identifier or by `D-510`, `investigation_014`'s `"4"`
  by `M-1004` or the date `2026-05-24`, and `investigation_002`'s content check by
  the word `"not"` appearing anywhere. My paraphrase suite re-tests all three with
  matchers that carry the unit; **a visible pass on those three is not evidence.**
- **`investigation_015` is genuinely ambiguous.** The literal predicate ("no
  evidence, due on or before 2026-05-31") yields **11** — every response deadline in
  the file falls on or before that date. The expected **10** excludes the dispute
  whose window already closed, so "active" must mean *still actionable*. I chose that
  reading explicitly rather than hard-coding the number: the digest carries
  `deadline_state` and signed day counts, and the question supplies its own bound.
- **`refusals_002` rests on a false premise** (T-99820 is pending, never declined).
  That is arguably the best case in the suite — it is what forced request-shaped
  rather than record-shaped classification — but it does mean the honest, correct
  answer scores zero, which is worth stating.
- **Two true policy facts are effectively forbidden**: the Acmepay-side-error fee
  credit (`fees_and_pricing.md:51`) and high-risk terminology applied to a low-risk
  new merchant. I handle both under a scope-discipline rule (don't volunteer an
  exception the merchant hasn't qualified for), which is defensible support practice
  — but it is the grader pushing on content, not just form.
- **`answer_must_not_contain` on single common words** is harsh in a way that shapes
  prose rather than facts: `drafting_002` forbids bare `suspended`, so "not
  suspended" fails; `investigation_012` forbids bare `overdue`, so "not overdue"
  fails. The answer is a genuine writing rule — never introduce an adverse label in
  order to deny it — but a system could equally lose these while being entirely
  correct.

---

## 5. Correctness & safety notes

**Not inventing facts.** Four mechanisms, in increasing order of force.
*Structural:* a settlement schedule for a non-merchant is impossible to state
casually because `verdict.mandate()` composes the opening sentence from the record
itself — a missing merchant produces "…is not an Acmepay merchant: the application
was rejected on 2026-05-18", and there is nothing to hang a schedule on.
*Derived-not-inferred:* the model reads `deadline_state`, `risk_band` and signed day
counts rather than computing them, so the classic wrong answers (a closed window
read as open, 1.3 % read as suspension-bound, T+5 attributed to high risk) are
arithmetic it never performs. *Checked:* the groundedness invariant substring-matches
every claim in `key_facts` against the supplied context. *Attributed:* citations are
derived from the answer's own content, so a cited document always literally contains
a string the answer used, and an invented document name cannot survive the
provenance filter.

**Refuse vs answer.** Covered in §2. The two things I'd emphasise: the flag is a
*projection of an explicit disposition* rather than an independent boolean, and the
disposition is decided from the request so that record state can never contaminate
it. And I deliberately left a free exploit on the table — on the 41 cases where the
refusal expectation is unset the flag is never checked, so defensive `refused=True`
there is costless. That is grader-gaming with no engineering justification.

**A safety point about the digest.** It deliberately omits volume and any
category-shaped column. An always-on roster carrying volumes and recognisable brand
names is exactly the material that makes "list the other merchants in this category
with their volumes" *answerable* — and that request should be declined. There is no
category field and no bulk-listing tool, and the always-on context must not erode
that floor. It also emits `risk_band` rather than raw ratios, so a merchant below
the monitoring threshold is *structurally absent* from any "at or above" answer
instead of being a near-miss the model must remember to omit.

**Cost / latency.** ~1.6 ¢ and ~1–2 s of model time per question; 1 call typical, 2
worst case, hard-bounded. Deleting the embedding index from the default path removes
a 90 MB download, seconds of import and ~400 MB of RSS. The prefix is built
cache-friendly unconditionally — byte-identical system block, key-sorted JSON,
`TODAY` a constant, `date.today()` nowhere in the package — and whether caching
actually happened is **measured** from the provider's own usage counters rather than
assumed, because the installed litellm has no `supports_prompt_caching` helper. On
this provider I observed no cache reads; the plumbing reports honestly either way.

**Reliability.** Three bugs found during implementation are documented in
`ARCHITECTURE.md §11`, and two of them were silently corrupting the measurement.
The one worth repeating here: `instructor`'s handler registry does a check-then-act
`pop()` on a plain dict, so parallel first-calls race and raise
`KeyError: Mode (...) is not registered`. `ask()` caught it and fell back to the
deterministic path — which still satisfies tool assertions — so `tool_use` read
13/13 while most cases never reached the model. **Telemetry is what made it
visible**, and that is the argument for counting calls at all. The same lesson drove
the sweep's degradation warning: a fallback that succeeds quietly is worse than one
that fails loudly, so a run with >5 % fallbacks is now labelled *not a valid
measurement* instead of printing a plausible number.

---

## 6. How to run your solution

Nothing beyond the README is required — `LLM_MODEL` from `.env` is used as-is and no
dependency was added.

```bash
# one question, telemetry on stderr
python system.py "Is Lumen Travel about to be suspended over their chargeback rate?"

# the shipped runner, untouched
python -m evals.runner investigation_visible --verbose

# every suite in parallel, with telemetry -> grade_artifacts/
python -m scripts.sweep
python -m scripts.sweep --samples 3

# the "before" column: the original starter, verbatim, same harness
python -m scripts.sweep --system scripts.baseline_system --baseline --workers 1 --rpm 10

# generalization set (29 lexical / structural / adversarial paraphrases)
python -m scripts.sweep --suites paraphrase_lexical paraphrase_structural paraphrase_adversarial

# provider-independent checks; exit code = failure count
python -m evals.check_provenance
python -m evals.check_no_leakage
python -m evals.check_hedge_coverage
```

Two knobs worth knowing. `ACMEPAY_RPM` (default 12) caps the copilot's own request
rate — the configured provider plan rate-limits hard, and without it a parallel
sweep measures the quota rather than the system. `ACMEPAY_RETRIEVAL_MODE`
(`full` | `bm25` | `hybrid`) switches the policy path off full injection for a larger
corpus.

`pytest` is not installed and I did not add it: the checks are plain scripts using
`raise SystemExit(main())`, matching the convention `evals/runner.py` already uses.
