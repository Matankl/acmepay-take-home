# TKT-202 — duplicate subscription charge?

**Merchant:** M-1002 (Stratoform Subscriptions)
**Opened:** 2026-05-12 13:40
**Closed:** 2026-05-12 16:20 by Marcus
**Status:** closed

---

**Merchant (2026-05-12 13:40):**
hey — one of our customers got billed twice for their May subscription. transaction IDs T-99817 and one earlier in the month. they want a refund for one of them. how do we handle this on our end vs theirs.

**Marcus (2026-05-12 16:20):**
You can issue the refund directly through `/v1/refunds` or the dashboard — either is fine. Just a heads-up that Acmepay's processing fee on the original transaction isn't returned with the refund, so you'll absorb that 2.4% + $0.30 on the refunded charge.

If the duplicate was a billing-side bug rather than the customer's, I'd recommend doing the refund proactively before they file a chargeback — much cheaper. Refunded transactions show as `refunded` in the API; chargebacks add a $15 fee and damage your ratio.

Looks like you've already issued the refund — confirmed in audit log just now. Closing.

— M
