# Acmepay API Reference

Concise reference for the Acmepay public API. Full docs at `https://docs.acmepay.example/api`.

## Authentication

All requests authenticate via Bearer token in the `Authorization` header:

```
Authorization: Bearer sk_live_<your_api_key>
```

API keys are issued in the merchant dashboard under Settings → API Keys. Use `sk_test_` keys against the sandbox, `sk_live_` keys against production. Never share or commit API keys.

## Base URLs

- Production: `https://api.acmepay.example`
- Sandbox: `https://api-sandbox.acmepay.example`

## Versioning

API version is set per-account in the dashboard. The current stable version is `2026-01-15`. The version header `Acmepay-Version` overrides the account default per request.

## Core Endpoints

### Charges

- `POST /v1/charges` — create a charge
- `GET /v1/charges/{charge_id}` — retrieve a charge
- `GET /v1/charges` — list charges (paginated, max 100 per page)

### Refunds

- `POST /v1/refunds` — issue a refund (full amount only; partial refunds are not currently supported)
- `GET /v1/refunds/{refund_id}` — retrieve a refund

Note: per the fees policy, the original processing fee is NOT returned on refund.

### Disputes

- `GET /v1/disputes/{dispute_id}` — retrieve a dispute
- `GET /v1/disputes` — list disputes (paginated)
- `POST /v1/disputes/{dispute_id}/evidence` — submit dispute evidence (must be within the 7-day response window)

### Customers

- `POST /v1/customers` — create a customer record
- `GET /v1/customers/{customer_id}` — retrieve a customer
- `DELETE /v1/customers/{customer_id}` — delete a customer (GDPR right-to-erasure)

### Payouts

- `GET /v1/payouts/{payout_id}` — retrieve a payout
- `GET /v1/payouts` — list payouts
- Settlement statements are available as line items on the payout object

## Webhooks

Acmepay sends webhook events for asynchronous state changes. Subscribe via the dashboard or `POST /v1/webhook_endpoints`.

Key event types:

- `charge.succeeded`, `charge.failed`
- `refund.created`
- `dispute.created`, `dispute.updated`, `dispute.closed`
- `payout.created`, `payout.failed`
- `account.warning_issued` (e.g. chargeback ratio crossed monitoring threshold)

Webhook signature verification is required. The signature is in the `Acmepay-Signature` header.

## Rate Limits

- 100 requests/second per API key
- Burst capacity: 200 requests
- Exceeding the limit returns `429 Too Many Requests`

## Error Codes

| Code | Meaning |
| --- | --- |
| 400 | Invalid request (malformed JSON, missing required field) |
| 401 | Invalid API key |
| 402 | Card declined |
| 403 | Action not permitted (e.g. submitting evidence after the 7-day window) |
| 404 | Resource not found |
| 409 | Conflict (e.g. duplicate idempotency key) |
| 422 | Validation error |
| 429 | Rate limit exceeded |
| 500 | Acmepay server error — safe to retry with idempotency key |

## Idempotency

All POST endpoints accept an `Idempotency-Key` header. Recommended for create operations. Acmepay caches responses for 24 hours keyed by the idempotency key.

## Test Card Numbers (Sandbox Only)

For testing in sandbox, use Acmepay's published test card numbers (see sandbox docs). NEVER use real card numbers in test mode.
