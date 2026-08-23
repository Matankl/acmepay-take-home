# Acmepay Settlement Timing

When funds from processed transactions become available in your linked bank account.

## Standard Settlement

For **established merchants in good standing**, settled funds are deposited to your linked bank account on a **T+2 business day** schedule, where T is the transaction date.

- Transaction processed on Monday → funds available Wednesday
- Transaction processed on Friday → funds available Tuesday (skipping weekend)
- Bank holidays extend this window by one business day per holiday

## New Merchant Settlement (First 90 Days)

For the first **90 days** after Acmepay approval, new merchants are placed on extended settlement:

- **Settlement window:** T+5 business days
- **Rolling reserve:** 10% of each day's processing volume is held in reserve for 90 days from the date of each transaction
- The rolling reserve releases automatically on a rolling basis (funds held from day 1 release on day 91)

After the 90-day period, new merchants in low-risk categories transition automatically to standard T+2, provided no excessive chargebacks or risk events have occurred. The rolling reserve continues to release on a rolling basis until fully discharged.

## High-Risk Categories — Extended Settlement Indefinite

Merchants in elevated-risk categories remain on extended settlement beyond the initial 90 days. The 90-day auto-graduation does NOT apply.

High-risk categories include:

- Subscription billing
- Digital goods and services
- Travel and hospitality
- High-ticket items ($5,000+ average transaction)
- Nutraceuticals and supplements (typically rejected at onboarding; see onboarding_playbook.md)

High-risk merchants typically have a 15% rolling reserve instead of the standard 10%. To move to standard T+2, see "Conditions for Moving Off Extended Settlement" in `chargeback_policy.md`.

## Settlement Schedule Override

Merchants on the Pro plan may request weekly batch settlement (Friday batch) at no additional charge. Contact your account manager to switch.

## Holiday Schedule

Settlement does not occur on US federal banking holidays. Holidays observed:

- New Year's Day
- MLK Day
- Presidents' Day
- Memorial Day
- Juneteenth
- Independence Day
- Labor Day
- Columbus Day
- Veterans Day
- Thanksgiving
- Christmas Day

## Failed Settlement

If a settlement transfer fails (closed bank account, incorrect routing number):

1. Funds remain in the Acmepay balance
2. Email and dashboard notification sent
3. Update banking details — Acmepay retries within 24 hours
4. Repeated failures may result in temporary account hold

## Reconciliation

Each settlement deposit is accompanied by a settlement statement available in the dashboard and via `/v1/payouts`. Statements break down the deposit by:

- Gross processing volume
- Refunds
- Chargebacks and chargeback fees
- Acmepay processing fees
- Rolling reserve withholding
- Net deposit amount
