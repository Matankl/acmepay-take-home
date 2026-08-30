# Architecture — Acmepay Support Copilot

How the system is put together and what happens on a request. Rationale, measurements and
results are in `REPORT.md`; this file is the map.

## 1. Shape of the system

`ask()` gathers evidence deterministically, makes **one** LLM call, validates the result against
machine-checkable invariants, and repairs at most once. Tool selection, argument extraction,
date arithmetic, threshold comparison, cross-merchant aggregation and citation attribution are
all Python. The model does two things only: **decide what matters, and write the prose.** Hard
ceiling: two LLM calls per `ask()`, and no agentic loop, so nothing can fail to terminate.

```
question
   │
   ├─ entities.extract()      ID grammar + merchant-name resolution        [no LLM]
   ├─ gather.first_hop()      saturate every tool that accepts an entity   [no LLM]
   ├─ verdict.mandate()       templated opening sentence, when determined  [no LLM]
   ├─ prompt.system_block()   cached, byte-identical prefix                [no LLM]
   ├─ prompt.user_block()     retrieved policy + records + precedent       [no LLM]
   ├─ generate.one_shot()     ONE structured call → Draft                  [LLM #1]
   ├─ validate.check()        5 invariants over the Draft                  [no LLM]
   │    └─ if any failed:     gather.expand() + prompt.repair_block()      [LLM #2]
   │
   └─ _project()              Draft + ToolLedger + ctx → Response          [no LLM]
```

## 2. Module map

Grouped by the stage each serves, in pipeline order.

| Stage | Modules |
|---|---|
| **Boundary** | `system.py` — `ask()`, orchestration, `Draft → Response` projection, fallback |
| **Foundations** | `config.py` static config + frozen `TODAY` · `text.py` punctuation folding, quantity tightening, `pct`/`usd` |
| **Knowledge** | `corpus.py` breadcrumbed sections + generated collision map · `retrieval.py` BM25 + dense + RRF · `precedent.py` clustered ticket archive · `digest.py` portfolio rollup |
| **Routing** | `entities.py` ID and merchant-name resolution · `gather.py` tool routing + `Evidence` · `registry.py` `ToolLedger` · `enrich.py` per-record derived fields + `PROVENANCE` |
| **Generation** | `verdict.py` mandated openings · `prompt.py` prompt assembly · `schema_internal.py` the `Draft` model · `generate.py` the single call, rate limiting, backoff |
| **Output** | `validate.py` invariants + terminal net · `cite.py` citation attribution · `telemetry.py` per-request counters |

`tools/`, `evals/schema.py`, `evals/runner.py` and the `*_visible.py` suites are
**unmodified from the starter**. Added: `evals/paraphrase_*.py`, `evals/check_*.py`,
`scripts/sweep.py` (parallel dev driver), `scripts/baseline_system.py` (the original starter,
preserved for the "before" column).

## 3. The request lifecycle

### 3.1 Entity extraction — `entities.py`

Extract loosely, emit canonically. Prefixed IDs match with any separator or none and any dash
variant (`d-503`, `D 503`, `D–503`), as do bare numbers next to a type word (`dispute 503`);
digit widths are checked against the shapes the data files use. Merchant names resolve by
coverage of the *name* (`|name ∩ question| / |name|`, threshold 0.5), keeping every candidate
tied at the top, and a match must include at least one token absent from the policy corpus — so
generic business vocabulary cannot identify a merchant alone. Output is an `EntityRefs`: four ID
sets, the resolved names and an `ambiguous` flag.

### 3.2 Evidence gathering — `gather.py`

Three clauses, and they are the whole of tool routing:

1. **First-hop saturation.** For every entity named, call every tool that accepts it.
   No intent classification, so nothing for a paraphrase to misclassify. A merchant
   lookup also pulls its disputes, tickets and audit log.
2. **Bounded transitive expansion**, suppressed for single-record field lookups —
   gated on the question's shape (`_FIELD_QUERY` vs `_INVESTIGATIVE`), never on the
   record's contents.
3. **`search_policies` is never called.** Policy text reaches the answer through
   `retrieval.py`; the shipped tool returns whole documents, unchunked.

Records pass through `enrich.py`, which attaches signed day counts, `deadline_state`,
`risk_band` and formatted quantities. One naming rule: **never name the negative condition** —
states are positive (`deadline_state: "open"`), so the model is never taught to write "not
overdue". The result is an `Evidence`: keyed blocks plus free-text notes, rendered key-sorted.

### 3.3 Mandated verdicts — `verdict.py`

Where the correct opening sentence is fully determined by the records, compose it in Python and
let the model write only the explanation around it. Three templates, keyed on
**question shape × record type**, never on wording: a named record that does not exist
(with a distinct form for a rejected applicant, whose only trace is the audit log); the count of
one merchant's active disputes; and one dispute's response window, branching on
`deadline_state`. `None` means the model writes its own opening.

### 3.4 Prompt assembly — `prompt.py`

Layout is driven by prompt caching, which is a prefix match: one changed byte invalidates
everything after it. The **system block** (`lru_cache`, byte-identical every request) carries
the role and frozen date, the three-way disposition taxonomy, the style contract, evidence-usage
rules, the generated ambiguous-quantity map, the portfolio digest and the precedent index; under
`full` mode also the policy TOC and the entire corpus. The **user block** (per request) carries
retrieved policy excerpts, the gathered records, the closest tickets, the mandated opening if
there is one, a forecast note if the question asks for a future value, then the question.

### 3.5 Policy retrieval — `retrieval.py`

The corpus is 59 breadcrumbed sections (4,184 tokens of raw file text; 4,602 as rendered
sections, the difference being the labels). Three modes: **`hybrid`** (the default — BM25 +
dense, reciprocal-rank fused, top 12), **`bm25`** (keyword only, no embedder loaded at all), and
**`full`** (every section verbatim, 100% recall by construction). `effective_mode()` degrades
`full` to `bm25` if the corpus outgrows `POLICY_CONTEXT_BUDGET`.

Sections carry their heading path, which both disambiguates facts that share a number and gives
citation attribution its structure. RRF needs no score normalisation between two incomparable
scorers, and the dense matrix is row-normalised and disk-cached under a content hash so one
matmul serves a query. Whatever was injected accumulates in a `RetrievedContext` — one per
`ask()`, passed by reference, unioned across both passes — which `cite.py` reads back; `full`
mode seeds it with every section, so it stays a special case of the same logic rather than a
second code path.

### 3.6 Generation — `generate.py`, `schema_internal.py`

One `instructor` call returns a `Draft`: `disposition`, `verdict`, `detail`, `key_facts`,
`sources`, `refusal_reason`. Every field is consumed by a validator or by the projection.
**`Draft` deliberately has no `tool_calls` field**, which makes it structurally impossible for
the model to report a call it never made. `instructor.from_litellm` runs in tool-calling mode,
consuming the tool channel to extract the response model. Because gathering is deterministic
there are no tools to pass, so the topology choice and the structured-output choice are one
choice. The call is wrapped in a global token bucket (`ACMEPAY_RPM`) and jittered exponential
backoff on rate-limit errors, both shared across threads.

### 3.7 Validation and repair — `validate.py`

| Code | Fires when |
|---|---|
| `incapacity_prose` | an ANSWER disclaims the assistant's own capability, or asks deferentially for documents |
| `fabricated_action` | prose claims a state change was carried out |
| `over_refusal` | a decline on a draft/explain speech act |
| `ungrounded` | reported `key_facts` do not appear in the supplied context |
| `missing_verdict` | a mandated opening sentence was dropped |

Detectors implement the *semantic class* (first-person modal incapacity, deferential information
requests), not any external phrase list, so they generalise to phrasings a list never
enumerated. On any problem the system re-gathers first — the usual cause is a fact the answer
needed and the first hop didn't fetch — then re-prompts once. The repair prompt restates the
question, lists the problems, and carries policy text of its own, widening retrieval to
`RETRIEVAL_REPAIR_TOP_K` only when the failure was `ungrounded`. A deterministic substitution
table (`sanitize`) is the terminal net, applied to ANSWER prose only if the repair pass did not
clear it; a decline is
*supposed* to describe what cannot be done, so rewriting it there would delete the
content.

### 3.8 Projection — `system.py`, `cite.py`

`_project()` is the only place the graded `Response` is constructed. Three fields the model
never authors:

- **`tool_calls`** — from the `ToolLedger` of what actually executed. A tool that
  raises is still recorded, because the grader matches on name and arguments.
- **`refused`** — `disposition != "ANSWER"`, decided from the *request*, not from what
  the records happen to contain.
- **`cited_doc_ids`** — `cite.py` takes the salient atoms the answer contains (amounts,
  percentages, endpoints, header names, status codes, schedule shorthand) plus verbatim n-grams
  from `key_facts`, and attributes each back to every injected document that literally contains
  it. The model's own `sources` list only seeds the union and is filtered against what was in
  context. Always `sorted()`, so repeat runs don't measure hash ordering.

`answer` flattens `verdict` + `detail`, prepending the mandated sentence if the model dropped
it. `refusal_reason` is a fixed per-disposition prefix plus the model's specifics, and is `None`
whenever `refused=False`.

## 4. Failure path

`ask()` never raises: the eval runner scores an exception as a hard zero for that case. Any
exception out of `_orchestrate` falls through to `_fallback`, which answers from records already
on disk — the mandated verdict, the gathered blocks and notes, or, when no entity was named, the
deterministic portfolio rollup. The read tools signal absence by returning `{"error": "not
found"}` rather than raising, so a missing record is data, never an exception. Telemetry is
thread-local (the sweep runs cases in parallel) and read via `last_telemetry()` after `ask()`
returns — out of band, because `Response` is the graded contract and must not grow.

## 5. Determinism rules

These hold across the package and are why the prompt prefix caches:

- `TODAY` is a module constant; `date.today()` appears nowhere in `copilot/`.
- Every serialised structure is key-sorted and every glob is `sorted()`.
- Every date difference, threshold comparison and count is computed in Python.
- A derived field must trace to a policy document or a schema field, never to an eval
  assertion — `enrich.PROVENANCE` records the trace, `evals/check_provenance.py` runs it.

## 6. Configuration surface

| Variable | Default | Effect |
|---|---|---|
| `LLM_MODEL` | `gpt-4o-mini` | any litellm-supported model |
| `ACMEPAY_RETRIEVAL_MODE` | `hybrid` | `hybrid` / `bm25` / `full` |
| `ACMEPAY_RETRIEVAL_TOP_K` | `12` | sections injected per request |
| `ACMEPAY_RETRIEVAL_REPAIR_TOP_K` | `20` | sections on the repair pass |
| `ACMEPAY_POLICY_BUDGET` | `12000` | token ceiling above which `full` degrades to `bm25` |
| `ACMEPAY_RPM` | `12` | the copilot's own request-rate cap |
| `ACMEPAY_NUM_CTX` / `ACMEPAY_TIMEOUT_S` | `16384` / `900` | Ollama context window (it truncates silently otherwise) and request deadline |

All are read at **module import**, so they must be set before process start — patching
`os.environ` afterwards has no effect.
