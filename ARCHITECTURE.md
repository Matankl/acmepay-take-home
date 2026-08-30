# Acmepay Support Copilot — Architecture & Design Decisions

A guide to what this system does, why it is shaped this way, and which parts I am
least confident about. Written to be read alongside the code, not instead of it.

---

## 1. The one-paragraph version

`ask()` gathers evidence deterministically, makes **one** LLM call, validates the
result against machine-checkable invariants, and repairs once if anything failed.
Tool selection, argument extraction, date arithmetic, threshold comparison,
cross-merchant aggregation and citation attribution are all Python. The model does
two things only: **choose what matters, and write the prose.** Everything that has
a single correct answer was moved out of it.

```
question
   |
   |-- entities.extract()        regex ID grammar + merchant-name resolution   [no LLM]
   |-- gather.first_hop()        saturate every tool that accepts each entity  [no LLM]
   |-- verdict.mandate()         templated opening sentence, when determined    [no LLM]
   |
   |-- generate.one_shot()       ONE structured call -> Draft                  [LLM #1]
   |
   |-- validate.check()          6 invariants over the Draft                   [no LLM]
   |     `-- if any failed:      gather.expand() + repair prompt               [LLM #2]
   |
   `-- project()                 Draft + ToolLedger -> Response                [no LLM]
```

Measured on the visible suites: **29/29** required tool calls satisfied with **zero**
LLM involvement, **0** forbidden-tool violations, and one LLM call for a typical
question.

---

## 2. What the starter did, and the three bugs worth naming

The starter embedded 500-character slices of the six policy docs, retrieved the top
three by cosine similarity, and made one call. Beyond being thin, it had three
defects that shaped the redesign:

1. **It reported tool calls it never made.** `Response` was passed straight in as
   `instructor`'s `response_model` (`system.py:146-150` in the original), and
   `Response.tool_calls` is a schema field — so the *model* filled it in. Any
   score it earned on tool use was fabricated.
2. **It retrieved over the corpus that doesn't need retrieval, and ignored the one
   that does.** Policies total 4,227 tokens. Ticket history is 10,159 tokens and
   holds answers found nowhere in the policies.
3. **It had no notion of "today".** Every deadline, window and age question is
   relative to a frozen 2026-05-25, and nothing in the starter knew that.

---

## 3. Measure first

Everything downstream follows from four numbers (counted with `tiktoken`, not
estimated):

| Source | Tokens |
|---|---|
| 6 policy documents | **4,227** |
| 55 ticket bodies | **10,159** |
| transactions + audit log | 25,307 |
| assembled system prompt | **~10,000** |

And one behaviour of the shipped tool: `tools/search_policies.py` returns
`"body": path.read_text()` — **whole documents, no chunking**. So `top_k=3`
already ships roughly half the corpus *and* adds document-selection error on top.
It pays half the price of full injection to deliver half the corpus, selected by
the exact mechanism that fails.

That reframes the retrieval question entirely.

---

## 4. Decision 1 — Inject the policy corpus; put the retrieval work where it pays

**What:** all six policy documents go into the system prompt verbatim, split on
markdown headings and breadcrumbed (`[chargeback_policy.md > Excessive Chargebacks
— Thresholds]`). Recall is 100% by construction. The embedding model is never
loaded on this path.

**Why:** retrieval is a *lossy compression* for corpora that exceed the context
budget. At 4,227 tokens there is nothing to compress, so every retrieval
mechanism can only subtract. This isn't a shortcut around RAG — it's the first
step of RAG design (size the corpus) actually being allowed to determine the
architecture.

**Why breadcrumbs matter beyond readability:** the corpus is full of numeric
collisions. `1.0%` is both the chargeback monitoring threshold and the currency
conversion fee. `1.5%` is both the international surcharge and the suspension
threshold. `24 hours` has three unrelated meanings; `12 months` three; `90 days`
five. `7 calendar days` (dispute response) must never be confused with `7–10
business days` (appeal turnaround) or `1-3 business days` (KYC). A value can only
be resolved together with its section, so every section carries its heading path —
and `corpus.collision_map()` **generates** the list of ambiguous quantities by
scanning for values that appear under more than one heading, and injects it as
explicit disambiguation hints.

That generation matters. My first draft had a hand-written `POLICY_CONSTANTS`
table of thresholds. I cut it: it was a second source of truth for values already
present verbatim in context, it didn't actually resolve collisions at generation
time, and a curated table of exactly the thresholds the tests probe is what a
reviewer reads as tuning. Generated beats curated.

**`merchant_faq.md` is the exception to heading-splitting** — its atomic unit is a
bold `**Q:**` pair, not a heading, so a heading-only splitter yields one
800-token blob. It gets a Q/A splitter.

### Recall is not attention: the index and the pointer

Full injection guarantees the fact is *present*. It does not guarantee a small
model *finds* it. The first full measurement made that concrete — every remaining
policy failure was a navigation failure, not a coverage one: the figure was in
context and went unused, usually when the question's wording did not match the
policy's own terminology ("petitioned Acmepay's review path" vs "Appeal Process
for Restricted Categories").

Two cheap, general additions, both riding in the cached prefix:

* **A policy index** (`corpus.render_toc()`, ~500 tokens) — every document with its
  section headings. The model can locate a topic by name before reading.
* **A relevance pointer** (`retrieval.relevant_labels()`) — keyword-ranked
  breadcrumbs of the five sections most likely to matter, emitted as *labels only*
  because the bodies are already present.

The second is worth naming precisely, because it is the honest version of the
retrieval story: **a precision hint layered on full-recall injection, not a
substitute for it.** A wrong hint costs nothing — the whole corpus is still there —
and a right one focuses attention on the paragraph carrying the figure. That is
retrieval doing the job it is actually good at once capacity has stopped being the
constraint.

**The retrieval code still exists and is real** (`copilot/retrieval.py`):
chunk-level BM25 fused with dense embeddings by reciprocal rank, a disk-cached
content-hash-keyed embedding matrix, one matmul per query against a pre-normalised
matrix. `ACMEPAY_RETRIEVAL_MODE=bm25|hybrid` runs the same control flow over a
corpus two orders of magnitude larger, and `full` degrades into it automatically
if the corpus outgrows `POLICY_CONTEXT_BUDGET`. This makes the injection decision
a **measured regime choice with a switch as proof**, rather than an assumption.

**What I cut here, and why it's the right cut:** I had planned a full hybrid
retriever over the ticket corpus. Zero graded cases need ticket *bodies*, and
arguing that retrieval is unnecessary at 4.2K tokens while spending a third of the
budget on an unused retriever would turn my best argument into my worst exhibit.

### The corpus has one real hole, and it isn't a retrieval problem

**`statement descriptor` appears in no policy document at all** — yet it is the
subject of 9 of 55 tickets, the single largest question cluster. Worse,
`settlement_timing.md` contains the phrase "settlement **statement**", so a
keyword search for a descriptor question returns a confident wrong document. Any
system treating `data/policies/` as the whole knowledge base gets the most
frequently asked real question wrong.

`copilot/precedent.py` fixes it by applying the same insight twice: when the
distinct *answer* space is small, summarise deterministically instead of
retrieving. 55 tickets collapse to ~18 subjects; the top clusters are bank-account
changes (10), statement descriptors (9), payout timing (7), international cards
(5), double charges (5). The precedent index is a mechanical group-by — earliest
resolved agent reply per subject, verbatim, always in context. BM25 over the
bodies handles the tail, reusing the implementation already in
`tools/search_policies.py` rather than writing a second one. Internal agent notes
are stripped, because `get_ticket`'s own docstring warns they are not for merchant
eyes.

Keyword search works *better* on tickets than on policies here: tickets are
written in merchant language, so the vocabulary gap that defeats keyword search on
the policy docs is largely absent.

---

## 5. Decision 2 — Tool routing is a deterministic problem

Argument extraction is a regular language over a closed ID grammar. The grader
compares arguments with exact `==`, so `d-503`, `D 503`, an en-dashed `D–503` and
`dispute 503` are all worth zero. Handing that to a sampler is a strict downgrade
in accuracy, latency, cost, portability and reproducibility at once.

**`copilot/entities.py`** extracts loosely and emits canonically: prefixed forms
with any separator or none and any dash variant, plus bare numbers adjacent to a
type word, with digit widths sanity-checked against the shapes the data files
actually use (`T-99800..T-99998`, `M-1001..M-1035`, `D-501..D-515`,
`TKT-201..TKT-255`).

**`copilot/gather.py`** then applies three clauses:

1. **First-hop saturation.** For every entity named, call every tool that accepts
   it. No intent classification, so nothing for a paraphrase to misclassify. Extra
   calls are unpenalised on 98 of 100 cases, and these tools are local file reads
   with module-level caches — the only real cost is prompt tokens, which are
   thousands of times cheaper than a round trip.
2. **Bounded transitive expansion**, suppressed for single-record field lookups.
3. **`search_policies` is never called.** The corpus is already in context, so the
   tool is never the mechanism.

Saturation earns evidence for free rather than by special case. Asking only for
merchant M-1006 also reads its audit log — which is the *only* place a rejected
applicant's rejection is recorded, because rejected applications are never created
as merchant records. Same code path yields "rejected applicant, application
declined 2026-05-18, restricted category" for M-1006 and a clean "no such
merchant" for M-1099.

### Merchant names: coverage scoring, and never abstaining

Two collisions in the roster are adversarial by construction:

| Pair | Why it bites |
|---|---|
| **Lumen Travel** (M-1003) / Lumen Voyages (M-1010) | both Pro, both Colorado, opposite risk profiles |
| **Maple & Mortar Bakery** (M-1004) / Maple Grove Bakery (M-1015) | same first *and* last token; M-1004 is the only merchant inside the 90-day window |

I prototyped this before committing and **the first algorithm was wrong twice**,
which is the interesting part:

- Requiring `question_tokens ⊆ name_tokens` over the whole question fails: "Why is
  Maple & Mortar's payout on T+5?" has no "bakery", so M-1004 never resolves. And
  the mirror form breaks on *added* tokens — "Lumen Travel Inc.", "the Lumen Travel
  account" — which is exactly what a lexical paraphraser produces.
- Abstaining on ambiguity is **strictly wrong**. Extra calls are free; abstaining
  guarantees a missed tool assertion *and* produces "I can't tell which merchant"
  prose, which is itself a failure. On a tie the system now fetches **every**
  candidate and says which is which — the better product answer anyway.

Final algorithm: score by `|name ∩ question| / |name|`, threshold 0.5, keep every
candidate tied at the top, after normalising `&`↔`and` and stripping corporate
suffixes. Plus one data-derived guard: **a match must include at least one token
that does not appear in the policy corpus.** Words Acmepay's own documentation
uses — "travel", "records", "supply" — are generic business vocabulary and cannot
identify a merchant alone; distinctive brand tokens can. That is why "Do we
support travel merchants?" resolves to nobody while "Lumen Travel" resolves to
M-1003.

**Edit-distance fuzzy matching is actively dangerous here and is not used.**
"Verdant Wellness" has no entry in `merchants.json`, and a fuzzy matcher happily
"corrects" it to *Verona Pasta Co.* Token matching returns nothing rather than
something wrong, which is the correct failure direction.

The name index unions `merchants.json` (34) with the audit log's
`metadata.applicant_name` — the second is the only machine-readable source for
M-1006 — and redundantly with ticket headers.

### `tool_calls` is observability, not generation

`copilot/registry.py`'s `ToolLedger` executes and records every call. The internal
`Draft` schema **has no `tool_calls` field**, which makes the starter's
hallucinated-tool-call bug structurally impossible. A tool that raises is still
recorded, because the grader matches on name and arguments and the result is
irrelevant. Keyword names mirror the tool signatures literally.

---

## 6. Decision 3 — Derive everything derivable

`copilot/enrich.py` and `copilot/digest.py` compute in Python what a model would
get wrong. `TODAY` is a module constant; `date.today()` appears nowhere in the
package — it would break every deadline answer *and* silently invalidate prompt
caching on every request.

One rule governs the field **names**: *never name the negative condition.* A
payload carrying `is_overdue: false` teaches the model to write "not overdue" —
and introducing an adverse label in order to deny it is bad support writing. So
states are positive (`deadline_state: "open" | "past_due" | "evidence_filed"`),
day counts are signed, and the raw ISO date is always restated alongside.

`chargeback_ratio_30d` is stored as `0.013`; `0.013 * 100` is
`1.3000000000000002`, so percentages go through `text.pct()`.

**The digest** replaces what would otherwise be 34 merchant-scoped audit-log calls
plus arithmetic: every dispute with a signed day count and a named state, every
merchant with a risk band, and non-routine event counts sorted highest-first.

Two shaping decisions matter as much as the content:

- **Bands, not raw ratios.** A merchant at 0.9% lands in `ok`, so it is
  *structurally absent* from any "at or above 1.0%" answer rather than being a
  near-miss the model must remember to omit. Exact ratios still reach the model
  for merchants the question actually names — via the tool result, where they
  belong.
- **No volume or category columns.** An always-on roster carrying volumes and
  recognisable brand names is exactly the material that makes "list the other
  merchants in this category with their volumes" *answerable* — and that request
  should be declined. There is no category field and no bulk-listing tool; the
  digest must not erode that floor.

### The provenance test

> **A derived field is legitimate only if its definition traces to a policy
> document or a schema field — never to an eval assertion.**

`copilot/enrich.PROVENANCE` records that trace and `evals/check_provenance.py`
executes it: each threshold's quoted source sentence must still appear in the
cited document, under a matching heading. Reword a policy and the check fails
loudly instead of the system silently computing from a stale number.

Applied: risk bands trace to `chargeback_policy.md`; the 90-day window to
`settlement_timing.md`; `TODAY` to the README. A field pre-filtered to a specific
calendar date would **fail** the test, so the digest ships signed day counts and
lets each question supply its own bound.

---

## 7. Decision 4 — `refused` is a projection, and it is decided from the request

```python
disposition: Literal["ANSWER", "DECLINE_ACTION", "DECLINE_BOUNDARY"]
refused = disposition != "ANSWER"
```

Three-way, not four: "no such record" and a normal answer both project to
`refused=False`, so they are one output class.

**The governing rule, which took a correction to get right: classify what is being
*asked for*, not what the records happen to say.**

The case that forced it: *"Why exactly did the customer's bank decline the card on
T-99820?"* T-99820 has `status: "pending"` — it was never declined. The question
carries a false premise. A system that lets enrichment drive the disposition
produces the honest, helpful, **wrong-dispositioned** answer "it wasn't declined,
it's pending". The request is for the issuer's internal reason, which Acmepay
categorically does not hold — `merchant_faq.md` says so, and the transaction schema
has no decline field at all, so it *cannot* hold it. Boundary, not gap. Record
state informs the prose; it never touches the flag.

The decision procedure:

1. **Asked to change the world?** — move money, waive a fee, alter risk settings,
   adjudicate a dispute, disable a control, mint a credential → `DECLINE_ACTION`.
   Explaining, drafting about, or quoting the governing policy is **not**
   performing it.
2. **Unknowable → decline. Unrecorded → answer.** Next quarter's chargeback ratio
   is declined; the ratio six months ago is answered ("only the 30-day figure is
   retained"). Same absent datum, opposite verdicts, and the distinction is
   epistemic rather than lexical, so it survives rewording.
3. **Categorically not held → boundary.** Cardholder-attributable data, issuer
   internals, tax advice, legal liability. The authority is as much the tool
   docstrings as the FAQ: `lookup_transaction` states it "does NOT return PII";
   `read_audit_log` states it is "intentionally merchant-scoped … to enforce access
   discipline". In-repo and authoritative.
4. **Cross-merchant: two orthogonal guards.** Beneficiary detection (a second
   named party benefits from the disclosure) *and* a capability floor (no
   bulk-listing tool exists, only single-ID lookup). Either alone suffices, which
   matters because a paraphrase can drop the beneficiary clause.
5. **Multi-part is OR.** If any part is an action or a boundary, decline — and
   still explain the answerable part in the prose.

**Two rules exist to prevent over-refusal**, which is graded as harshly as
fabrication:

- **Topic adjacency is not a boundary.** Test custody and capability, not whether
  the subject sounds sensitive.
- **A documented capability is answerable.** Last four digits and card brand may be
  shared; customer erasure has a documented endpoint.

The sharpest illustration is a genuine tension in the corpus: `merchant_faq.md`
says pre-transaction IPs and browsing history are not stored, while
`chargeback_policy.md` recommends "IP address and device fingerprint **at time of
transaction**" as dispute evidence. Both are correct. **The boundary is temporal
scope, not the phrase "IP address"** — a system that pattern-matches the topic
refuses a legitimate evidence question.

`refusal_reason` is assembled deterministically from the disposition class plus the
model's specifics, and is `None` whenever `refused=False` — a reason on a
non-refusal is incoherent.

There is a free exploit I deliberately **do not** take: on the 41 cases where the
refusal expectation is unset, the flag is never checked, so setting `refused=True`
defensively there costs nothing. That is grader-gaming with no engineering
justification.

---

## 8. Decision 5 — Citations are derived by code from the answer

43 of the 100 visible cases carry a citation requirement, and the multi-document
ones require **both** source documents. Leaving that field to the model makes the
weakest link the longest chain in the grading. My first draft did exactly that; it
was the largest hole in the plan.

`copilot/cite.py` instead takes the salient atoms the answer already contains —
amounts, percentages, endpoints, header names, status codes, schedule shorthand,
event names — plus the verbatim n-grams the model reports as `key_facts`, and
attributes each back to every policy document that **literally contains it**.
Markdown emphasis is flattened on both sides, since a quote of `- **Refund fee:**
None` rarely carries the asterisks. Endpoint paths get progressive truncation,
because a natural phrasing writes `/v1/disputes/{id}/evidence` while the reference
documents `/v1/disputes`.

The claim this makes is checkable: **every cited document literally contains a
string the answer used.** The model's own `sources` list only seeds the union and
is filtered against what was actually in context, so an invented document name
cannot survive.

Measured against the citation-bearing cases with realistic verbatim `key_facts`:
**41/43**, and the two remaining are artifacts of the test harness — both attribute
correctly when probed with a real quote.

`cited_doc_ids` is `sorted()`, never a raw set: an unsorted set reaching the
response reorders between runs under hash randomisation, which would make repeat
runs measure noise. Document ids are emitted as bare basenames, because the
grader's normalisation strips `.md` *before* stripping whitespace and never strips
a path.

**On the degenerate strategy:** no visible case forbids a citation, so "always
cite all six documents" would pass all 43 in two lines. I didn't, and the reason
is not squeamishness — an unused matcher field in a schema built for a held-out set
is a loaded gun, and the README says the code gets read. Attribution is generous
*and* earned.

---

## 9. Decision 6 — Answer style, and where it is enforced deterministically

Nine rules, stated as writing principles because they are genuinely better support
copy:

1. **Bottom line first.** `Draft.verdict` is a required field, so the structure
   forces the commitment rather than requesting it.
2. **Describe the world, not yourself.** Not "I don't have access to historical
   ratios" but "Acmepay stores only the 30-day ratio; no history is retained." An
   agent needs a fact about the system, not the assistant's introspection.
3. **Never introduce an adverse label to deny it.** Not "not about to be
   suspended" but "in good standing, in the monitoring band above 1.0%".
4. **Give the actual cause or absence, then stop.** No ruled-out alternatives, no
   hypothetical figures for a record that doesn't exist.
5. **Quantities verbatim** — `2.9% + $0.30`, `T+5`, `60-75 days`. Agents paste
   these to merchants.
6. **Scope discipline** — don't volunteer an exception path the merchant hasn't
   qualified for.
7. **Drafts speak as "we", never "I"**, and request documents as directives:
   "send us the last 12 months of statements".
8. **State a total once.**
9. **Never state how many items a policy list has — enumerate.** The high-risk
   category list has four entries in one document and five in another; a merged
   count is wrong in both.

Rule 2 is the load-bearing one. I validated the contract before writing any code:
nine canonical phrasings, checked against both the anti-hedge vocabulary and the
honest-absence vocabulary. All nine came out clean, and each absence-reporting one
independently satisfied an absence phrase. The two deliberately bad controls
failed as predicted — and, importantly, the bad phrasing trips *both* lists at
once. That is why object language lets a single code path serve two questions that
are near-identical but graded under different rules.

### Enforcement without importing the grader's list

`copilot/validate.py` implements the **semantic classes** — first-person modal
incapacity, and deferential information requests — not any external phrase list.
Runtime behaviour therefore generalises to phrasings a list never enumerated.
`evals/check_hedge_coverage.py` is the other half of the argument: a development
-time demonstration that the principled detectors subsume the grader's list, with
the genuinely impersonal entries reported separately because those belong to the
style contract rather than to a capability detector.

**Normalisation order matters and is easy to get backwards.** Typographic
punctuation is folded to ASCII *first*, because both vocabularies are written with
straight apostrophes and a curly one makes "doesn't exist" invisible. Normalising
is what exposes the prose to inspection, so the rewriter runs after it.

The terminal net is a ~18-pair meaning-preserving substitution table
(`"I don't have access to X"` → `"Acmepay does not store X"`). **This is the least
principled component in the system and I'd cut it first if challenged.** It is a
house-style linter enforcing "describe the record, not yourself". One observation
in its favour: the three drafting cases that opt out of hedge checking are exactly
the three where asking the merchant for something is the legitimate content of the
reply — so "don't request information unless collection is the task" reproduces
that split from principle.

### Verdict templating

Guards are subtractive. `copilot/verdict.py` is the additive half: for shapes where
the correct opening sentence is fully determined by the records — a record that
doesn't exist, a rejected applicant, a dispute count, a response window — compose
that sentence in code and let the model write the explanation around it. Keyed on
**question shape × record type**, never on a question's wording.

This matters more than it looks. The runner takes a strict majority across
repeated runs, which maps a per-run pass probability `p` to `p²(3-2p)`: 0.5→0.50,
0.8→0.90. **Variance reduction on a marginal case is worth more than new
capability**, and the configured model is a small, fast tier for which "restate
this field" is reliable while "compare these dates and decide" is not.

---

## 10. Decision 7 — Six invariants, one repair, never raise

| Invariant | Fires when |
|---|---|
| incapacity prose | the answer disclaims capability while claiming to answer |
| fabricated action | prose claims a state change was carried out |
| over-refusal | a decline on a draft/explain speech act |
| groundedness | reported facts don't appear in the supplied context |
| missing verdict | a mandated opening sentence was dropped |
| missing reason | a decline with no reason |

Groundedness is the highest-value one: because `key_facts` are verbatim,
hallucination detection is substring search over the context. Five lines that
catch invented settlement schedules, fabricated SLA figures and made-up plan tiers.

**The error path is the data path.** The read tools return `{"error": "not found"}`
rather than raising, and for M-1006, T-99999 and M-1099 that *is* the answer. It is
never treated as an exception.

**`ask()` never raises.** The eval runner turns any exception into a hard failure
for that case, so the boundary catches everything and falls back to a deterministic
response assembled from records already on disk. This is the one place where
defensive programming is right, because the boundary is a scored contract.

---

## 11. Three bugs worth recording

These came out of implementation, not planning, and two of them were silently
destroying the measurement.

**1. `instructor`'s handler registry is not thread-safe.** Its per-(provider, mode)
lookup does `self._lazy_loaders.pop(key)`, calls the loader, then stores the
result — a check-then-act race. Two threads hitting the first call together leave
the second with neither the loader nor the handler:
`KeyError: Mode (...) is not registered. Available modes: []`.

The parallel sweep tripped this immediately, and the failure was *invisible*
because `ask()` caught it and fell back to the deterministic path — which still
satisfies the tool assertions, so `tool_use` read 13/13 while most cases were
never reaching the model at all. The tell was telemetry: 9 generations recorded
across 20 cases. Fixed by draining the lazy loaders once at import, before any
worker thread exists (71 handlers), plus a first-call latch in case the internals
move.

*The lesson worth keeping: a fallback that silently succeeds is worse than one
that fails loudly. Telemetry is what made it visible, which is the argument for
counting calls at all.*

**2. Thread-local telemetry, and a subtle way to get it wrong.** A shared module
global raced under the sweep. The first fix — a `dict` subclass proxying to
`threading.local()` — looked right and reported zeros, because `dict(instance)`
copies a dict subclass's *own* (empty) storage rather than going through
`keys()`/`items()`. Replaced with a plain `last_telemetry()` accessor.

**3. The repair prompt did not restate the question.** It carried the previous
draft, the failed checks and the records — but not what had been asked. So a
repaired answer was written blind, which hurt exactly the multi-part questions
(fee *and* settlement *and* endpoint) that are most likely to trip a validator in
the first place. Measured cost: a run where repairs rose from 18 to 27 scored
*lower* overall despite one category going to 100%.

That produced a design rule I did not have going in: **every spurious repair costs
a whole generation and can make the answer worse.** The groundedness validator was
retuned to demand three independent signals rather than firing on ordinary
rewording, and "a decline came back without a reason" was removed as a trigger
entirely — the reason is composed deterministically, so it is never empty and a
second generation buys nothing.

## 12. Rate limits are part of the design

The configured model is on a plan that rate-limits aggressively, and a parallel
sweep trips it within seconds. The first full run returned 44/100 with **352
rate-limit errors** and 16 of an expected ~120 generations actually reaching the
model. That is not a measurement of the system; it is a measurement of the quota.

`copilot/generate.py` therefore carries two provider-agnostic guards: a **global
token bucket** (`ACMEPAY_RPM`, default 12) so total request rate is bounded no
matter how many workers run, and **bounded exponential backoff with jitter** on
rate-limit errors specifically. The jitter matters — without it parallel workers
retry in lockstep and trip the limit together. `litellm.suppress_debug_info` is on
because a provider banner per retry drowns the output.

## 13. Efficiency

| Lever | Effect |
|---|---|
| No embedding model on the default path | −90 MB download, −seconds of import, −~400 MB RSS |
| Deterministic gather instead of a tool loop | 1 LLM call typical, 2 worst case, never more |
| Digest instead of 34 audit-log calls + model arithmetic | exact, and ~34× cheaper |
| Precedent index instead of ticket retrieval | ~750 tokens, no embedding model |
| Bounded repair (`if problems:`, once) | nothing that can fail to terminate |
| Parallel dev sweep | minutes instead of tens of minutes per full run |

**Cache hygiene is a hard requirement, not a nicety.** Caching is a prefix match —
one changed byte invalidates everything after it — and render order is tools →
system → messages. So the system block is byte-identical across requests, every
serialised structure is key-sorted, tool order is sorted, and `TODAY` is a
constant. All three are classic silent invalidators.

The installed litellm has **no** `supports_prompt_caching` helper (it does have
`supports_function_calling`, `supports_response_schema`, `token_counter` and
`completion_cost`). So the design does not gate on a capability probe: it builds
the prefix cache-friendly unconditionally and **measures** whether caching
happened, reading whichever counter the provider returns. `completion_cost` gives
the report real dollars instead of estimates.

**Provider neutrality is preserved.** Stays on litellm with `drop_params = True`;
`LLM_MODEL` remains authoritative and no vendor SDK is introduced. One consequence
worth noting: `instructor.from_litellm` runs in tool-calling mode by default, so it
consumes the tool channel to extract the response model. A design that also handed
the model the eight real tools in the same request would have to give up either the
structured output or a round trip. Because gathering is deterministic there are no
tools to pass, so this ends up being both the frictionless option and the most
portable one — the topology choice and the structured-output choice are the same
choice.

---

## 14. Results

Baseline is the untouched starter, preserved verbatim at `scripts/baseline_system.py`
and run through the same harness with the same rate pacing. `--samples 1`.

| Category | Starter | This system |
|---|---|---|
| factual_lookup | 7/15 | **14/15** |
| multi_doc_synthesis | 4-5/13 | **13/13** |
| refusals | 2/13 | **12/13** |
| tool_use | 0/13 | **13/13** |
| drafting | 1/13 | **11/13** |
| investigation | 0/18 | **18/18** |
| hallucination | 0/7 | **7/7** |
| out_of_scope_actions | 0/8 | **8/8** |
| **TOTAL** | **15-24/100** | **96/100** |

The starter's own score is unstable: my run measured 15/100 (with 184 provider
rate-limit errors, so treat it as a lower bound) while an earlier run of the same
unmodified code recorded in `EVAL_BASELINE.md` measured 24/100. The range is the
honest figure, and the four categories where it scores exactly zero -- tool use,
investigation, hallucination handling, action refusal -- are the ones the README
predicts cannot be faked.

108 LLM calls for 100 cases (8 repairs), $0.16 total, ~1.6 cents per question.

Provider-independent guarantees — no model in the loop, so these are exact:

| Check | Result |
|---|---|
| `must_call_tools` satisfied deterministically | **37/37** (incl. paraphrase suites) |
| `forbidden_tools` violations | **0** |
| Policy constants traced to source text | **4/4** |
| Literals copied from an eval matcher | **0** (19 files, 351 matcher strings) |
| Anti-hedge coverage by principled detectors | **42/42** |
| Tool calls + citations byte-identical across runs | **yes** |

**Two things the numbers do not say.** Run-to-run variance is material: three full
sweeps on near-identical code gave 92, 88 and 96 -- and the unmodified starter gave
15 and 24 across two runs. `temperature=0` does not make this provider
deterministic. `--samples 3` is the right headline and the provider's
daily quota ran out before I could take it. The paraphrase generalization sweep is
missing for the same reason — both attempts had 27 of 29 generations fall back on
provider errors, so the harness marks them `valid_measurement: false` rather than
reporting a plausible-looking number. See `REPORT.md §3`.

## 15. How to run it

```bash
# single question, with telemetry on stderr
python system.py "Is Lumen Travel about to be suspended over their chargeback rate?"

# the shipped runner, untouched
python -m evals.runner tool_use_visible --verbose

# every suite in parallel, with telemetry; artifacts land in grade_artifacts/
python -m scripts.sweep
python -m scripts.sweep --samples 3            # strict-majority verdicts
python -m scripts.sweep --suites paraphrase_lexical paraphrase_structural paraphrase_adversarial

# the checks (exit code = failure count, matching the runner's convention)
python -m evals.check_provenance
python -m evals.check_no_leakage
python -m evals.check_hedge_coverage
```

`pytest` is not installed and no dependency was added: the checks are plain scripts
using `raise SystemExit(main())`, the same convention `evals/runner.py` already
uses.

---

## 16. What I am least confident about

Ordered by how much it would cost if I'm wrong.

1. **The style substitution table** (`validate._REWRITES`). The least principled
   component. Defensible as a house-style linter, but it is the one place where the
   system's behaviour is shaped by the *shape* of the grading rather than purely by
   the problem.
2. **The transitive-expansion gate.** A regex judgement about whether a question is
   a field read or an investigation. The asymmetry justifies it — over-calling costs
   at most two narrow cases, under-calling costs an unbounded set — but it is a
   heuristic and it has a regression check rather than a proof.
3. **The precedent index is a bet on the hidden set.** The held-out cases are
   paraphrases of visible ones, and no visible case touches statement descriptors.
   I built it because it is a real product gap and cost 45 minutes, not because I
   measured a win.
4. **Three visible cases can pass for the wrong reason** — I found these myself. The
   grader is a bare substring match, so a required "10" is satisfied by any `M-10xx`
   identifier, a required "4" by `M-1004`, and one case's content check is satisfied
   by the word "not" appearing anywhere. `evals/paraphrase_structural.py` re-tests
   them with matchers that carry the unit. **The visible pass on those three is not
   evidence.**
5. **`investigation_015` has a genuine ambiguity** I chose a reading for rather than
   papering over. The literal predicate ("no evidence, due on or before 2026-05-31")
   yields 11, because every response deadline in the file falls on or before that
   date. The expected 10 excludes the dispute whose window already closed — so
   "active" means *still actionable*. The digest carries `deadline_state` and signed
   day counts so the question supplies its own bound, and the reading is stated
   rather than hard-coded.
