# FraudShield API

Base URL: `http://localhost:5000/api` (Docker: `http://localhost:8080/api`).

## Conventions

Every response has the same shape:

```json
{ "ok": true,  "data": { ... } }
{ "ok": false, "error": { "code": "VALIDATION_ERROR", "message": "Some fields are missing or invalid.", "details": { "amount": ["..."] } } }
```

| HTTP | When |
|---|---|
| 200 / 201 | Success (201 = created) |
| 202 | Accepted, running in the background (evaluation) |
| 400 | Bad request / business rule (e.g. wrong OTP) |
| 401 | Not logged in, token expired or revoked |
| 403 | Logged in, but your role can't do this |
| 404 | Not found |
| 409 | Conflict (duplicate, already closed) |
| 410 | Expired (OTP / approval) |
| 422 | Validation error (`details` lists each field) |
| 423 | Payee on 24-hour safety hold |
| 429 | Rate limited |
| 500 | Server error (details only in `logs/app.log`; every response has an `X-Request-ID`) |

**Authentication.** Staff endpoints need `Authorization: Bearer <access_token>` from `/auth/login`.
Access tokens last 15 minutes, refresh tokens 7 days.
Roles are ranked **ADMIN > RISK_MANAGER > ANALYST**; "ANALYST+" means any staff role.
Ingestion also accepts `X-API-Key: <INGEST_API_KEY from .env>`.
Demo-bank endpoints use a separate token from `/bank-demo/login`, which never works on staff endpoints.

Lists accept `?page=1&per_page=25` and return `{ items, total, page, per_page, pages }`.

---

## Auth

| Method | Path | Role | Notes |
|---|---|---|---|
| POST | `/auth/login` | public (10/min) | `{ "username", "password" }` → `{ access_token, refresh_token, user }` |
| POST | `/auth/refresh` | refresh token | → `{ access_token }` |
| GET | `/auth/me` | any staff | current user |
| POST | `/auth/logout` | any token | body `{ "refresh_token" }` (optional). Revokes both tokens |

```bash
curl -X POST localhost:5000/api/auth/login -H "Content-Type: application/json" \
     -d '{"username":"admin","password":"Admin@123"}'
```

## Transactions

| Method | Path | Role |
|---|---|---|
| POST | `/transactions` | ADMIN or `X-API-Key` |
| POST | `/transactions/bulk` | ADMIN or `X-API-Key` (multipart `file`, CSV) |
| GET | `/transactions` | ANALYST+ |
| GET | `/transactions/latest?since_id=` | ANALYST+ |
| GET | `/transactions/{id}` | ANALYST+ |

**Ingest one payment** — the payment is saved, checked by `sp_evaluate_transaction` and committed
in one database transaction. Sending the same `external_ref` again returns the stored decision with
`"duplicate": true` (HTTP 200) instead of creating a second payment.

```json
POST /api/transactions
X-API-Key: dev-ingest-key
{
  "external_ref": "BANK-000123",
  "account_no": "30219876543210",
  "amount": 48000,
  "channel": "NETBANKING",
  "city": "Delhi",
  "device_id": "NEW-PHONE-1",
  "ip_address": "103.21.4.9",
  "beneficiary_id": 12,
  "txn_time": "2026-10-28T14:05:00"
}
```

Fields: `external_ref`*, `account_id` or `account_no`*, `amount`*, `channel`* (`CARD|UPI|NETBANKING|ATM`),
`merchant_id`, `beneficiary_id`, `otp_request_id`, `city`, `device_id`, `ip_address`,
`txn_time` (defaults to now), `currency` (INR).

```json
201 Created
{
  "ok": true,
  "data": {
    "txn_id": 27105, "external_ref": "BANK-000123", "account_id": 201, "amount": 48000.0,
    "status": "BLOCKED", "risk_score": 100, "decision_ms": 14.21, "total_ms": 16.02,
    "stage_timings": { "ingest": 1.1, "save": 1.9, "rules": 8.4, "score": 0.2, "decide": 0.4, "alert": 1.3 },
    "rules": [
      { "rule_code": "R1", "weight_applied": 40, "observed_value": "19.2x usual",
        "detail_text": "₹48,000 is 19.2× this account's usual ₹2,500" },
      { "rule_code": "R4", "weight_applied": 40, "observed_value": "NEW-PHONE-1",
        "detail_text": "₹48,000 from a device never seen on this account (limit for new devices ₹25,000)" }
    ],
    "alert_id": 311, "duplicate": false
  }
}
```

**Bulk CSV** — columns `external_ref, account_no (or account_id), amount, channel` plus optional
`city, device_id, ip_address, merchant_id, txn_time`. Max 5,000 rows. Returns
`{ rows, approved, review, blocked, duplicates, errors: [{ line, error }] }`.

**List filters:** `status`, `channel`, `source`, `date_from`, `date_to` (YYYY-MM-DD), `min_score`,
`account_id`, `search` (reference, customer name, account number, city).

**Live feed:** `GET /transactions/latest?since_id=27100` → `{ items: [...oldest first], max_id }`.
Without `since_id` you get the latest 30.

**Detail:** `GET /transactions/{id}` →
`{ transaction, hits, rules (all 9, with fired flag and plain-English sentence), bands, explanation: { headline, reason, next_step }, alert, history (last 20), otp_request }`.

## Alerts and cases

| Method | Path | Role | Body |
|---|---|---|---|
| GET | `/alerts?status=OPEN\|IN_PROGRESS\|CLOSED\|ALL&priority=&mine=1&search=` | ANALYST+ | — |
| GET | `/alerts/{id}` | ANALYST+ | — |
| PATCH | `/alerts/{id}` | ANALYST+ | `{ "assign_to_me": true }` or `{ "assigned_to": 2 }` and/or `{ "alert_status": "IN_PROGRESS" }` |
| GET | `/cases/{id}` | ANALYST+ | → `{ case, alert, hits, otp_request, notes, recent_transactions, timeline }` |
| POST | `/cases/{id}/notes` | ANALYST+ | `{ "body": "Called the customer" }` |
| PATCH | `/cases/{id}/outcome` | ANALYST+ | `{ "outcome": "CONFIRMED_FRAUD" \| "FALSE_POSITIVE", "notes": "..." }` |

Alert lists also return `counts: { OPEN, IN_PROGRESS, CLOSED }`. Closing a case closes its alert and
feeds `v_rule_precision`.

## Rules

| Method | Path | Role | Body |
|---|---|---|---|
| GET | `/rules` | ANALYST+ | → `{ rules (with stats from v_rule_precision), bands, history }` |
| PUT | `/rules/{code}` | RISK_MANAGER+ | any of `param_1..param_4`, `weight` (0–100), `is_active` |
| PUT | `/rules/bands` | RISK_MANAGER+ | `{ "review_threshold": 40, "block_threshold": 70 }` |

Changes apply to the very next payment (the procedure reads `fraud_rules` every time).
A database trigger records each change in `audit_log`.

## Watchlist

| Method | Path | Role |
|---|---|---|
| GET | `/watchlist?type=IP&search=` | ANALYST+ |
| POST | `/watchlist` | RISK_MANAGER+ — `{ "entry_type": "IP\|DEVICE\|ACCOUNT\|MERCHANT", "entry_value", "reason" }` |
| DELETE | `/watchlist/{id}` | RISK_MANAGER+ |

## OTP Shield and the demo bank app

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/bank-demo/info` | public | Demo login and the ready-made scam payee |
| POST | `/bank-demo/login` | public (20/min) | `{ netbanking_id, password, device_id, ip_address, city }` → `{ token, customer, account, device, payees }` (logs a LOGIN session) |
| GET | `/bank-demo/me` | bank token | profile + payees |
| POST | `/bank-demo/payees` | bank token | `{ payee_name, payee_account_no, payee_ifsc }` |
| POST | `/bank-demo/send` | bank token | `{ beneficiary_id, amount }` → OTP Shield decision (same as `/otp/request`) |
| POST | `/bank-demo/reset` | ANALYST+ | puts Ravi back to the start of the story |
| POST | `/otp/request` | bank token | `{ beneficiary_id, amount }` |
| POST | `/otp/verify` | bank token | `{ otp_request_id, otp }` → `{ verified, payment }` (payment = fraud-engine decision) |
| GET | `/otp/request/{id}/status` | bank token | request + approval + payment |
| GET | `/otp/approval/pending?account_id=` | bank token | "Was this you?" requests for this account |
| POST | `/otp/approval/{id}/respond` | bank token (trusted device only) | `{ "answer": "YES" \| "NO" }` |
| GET | `/notifications?customer_id=&since_id=` | bank token | SMS/app messages for the phone screen |

OTP Shield response:

```json
{
  "otp_request_id": 41,
  "decision": "OTP_BLOCKED_APPROVAL_REQUIRED",
  "risk_points": 55,
  "signals": [
    { "code": "UNTRUSTED_DEVICE", "points": 15, "text": "This phone or computer is not one of the customer's trusted devices" },
    { "code": "NEW_PAYEE", "points": 15, "text": "The payee Kumar was added only 1 min ago" },
    { "code": "NEW_DEVICE_LOGIN", "points": 10, "text": "Someone logged in from a new device 2 min ago" },
    { "code": "NEW_LOCATION", "points": 5, "text": "The request comes from Delhi, but the customer lives in Hyderabad" },
    { "code": "LARGE_AMOUNT", "points": 10, "text": "₹48,000 is 19.2× the usual ₹2,500" }
  ],
  "approval_id": 9,
  "expires_at": "2026-10-28T14:10:00",
  "message": "Approve this payment in the app on your registered phone."
}
```

Limits: 5 OTP requests per account per 10 minutes (429), 3 verification attempts per OTP, OTP valid
3 minutes, approval valid 5 minutes.

## Fraud Lab (simulator)

| Method | Path | Role |
|---|---|---|
| GET | `/simulator/scenarios` | ANALYST+ |
| POST | `/simulator/scenario/{NORMAL\|R1..R9}` | RISK_MANAGER+ → `{ scenario, story, expected_rule, expected_rule_fired, target, steps, summary }` |
| POST | `/simulator/stream/start` | RISK_MANAGER+ — `{ "rate": 2, "fraud_ratio": 0.03 }` |
| POST | `/simulator/stream/stop` | RISK_MANAGER+ |
| GET | `/simulator/stream/status` | ANALYST+ |

## Dashboard

| Method | Path | Role |
|---|---|---|
| GET | `/dashboard/summary?range=today\|7d\|30d\|90d` | ANALYST+ → `{ total, approved, review, blocked, money_protected, money_held, avg_decision_ms, open_alerts, high_open, flag_rate }` |
| GET | `/dashboard/charts?range=...` | ANALYST+ → `{ volume, decisions, by_channel, cities, rule_hits, rule_precision }` |

## Evaluation

| Method | Path | Role |
|---|---|---|
| POST | `/evaluation/run` | RISK_MANAGER+ — `{ "size": 1000, "fraud_ratio": 0.03 }` → 202, runs in background |
| GET | `/evaluation/status` | RISK_MANAGER+ → `{ running, done, total, last_run_id, error }` |
| GET | `/evaluation/latest` | RISK_MANAGER+ → latest run with `targets` (pass/fail per target) |
| GET | `/evaluation/history` | RISK_MANAGER+ → last 30 runs |

## Customers, audit, users

| Method | Path | Role |
|---|---|---|
| GET | `/customers?search=` | ANALYST+ |
| GET | `/customers/{id}` | ANALYST+ → `{ customer, accounts, devices, payees, sessions, recent_transactions }` |
| GET | `/audit?entity=&actor=&action=&search=` | RISK_MANAGER+ |
| GET | `/users` | ADMIN |
| POST | `/users` | ADMIN — `{ username, full_name, password (8+), role }` |
| PATCH | `/users/{id}` | ADMIN — any of `full_name, password, role, is_active` (you can't disable yourself) |

## Health

`GET /health` → `{ status, database, procedures }` (no auth). `GET /` → API info.
