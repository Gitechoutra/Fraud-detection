# FraudShield architecture

## The big picture

```mermaid
flowchart LR
    subgraph Clients
        Bank["Bank / UPI switch<br/>(X-API-Key)"]
        Sim["simulate.py / evaluate.py"]
        UI["React control room<br/>(analysts, risk managers)"]
        Phones["Demo bank app<br/>(two phones)"]
    end

    subgraph Flask["Flask API (portal/)"]
        API["REST blueprints<br/>portal/api/*"]
        Engine["fraud_engine.py<br/>ingest → persist → CALL → commit"]
        Shield["otp_shield.py<br/>R9-A pre-OTP check"]
        Notifier["notifier.py<br/>Console / MSG91 / Twilio"]
        Sched["scheduler.py<br/>APScheduler"]
    end

    subgraph MySQL["MySQL 8 · fraude"]
        SP1[["sp_evaluate_transaction<br/>rules R1–R9, score, decide, alert"]]
        SP2[["sp_otp_risk_check<br/>R9-A risk points"]]
        Tables[("transactions · rule_hits · alerts · cases<br/>accounts · devices · sessions · beneficiaries<br/>fraud_rules · watchlist · otp_requests …")]
        Views[["v_alert_queue · v_rule_precision · v_daily_stats"]]
        Trg[["audit triggers"]]
    end

    Bank --> API
    Sim --> API
    UI --> API
    Phones --> API
    API --> Engine --> SP1
    API --> Shield --> SP2
    Shield --> Engine
    Engine --> Notifier
    Shield --> Notifier
    SP1 --> Tables
    SP2 --> Tables
    Tables --> Views
    Tables --> Trg
    Sched --> Tables
```

**Python orchestrates, MySQL decides.** The nine rules, the score, the decision, the alert and
case creation all happen inside `sp_evaluate_transaction`. Python never re-implements a rule.

## One payment, step by step

```mermaid
sequenceDiagram
    autonumber
    participant B as Bank / client
    participant A as Flask API
    participant E as fraud_engine.ingest()
    participant DB as MySQL (one transaction)
    participant N as Notifier

    B->>A: POST /api/transactions (JSON)
    A->>A: validate (marshmallow), check API key / role
    A->>E: ingest(payload)
    E->>DB: SELECT ... WHERE external_ref = ? (idempotency)
    alt already seen
        DB-->>E: existing row
        E-->>A: stored decision (duplicate = true)
    else new payment
        E->>DB: INSERT transactions (status PENDING)
        E->>DB: CALL sp_evaluate_transaction(id)
        Note over DB: R1…R9 read thresholds from fraud_rules<br/>INSERT rule_hits for each rule that fires<br/>score = LEAST(100, SUM(weights))<br/>UPDATE status · alert + case if REVIEW/BLOCKED<br/>remember device · update last_txn_at
        DB-->>E: score, status, alert_id, stage timings
        E->>DB: UPDATE decision_ms, stage_timings
        opt REVIEW or BLOCKED
            E->>N: "Was this you?" SMS (row in notifications)
        end
        E->>DB: COMMIT (any error → ROLLBACK everything)
        E-->>A: decision
    end
    A-->>B: 201 { status, risk_score, rules, decision_ms }
```

Because the INSERT, the procedure and the notification share one database transaction, a payment
can never exist without its decision and evidence (`tests/test_ingest_atomicity.py` proves the
rollback). Deadlocks between parallel payments of one account are retried up to three times.

## OTP Shield: two checkpoints

```mermaid
flowchart TD
    Start(["Customer (or a scammer) presses Send"]) --> R9A{{"R9-A: sp_otp_risk_check<br/>who is asking?"}}
    R9A -->|"0–19 points"| OTP["Normal OTP<br/>(6 digits, 3 min, stored as a hash)"]
    R9A -->|"20–39 points"| WARN["OTP with an explicit warning:<br/>'OTP 482913 is to SEND ₹15,000 to Kumar (NEW payee)…'"]
    R9A -->|"40+ points"| NOOTP["NO OTP is generated.<br/>Registered phone asks: Was this you?"]
    OTP --> Verify["verify OTP (max 3 tries)"]
    WARN --> Verify
    Verify --> Pay
    NOOTP -->|YES| Trust["Trust the new device"] --> Pay
    NOOTP -->|NO| Deny["Block · log the device out · freeze payee 24 h<br/>watchlist device, IP, payee · HIGH alert"]
    Pay["Payment → fraud_engine.ingest()"] --> R9B{{"R9-B inside sp_evaluate_transaction<br/>(safety net)"}}
    R9B --> Decision(["APPROVED / REVIEW / BLOCKED"])
```

## Code layout

| Layer | Where | Responsibility |
|---|---|---|
| SQL engine | `portal/sql/*.sql` | indexes, views, audit triggers, `sp_evaluate_transaction`, `sp_otp_risk_check`, `fn_inr` |
| Loader | `helpers/db_helpers.py` | runs the SQL files, honouring `DELIMITER` (also called from the Alembic migration) |
| Services | `portal/services/` | `fraud_engine`, `otp_shield`, `notifier`, `simulator`, `evaluator` |
| API | `portal/api/` | thin blueprints: validate → call a service → `ok()` / `error()` |
| Models | `portal/models/` | SQLAlchemy tables (schema source for Flask-Migrate) |
| Jobs | `portal/scheduler.py` | expire OTPs (1 min), refresh `daily_stats` (5 min), nightly dormant marking |
| UI | `frontend/src/` | React 18 + Vite + Tailwind + Framer Motion + Recharts |

## Data model (main tables)

```mermaid
erDiagram
    customers ||--o{ accounts : owns
    accounts ||--o{ devices : "seen on"
    accounts ||--o{ sessions : "security events"
    accounts ||--o{ beneficiaries : payees
    accounts ||--o{ transactions : makes
    merchants ||--o{ transactions : receives
    beneficiaries ||--o{ transactions : receives
    transactions ||--o{ rule_hits : evidence
    fraud_rules ||--o{ rule_hits : fired
    transactions ||--o| alerts : raises
    otp_requests ||--o| alerts : raises
    alerts ||--|| cases : "investigated in"
    cases ||--o{ case_notes : notes
    accounts ||--o{ otp_requests : "OTP Shield checks"
    otp_requests ||--o| device_approvals : "Was this you?"
    customers ||--o{ notifications : receives
```

## Performance design

* Every rule reads one account's recent history, so the indexes start with `account_id` and end
  with a time column (`ix_txn_account_time`, `ix_sessions_account_event_time`, ...).
* The watchlist check is an index lookup on `(entry_type, entry_value)`.
* Only the evaluated row is locked (`SELECT ... FOR UPDATE OF t`), so payments of different
  accounts never wait for each other.
* Measured on a laptop: ~15 ms median, ~30 ms p95 per decision (`tests/test_performance.py`);
  see `docs/RULES.md` for the full evaluation results.

## Security

* bcrypt password hashes; JWT access (15 min) + refresh (7 days); logout revokes both
  (`token_blocklist`).
* Role checks on every staff endpoint (`min_role`), enforced on the server even though the UI also
  hides what a role cannot do. Demo-bank tokens are a separate kind and never pass a staff check.
* All SQL is parameterised; the only identifiers formatted into SQL (procedure and database names)
  are validated against a strict pattern first.
* Rate limits: login 10/min, OTP requests 5 per account per 10 min, 3 OTP attempts.
* CORS only for `FRONTEND_ORIGIN`. Errors return a generic message; details go to `logs/app.log`
  with the request ID that is also returned in the `X-Request-ID` header.
