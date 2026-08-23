# TKT-209 — refund didn't get the fees back?

**Merchant:** M-1001 (Bright Bean Coffee)
**Opened:** 2026-05-22 13:00
**Closed:** 2026-05-22 14:00 by Sarah
**Status:** closed

---

**Merchant (2026-05-22 13:00):**
just refunded a $220 order to a customer (T-99814 i think). expected to see the original processing fee come back to our balance as well — that's the standard pattern with most processors. but the audit log shows the full $220 went to the customer and we ate the original 2.9% + $0.30. is this right?

**Sarah (2026-05-22 14:00):**
That's correct, unfortunately. Acmepay's policy is that the processing fee on the original transaction is retained by Acmepay even on a full refund. So you refunded $220 to the customer, but the original $6.68 in fees stays with us. This is in the fees and pricing doc — and yes, it's a real cost of doing business that catches people off guard.

A couple of practical notes: if a refund is to fix our own error, we can sometimes credit the fee back manually — file a ticket if that's ever the case. But for a customer-initiated change of mind, the fee is non-recoverable.

— S
