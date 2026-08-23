# Acmepay Fees and Pricing

## Standard Plan

The Acmepay Standard plan is the default offering for new merchants. No monthly fee, no setup fee.

- **Per-transaction fee:** 2.9% + $0.30
- **Monthly fee:** None
- **Setup fee:** None
- **Volume requirement:** None

## Pro Plan

The Acmepay Pro plan is available for merchants processing over $50,000 per month.

- **Per-transaction fee:** 2.4% + $0.30
- **Monthly fee:** $99
- **Setup fee:** None
- **Volume requirement:** $50,000+/month in processing

## International Cards

For cards issued outside the United States, an additional surcharge applies on top of the base transaction fee:

- **International surcharge:** +1.5%
- Applies to all plans equally
- The surcharge is charged to the MERCHANT, not the cardholder
- Example: a $100 international transaction on the Standard plan costs the merchant 2.9% + 1.5% + $0.30 = $4.70 in fees; the customer is charged exactly $100.

## Currency Conversion

For transactions processed in a currency other than the merchant's settlement currency:

- **Conversion fee:** 1.0% on the converted amount
- Mid-market exchange rates are used, refreshed daily

## Chargeback Fees

When a customer disputes a transaction with their card issuer:

- **Chargeback fee:** $15 per disputed transaction
- The fee is debited immediately when the chargeback is filed
- The fee applies whether the dispute is won or lost
- See `chargeback_policy.md` for the full dispute process

## Refunds

- **Refund fee:** None
- However, the **original transaction fee is NOT returned** when a refund is issued
- Acmepay keeps the per-transaction fee (e.g. 2.9% + $0.30 on Standard) even when a transaction is fully refunded
- Exception: if a refund is needed to fix an Acmepay-side error, the fee can sometimes be credited back manually via a support ticket
- Refunds can be issued via the `/v1/refunds` endpoint or the merchant dashboard

## Payout Fees

- **ACH payout to US bank:** Free
- **Wire transfer payout:** $25 per wire
- **International payout:** $35 per transfer
