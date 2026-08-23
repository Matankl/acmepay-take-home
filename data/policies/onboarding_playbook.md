# Acmepay Onboarding Playbook

This playbook covers merchant onboarding from application through approval, including KYC requirements, restricted categories, and the appeal process.

## Standard Application Flow

1. **Application submission** — merchant provides business name, EIN/Tax ID, owner identity verification, banking details
2. **Initial review** — automated screening + manual reviewer
3. **KYC verification** — typically 1-3 business days
4. **Approval or rejection** — decision communicated via email
5. **Account activation** — approved merchants can process within 24 hours of approval

## KYC Requirements

All applicants must provide:

- Legal business name and EIN
- Business address (no P.O. boxes for primary)
- Beneficial owner identity (driver's license or passport for 25%+ owners)
- Bank account for settlement (verified via micro-deposit)
- Business website or storefront URL
- Estimated monthly processing volume

## Restricted Categories

Acmepay does not onboard merchants in the following categories through the standard flow:

- **Adult content and services**
- **Marijuana and CBD products** (state-by-state exception process available)
- **Firearms and ammunition**
- **Gambling and lottery**
- **Pharmaceuticals and prescription drugs**
- **Nutraceuticals and supplements**
- **Multi-level marketing (MLM)**
- **Cryptocurrency exchanges**
- **Debt collection services**
- **Cash advance and short-term lending**

Applications in these categories are rejected by default. The rejection email includes the specific category restriction triggered.

## Appeal Process for Restricted Categories

There is an exception process for established merchants in restricted categories with strong compliance records. To submit for review:

1. **12 months of statements** from your current processor (showing volume and chargeback ratios)
2. **Compliance documentation** specific to your category (e.g. FDA labeling for nutraceuticals, state license for CBD)
3. **Business license** and proof of years in operation
4. **Reference letter** from a current banking or processing partner

Submit the package through the dashboard or via your point of contact. Expected turnaround is **7–10 business days** from submission of complete documentation.

Approval is not guaranteed. Merchants approved through the appeal process are typically placed on **Pro plan with extended settlement (T+5 + 15% rolling reserve)** as a starting configuration, with terms reviewed at the 12-month mark.

## High-Risk Categories (Approved with Conditions)

Some categories are allowed but classified as high-risk from day one:

- Subscription billing
- Travel and hospitality
- Digital goods and services
- High-ticket items ($5,000+ average transaction)

These merchants are approved through the standard flow but placed directly on Pro plan with extended settlement. They do not auto-graduate from the 90-day window — see settlement_timing.md for the conditions to move to standard T+2.

## New Merchant Configuration

All approved merchants (low-risk or high-risk) start with:

- **First 90 days:** T+5 settlement, 10% rolling reserve (low-risk) or 15% (high-risk)
- Account flag: `new_merchant_90day` (low-risk) or `high_risk_category` (high-risk)
- Restricted to documented business model — material changes require re-review

## Rejection and Re-application

A rejected applicant may:

- File an appeal (see "Appeal Process" above) — recommended path for restricted-category rejections
- Re-apply after addressing the rejection reason (KYC gap, incomplete docs)
- Wait 6 months and re-apply without changes (not recommended)

Rejected applicants are NOT created as merchant records in the merchants database. Their rejection is recorded in the audit log only.
