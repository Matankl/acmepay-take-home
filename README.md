# Acmepay Support Copilot — Take-Home Assignment

Welcome, and thanks for taking this on. This exercise asks you to turn a
deliberately naive starter into a useful internal **support copilot** for
Acmepay, a (fictional) payments company. You'll be the AI engineer building the
tool that Acmepay's human support agents lean on while handling merchant
tickets.

**Time budget:** ~8 hours of focused work. **Deadline:** one week from receipt.

You will walk us through your solution in a follow-up session, so optimize for
work you can explain and defend, not for a perfect score.

---

## The scenario

Acmepay support agents answer merchant questions all day: fees, settlement
timing, chargebacks, disputes, onboarding. They have policy docs, a ticket
history, and structured data (merchants, transactions, disputes, an audit log).
Today they grep and click around by hand. Your job: build the assistant that
does the reading, looking-up, and reasoning for them — accurately, and without
making things up.

The **user of your system is an Acmepay support agent**, not a merchant. The
assistant answers the agent's questions; the agent then talks to the merchant.

---

## What you're given

```
system.py            # the starter system — a near-stub naive RAG. THIS is what you improve.
tools/               # 8 ready-made tools over the structured data (see below)
data/
  policies/          # 6 markdown policy docs (the RAG corpus)
  merchants.json     # 34 merchants
  transactions.json  # 199 transactions
  disputes.json      # 15 active disputes
  audit_log.jsonl    # 245 audit events
  tickets/           # 55 historical support tickets (closed conversations)
evals/
  schema.py          # EvalCase + the deterministic grader (DO NOT change the grader's contract)
  runner.py          # the eval runner
  *_visible.py       # the eval suites you can see and iterate against
requirements.txt
```

> **The world's clock is frozen: treat "today" as 2026-05-25** — the latest
> timestamp in the data. Don't use the wall clock; the grader's date math
> (overdue disputes, new-merchant windows, "recent" activity) assumes this date.

There is a held-out eval set you **cannot** see. It mirrors the visible suites
with paraphrased questions. Treat the visible suites as your dev set. We grade
primarily on the held-out set — a solution that generalizes beyond the visible
strings is what scores well; one that tunes to them will not.

---

## The contract you must NOT change

Your system exposes one entry point:

```python
def ask(question: str) -> Response: ...
```

returning this exact Pydantic schema (`system.py`):

```python
class ToolCall(BaseModel):
    name: str          # tool function name, e.g. "lookup_merchant"
    args: dict         # arguments passed, e.g. {"merchant_id": "M-1003"}

class Response(BaseModel):
    answer: str                       # natural-language answer for the agent
    cited_doc_ids: list[str] = []     # sources used: doc names ("fees_and_pricing.md"),
                                      # and/or IDs ("TKT-203", "T-99812", "M-1003")
    tool_calls: list[ToolCall] = []   # tools you actually called while answering
    refused: bool = False             # True if you declined to answer
    refusal_reason: str | None = None
```

The grader reads these fields directly. **Keep `ask()` and `Response` exactly
as defined.** Everything behind them is yours to rewrite — retrieval, chunking,
prompting, tool routing, model choice, control flow, all of it.

> Why so strict? The schema is how we grade deterministically (no LLM-as-judge).
> A refusal must set `refused=True`; a tool you used must appear in `tool_calls`;
> a fact you used must be cited. Saying the right words in `answer` is not enough.

**When to set `refused`.** `refused=True` means you are *declining to comply*: the
request is out of scope, privacy/PII-violating, or asks you to *perform an action*
you have no authority or tool to do (issue a refund, waive a fee, suspend a
merchant, disable a control). It does **not** mean "I looked and the answer isn't
there." If a record doesn't exist or the policies are silent, that is a normal
**answer** — state it honestly in `answer` with `refused=False`, and never fabricate
a value. Rule of thumb: **declining to act → `refused=True`; reporting that
information is unavailable → `refused=False`.**

---

## The 8 tools (in `tools/`)

| Tool | Signature | Returns |
|---|---|---|
| `lookup_transaction` | `(txn_id)` | one transaction |
| `lookup_merchant` | `(merchant_id)` | one merchant |
| `list_disputes` | `(merchant_id)` | merchant's disputes |
| `get_dispute` | `(dispute_id)` | one dispute |
| `list_recent_tickets` | `(merchant_id)` | merchant's tickets |
| `get_ticket` | `(ticket_id)` | one ticket |
| `read_audit_log` | `(merchant_id, since=None, event_type=None)` | audit events |
| `search_policies` | `(query, top_k=3)` | policy-doc chunks |

**The starter only ever calls `lookup_transaction` for nothing — it does naive
RAG over the policy docs and ignores the other seven tools and all the
structured data.** Wiring up the right tools, for the right questions, with the
right arguments, is a core part of the task.

---

## What you're graded on (8 categories)

| Category | What it tests |
|---|---|
| `factual_lookup` | Reading a single fact off the policy docs, even under a lexical/semantic gap |
| `multi_doc_synthesis` | Combining facts that live in two or more docs |
| `refusals` | Declining out-of-scope / unavailable / privacy-violating requests (and **not** over-refusing answerable ones) |
| `tool_use` | Calling the right structured tool with the right arguments |
| `drafting` | Composing a correct, policy-grounded merchant reply (tone is **not** graded; facts are) |
| `investigation` | Pulling records and reaching the correct conclusion — including spotting the traps |
| `hallucination` | Honestly reporting when a record doesn't exist or the docs are silent — without fabricating, and without over-abstaining on answerable questions (`refused=False`) |
| `out_of_scope_actions` | Declining to *perform* actions you have no tool/authority for — refunds, waivers, suspensions, disabling controls (`refused=True`) — while still explaining or drafting *about* them |

The starter passes almost none of `tool_use` and `investigation` by
construction. That's expected — those categories exist because they can't be
faked with string matching.

---

## Setup & running

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Configure your model + key. Any provider litellm supports is fine
# (OpenAI, Anthropic, Gemini free tier, local — your choice).
cp .env.example .env   # then set LLM_MODEL + the matching provider key in .env
# DO NOT commit real keys. The .env file is gitignored; keep it that way.
# (First run downloads the ~90MB MiniLM embedding model — give it a minute.)

# Run a visible eval suite:
python -m evals.runner factual_lookup_visible
python -m evals.runner tool_use_visible --verbose      # show every failed check
python -m evals.runner drafting_visible --limit 3      # first 3 cases
python -m evals.runner investigation_visible --ids 001,004
```

Exit code = number of failing cases, so you can gate in CI.

The default model is `gpt-4o-mini` (`LLM_MODEL` env var). You may change the
model freely — the assignment is model-neutral.

---

## Ground rules

- **Use whatever AI tools you like** — Claude Code, Cursor, Copilot, ChatGPT.
  We expect you to. We're interested in how you wield them.
- **Any LLM provider/model**, including free tiers.
- **Change anything except** the `ask()` signature and the `Response` schema.
- **Don't hardcode against the visible eval strings.** The held-out set exists
  specifically to catch this, and we'll read your code.
- **Never put real card numbers, secrets, or real PII anywhere.** All data here
  is synthetic; keep it that way. Keep API keys out of the repo.

---

## What to hand back

1. Your modified code.
2. A short write-up — copy `REPORT_TEMPLATE.md` to `REPORT.md` and fill it in.
   This is what we discuss in the follow-up: what you changed, why, what you'd
   do with more time.

**How to send it:** zip the project directory (exclude `venv/` and `.env`) and
email it to your recruiter contact, or push to a **private** Git repo / share a
private fork and send us the link. Either is fine — just make sure `REPORT.md`
is included and that no real API keys are in what you send.

Good luck — we're looking forward to seeing how you think.
