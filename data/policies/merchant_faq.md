# Acmepay Merchant FAQ

Common questions from merchants, answered. If your question isn't here, check the policy docs (fees_and_pricing, chargeback_policy, settlement_timing, onboarding_playbook, api_reference) or escalate.

## Account & Settings

**Q: How do I change my settlement bank account?**
A: Dashboard → Settings → Banking → "Add new account." After micro-deposit verification (1–2 business days), you can mark the new account as primary. Old account stays linked until you remove it.

**Q: Can I have multiple users on one Acmepay account?**
A: Yes. Dashboard → Settings → Team. Roles available: Admin, Operator, Read-only. Up to 10 users on Standard, unlimited on Pro.

**Q: Can I download my data?**
A: Yes. Dashboard → Reports → Export. Transactions, refunds, disputes, and payouts can each be exported as CSV for any date range up to 12 months.

## Fees & Refunds

**Q: Are there volume discounts?**
A: The Pro plan is effectively the volume discount — switch when you cross ~$50K/mo. Beyond that, custom pricing is available for merchants processing $1M+/month; contact your account manager.

**Q: Can I get a partial refund?**
A: Partial refunds are not currently supported. Refunds must be for the full transaction amount. (This is a frequently requested feature; check the changelog.)

**Q: Do refunds count against my chargeback ratio?**
A: No. Refunds are voluntary; chargebacks are involuntary disputes filed by the cardholder. Only chargebacks affect the ratio.

## Disputes

**Q: What's the difference between a chargeback and a refund?**
A: A refund is initiated by you (the merchant). A chargeback is initiated by the cardholder through their bank. Chargebacks have fees ($15), windows, and ratio implications; refunds don't.

**Q: Can I waive the chargeback fee?**
A: No. The chargeback fee is non-refundable regardless of dispute outcome.

**Q: What if a customer disputes a refunded transaction?**
A: This shouldn't happen in normal flow — disputes filed after a successful refund are usually filed in error or the customer didn't notice the refund. Submit your refund confirmation as evidence and you typically win.

## Settlement & Payouts

**Q: Why is my balance different from my settled amount?**
A: Your balance includes pending transactions, recent settlements, refunds, and rolling reserve withholdings. The settled amount is funds released to your bank. Check the reconciliation breakdown on each payout statement.

**Q: Can I get instant settlement?**
A: Not at this time. We're aware of demand and it's on the roadmap.

## Customer Data

**Q: Can I see customer card details?**
A: No. Card numbers, CVVs, and full billing details are never exposed via the API or dashboard. You see the last 4 digits and card brand only. This is a PCI-DSS requirement.

**Q: How does GDPR work?**
A: Use `DELETE /v1/customers/{customer_id}` to erase a customer record. Transactions linked to that customer remain (we anonymize the customer reference) for our regulatory record-keeping obligations.

## What's NOT in this FAQ

Some merchant questions cannot be answered from this FAQ alone:

- **Card-issuer-side decline reasons** — Acmepay sees that a card was declined but not why. The cardholder must contact their issuing bank for the reason.
- **Specific tax handling for your jurisdiction** — we don't provide tax advice.
- **Customer behavior or PII data we don't store** (IPs from prior to a transaction, browsing history, etc.).

When in doubt, escalate to risk team or your account manager rather than guess.
