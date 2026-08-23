# Acmepay Chargeback Policy

## Dispute Window

Cardholders have **120 days** from the transaction date to initiate a dispute with their card issuer. Some card networks allow longer windows for specific dispute reasons (fraud, credit not processed).

## Merchant Response Window

When a chargeback is filed against your account, you have **7 calendar days** from notification to submit a response with supporting evidence through the Acmepay dashboard or the `/v1/disputes` endpoint.

If you do not respond within 7 days, the dispute is automatically lost.

## Funds Handling During Dispute

When a chargeback is filed:

1. The disputed amount is **immediately debited** from your Acmepay balance.
2. The $15 chargeback fee (see `fees_and_pricing.md`) is also debited at this time.
3. If you win the dispute, the disputed funds are returned to your balance **60–75 days** after the original chargeback date.
4. The chargeback fee itself is **non-refundable**, even if you win the dispute.

Example, $1,000 disputed charge:
- Day 0: $1,000 + $15 debited from balance
- Day 7: merchant response due
- Day 60–75: $1,000 returned if dispute won; the $15 stays gone

## Evidence That Helps

Strong dispute responses typically include:

- Proof of delivery (tracking number, signed delivery confirmation)
- Customer communication records (emails, support tickets)
- Refund/return policy at time of sale
- Photo or scan of signed receipt
- IP address and device fingerprint at time of transaction

## Excessive Chargebacks — Thresholds

Acmepay monitors merchants' chargeback ratios on a rolling 30-day basis. There are two thresholds:

- **Monitoring (1.0%):** at or above 1.0% triggers automated email warnings and increased scrutiny. No account action at this level alone, but the next 30 days are watched closely.
- **Suspension risk (1.5%):** at or above 1.5% may result in account hold, forced extension of the rolling reserve window, and/or account suspension subject to risk team review.

Merchants on extended settlement (new merchants or high-risk categories) are evaluated against the same thresholds.

## Conditions for Moving Off Extended Settlement

If a merchant is on extended settlement (T+5 + rolling reserve) due to high-risk categorization, the conditions for moving to standard T+2 are:

- Chargeback ratio sustained below 0.7% for 6+ consecutive months
- Account on platform 12+ months with no risk events
- Volume stability month-over-month
- Account manager review and risk-team approval required

## Dispute Reason Codes

Acmepay surfaces the card-network reason code with each chargeback. Common codes:

- **fraudulent** — cardholder did not authorize the transaction
- **product_not_received** — goods/services not delivered
- **product_unacceptable** — goods/services not as described
- **credit_not_processed** — refund promised but not issued
- **duplicate** — same transaction charged twice
