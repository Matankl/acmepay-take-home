# Solution Write-Up — Acmepay Support Copilot

> Copy this file to `REPORT.md` and fill it in. Keep it concise — bullet points
> are fine. We use this to guide the follow-up conversation, so write what
> you'd want to talk through. Aim for ~1–2 pages.

**Your name:**
**Time spent (rough):**
**Model(s) / provider used:**

---

## 1. Summary

A few sentences: what state did you get the system to, and what's the headline
of your approach?

---

## 2. What I changed and why

Walk through the meaningful changes. For each, the problem you saw and the
decision you made. Suggested areas (cover what's relevant — you don't have to
touch all of them):

- **Retrieval** (chunking, embeddings, reranking, top-k, hybrid search):
- **Tool use** (when/how the system decides to call which tool, argument extraction):
- **Prompting / system design** (role, instructions, structured-output strategy):
- **Refusal & grounding** (how you decide to refuse; how you avoid hallucinating):
- **Control flow** (single-shot vs. multi-step / agentic, routing by category):
- **Anything else:**

---

## 3. Results

How your system does on the visible suites (and any held-out you simulated).

| Category | Before (starter) | After |
|---|---|---|
| factual_lookup | | |
| multi_doc_synthesis | | |
| refusals | | |
| tool_use | | |
| drafting | | |
| investigation | | |

Note any cases you couldn't pass and why you think so.

---

## 4. Tradeoffs & things I'd do with more time

- What did you deliberately skip or simplify, and why?
- Where would you invest the next 8 hours?
- Anything you think is wrong or unsupported in the assignment itself?

---

## 5. Correctness & safety notes

- How do you keep the system from inventing facts or fabricating data
  (e.g. a settlement schedule for a non-merchant, a status for a missing record)?
- How do you handle requests that should be refused vs. answered?
- Any cost / latency / reliability considerations in your design?

---

## 6. How to run your solution

Anything we need to know beyond the README to reproduce your results
(env vars, model, a one-liner to run the suites).
