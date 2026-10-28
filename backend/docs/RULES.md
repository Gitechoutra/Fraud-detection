# The nine fraud rules

All nine rules run **inside MySQL**, in the stored procedure `sp_evaluate_transaction`
(`portal/sql/04_sp_evaluate_transaction.sql`). Every threshold and weight is read from the
`fraud_rules` table on every payment, so a change made in the Rules page applies to the very next
payment. Nothing is hard-coded in Python.

**Score** = `LEAST(100, SUM(weight of every rule that fired))`.
**Decision** (bands in `system_settings`, editable): 0–39 **Approved** · 40–69 **Held for review** ·
70–100 **Blocked**. Held and blocked payments get an alert and an investigation case.

Each rule that fires writes a `rule_hits` row with the value it saw and a plain-English sentence,
which is exactly what the app shows under “Why was this decision made?”.

## Final default settings

| Code | Simple name | Fires when (defaults) | Weight (final) | Weight (spec start) |
|---|---|---|---|---|
| R1 | Unusually large amount | amount > **5 ×** the account's average approved amount over **90** days, with ≥ **3** past payments | **40** | 30 |
| R2 | Too many payments too fast | more than **5** payments in **10** minutes (this one included) | **40** | 25 |
| R3 | Impossible travel | previous payment was in a **different city** less than **30** minutes ago | **45** | 35 |
| R4 | New device, big amount | device **never seen** on this account and amount > **₹25,000** | **40** | 20 |
| R5 | Late-night large payment | between **00:00** and **05:00** and amount > **₹10,000** | **40** | 10 |
| R6 | Known fraudster | device, IP, shop, payee account or the account itself is on the **watchlist** | **70** | 50 |
| R7 | Splitting money to dodge limits | ≥ **3** payments between **₹45,000** and **₹49,999** within **24** hours | **40** | 15 |
| R8 | Sleeping account wakes up | no activity for **180** days and amount > **₹20,000** | **40** | 20 |
| R9 | OTP / phishing-link fraud | payee added < **24** h ago, amount ≥ **₹10,000**, and the OTP was typed on an untrusted device **or** the payment is within **15** min of a login from a new device / SIM change / password reset / mobile-number change | **55** | 45 |

Only the weights changed during tuning; every threshold is still the specification's value.

---

## Each rule in plain English, and its SQL

### R1 — Unusually large amount
*The payment is many times bigger than what this person usually spends.*
Example: Priya usually spends about ₹2,000; suddenly ₹40,000 is spent on her card.

```sql
SELECT AVG(amount), COUNT(*) INTO v_avg, v_cnt
  FROM transactions
 WHERE account_id = v_account_id
   AND txn_time >= v_time - INTERVAL CAST(r_p3 AS UNSIGNED) DAY     -- 90-day look-back
   AND txn_time < v_time AND status = 'APPROVED' AND id <> p_txn_id;
-- fires when v_cnt >= r_p2 (3) AND v_amount > r_p1 (5) * v_avg
```
Technique: `AVG()` over an indexed time range (`ix_txn_account_time`). Only approved payments
count, so earlier fraud attempts don't inflate the “usual” amount.

### R2 — Too many payments too fast
*Lots of payments in a few minutes is how fraudsters test or drain stolen cards.*

```sql
SELECT COUNT(*) INTO v_cnt FROM transactions
 WHERE account_id = v_account_id
   AND txn_time BETWEEN v_time - INTERVAL CAST(r_p2 AS UNSIGNED) MINUTE AND v_time;
-- fires when v_cnt > r_p1 (5)
```
Technique: sliding-window `COUNT()`.

### R3 — Impossible travel
*The card was used in Hyderabad and then in Mumbai 20 minutes later. Nobody can travel that fast.*

```sql
SELECT x.prev_city, x.prev_time INTO v_prev_city, v_prev_time
  FROM (SELECT id,
               LAG(city)     OVER w AS prev_city,
               LAG(txn_time) OVER w AS prev_time
          FROM transactions
         WHERE account_id = v_account_id
           AND txn_time BETWEEN v_time - INTERVAL CAST(r_p1 AS UNSIGNED) MINUTE AND v_time
           AND (status <> 'BLOCKED' OR id = p_txn_id)
        WINDOW w AS (ORDER BY txn_time, id)) x
 WHERE x.id = p_txn_id;
-- fires when v_prev_city <> v_city   (minutes = TIMESTAMPDIFF(MINUTE, v_prev_time, v_time))
```
Technique: `LAG()` window function + `TIMESTAMPDIFF`. Blocked attempts are skipped, so a stopped
fraud attempt in another city doesn't flag the real customer's next payment.

### R4 — New device, big amount
*A criminal who steals a password logs in from their own phone.*

```sql
IF v_device IS NOT NULL AND v_amount > r_p1                         -- ₹25,000
   AND NOT EXISTS (SELECT 1 FROM devices
                    WHERE account_id = v_account_id AND device_id = v_device) THEN ...
```
Technique: `NOT EXISTS` on `devices`, checked **before** the procedure registers the device.
A device is only registered after an **approved** payment, so a blocked fraudster's phone never
becomes “known”.

### R5 — Late-night large payment
*Fraud often happens while the owner is asleep.*

```sql
IF HOUR(v_time) >= r_p1 AND HOUR(v_time) < r_p2 AND v_amount > r_p3 THEN ...   -- 0, 5, ₹10,000
```

### R6 — Known fraudster
*Something in the payment was already reported for fraud.*

```sql
SELECT w.entry_type, w.entry_value, w.reason INTO v_event, v_obs, v_txt
  FROM watchlist w
 WHERE (w.entry_type = 'IP'       AND w.entry_value = v_ip)
    OR (w.entry_type = 'DEVICE'   AND w.entry_value = v_device)
    OR (w.entry_type = 'MERCHANT' AND w.entry_value IN (v_merchant_str, v_merchant_name))
    OR (w.entry_type = 'ACCOUNT'  AND w.entry_value IN (v_payee_acct, v_account_no))
 ORDER BY FIELD(w.entry_type, 'DEVICE', 'IP', 'ACCOUNT', 'MERCHANT') LIMIT 1;
```
Technique: `EXISTS`-style lookup on the unique index `(entry_type, entry_value)`.

### R7 — Splitting money to dodge limits
*Breaking a big amount into pieces just under ₹50,000 to avoid extra checks (“structuring”).*

```sql
IF v_amount BETWEEN r_p2 AND r_p3 THEN                               -- ₹45,000 – ₹49,999
  SELECT COUNT(*) INTO v_cnt FROM transactions
   WHERE account_id = v_account_id AND amount BETWEEN r_p2 AND r_p3
     AND txn_time BETWEEN v_time - INTERVAL CAST(r_p4 AS UNSIGNED) HOUR AND v_time;   -- 24 h
  -- fires when v_cnt >= r_p1 (3)
```

### R8 — Sleeping account wakes up
*Forgotten accounts are easy targets because nobody is watching them.*

```sql
SET v_days = DATEDIFF(v_time, COALESCE(v_last_txn, v_opened));   -- accounts.last_txn_at
-- fires when v_days >= r_p1 (180) AND v_amount > r_p2 (₹20,000)
```
`last_txn_at` is updated only after the rules ran, and only for approved payments.

### R9 — OTP / phishing-link fraud (the payment-time safety net)
*Money sent to a brand-new payee right after a risky login is the classic OTP scam.*

```sql
IF v_benef IS NOT NULL AND v_amount >= r_p3                                     -- ₹10,000
   AND v_payee_added BETWEEN v_time - INTERVAL CAST(r_p1 AS UNSIGNED) HOUR AND v_time THEN   -- 24 h
  -- (a) the OTP for this payment was typed on an untrusted device
  SELECT o.verified_device_id INTO v_obs FROM otp_requests o
   WHERE o.id = v_otp AND o.verified_device_id IS NOT NULL
     AND NOT EXISTS (SELECT 1 FROM devices d WHERE d.account_id = v_account_id
                       AND d.device_id = o.verified_device_id AND d.is_trusted = 1);
  -- (b) or a risky security event in the last r_p2 (15) minutes
  SELECT s.event_type, TIMESTAMPDIFF(MINUTE, s.created_at, v_time) INTO v_event, v_mins
    FROM sessions s
   WHERE s.account_id = v_account_id
     AND s.created_at BETWEEN v_time - INTERVAL CAST(r_p2 AS UNSIGNED) MINUTE AND v_time
     AND (s.event_type IN ('SIM_CHANGE', 'PASSWORD_RESET', 'MOBILE_CHANGE')
          OR (s.event_type = 'LOGIN' AND NOT EXISTS (
                SELECT 1 FROM devices d WHERE d.account_id = v_account_id
                   AND d.device_id = s.device_id AND d.is_trusted = 1)))
   ORDER BY s.created_at DESC LIMIT 1;
```
Technique: `EXISTS` / `NOT EXISTS` across `beneficiaries`, `sessions`, `devices` and
`otp_requests`, plus `TIMESTAMPDIFF`.

## OTP Shield — checkpoint R9-A (before any OTP exists)

`sp_otp_risk_check` (`portal/sql/05_sp_otp_risk_check.sql`) adds points for who is asking:

| Signal | Points |
|---|---|
| Requesting device is not a trusted device of this account | +15 |
| Payee was added less than 24 hours ago (R9 setting 1) | +15 |
| Within 15 minutes of a login from an untrusted device (R9 setting 2) | +10 |
| City differs from the customer's home city, or a never-used IP | +5 |
| Password reset, SIM change or mobile-number change in the last 48 hours | +10 |
| Amount > 3 × the account's 90-day average | +10 |
| Device, IP or payee account on the watchlist | +40 |

**0–19 → OTP sent** · **20–39 → OTP sent with an explicit warning** (“OTP 482913 is to SEND ₹15,000
to Kumar (NEW payee). If you did not start this, DO NOT share it.”) · **40+ → no OTP at all**; the
customer's registered phone is asked “Was this you?”. NO → payment denied, the device's sessions
logged out, the payee frozen for 24 hours, device + IP + payee account added to the watchlist, and
a HIGH alert raised. YES → the device becomes trusted and the payment goes through the normal
nine-rule check.

---

## How the weights were tuned

`python evaluate.py` builds a fresh labelled data set (5,000 payments, 3% fraud spread evenly over
the nine fraud stories, at random times over the last 7 days), sends every payment through the real
API, and compares decisions with the labels. A payment counts as “flagged” when it is held or
blocked.

**Run 1 — specification weights** (R1 30, R2 25, R3 35, R4 20, R5 10, R6 50, R7 15, R8 20, R9 45):

| Recall | FPR | Precision | Caught per story |
|---|---|---|---|
| **34.0%** | 0.00% | 100% | R6 17/17, R7 16/16, R9 16/16 — **R1, R2, R3, R4, R5, R8: 0** |

Every story's own rule *fired* (17/17 for each), but a story that trips a single rule worth less
than 40 points was approved. With these weights, only R6 alone, or two rules together, could ever
reach the hold line.

**Change:** raise every rule's weight to at least the 40-point hold line (so any single warning
sign is enough to pause a payment for a human check), make a watchlist match (R6, 70) block on its
own, and keep R9 above the hold line (55) so OTP-scam payments are paused even when nothing else
fires. Two warning signs together (≥ 80) block. Thresholds were left unchanged.

**Run 2 — final weights**, 5,000 labelled payments through the HTTP API (Waitress, 16 client
threads, laptop with MySQL 8.0 on the same machine):

| Metric | Result | Target |
|---|---|---|
| Recall (fraud caught) | **100%** (150 / 150) | ≥ 90% ✓ |
| False-positive rate | **0.10%** (5 of 4,866 genuine) | ≤ 5% ✓ |
| Precision | 96.8% | — |
| F1 | 98.4% | — |
| Decision latency p50 / p95 | 68 ms / **256 ms** (under 16-way load) | p95 ≤ 500 ms ✓ |
| Throughput | **103 payments/s** | ≥ 100 ✓ |

Single-client latency (`tests/test_performance.py`, 500 payments): p50 ≈ 15 ms, p95 ≈ 30 ms.
Under load, latency is mostly time waiting for the single Python process (Waitress threads share
one interpreter), not time in MySQL. Throughput clears the target only narrowly on this laptop and
will vary with the machine.

Per rule in run 2: every rule had 100% precision except **R3 (79%)**. All 5 false alarms were R3:
a genuine customer paying at home shortly after a stolen-card use in another city that was *held*
(not blocked), which correctly looks like impossible travel from the customer's side. An analyst
clears these in one click; they are the kind of case the “Mark as genuine” button feeds back into
`v_rule_precision`.

### Things worth knowing about the evaluation

* Only the payment a story is designed to catch is labelled fraud. Build-up payments (the first
  five small card-testing payments of R2, the first two structured payments of R7) are unlabelled
  and excluded; the genuine customer's own home-city payment in R3 is labelled genuine.
* Stories pick accounts that make their rule the main signal (R4 uses a high spender so a ₹28,000
  payment is not also “unusually large”). Some stories still trip a companion rule, as real fraud
  does: R7's ₹45,000+ payments are usually also R1, and R9 transfers usually also trip R4.
* The synthetic genuine traffic is well behaved (customers pay near home, within their usual
  amounts and hours), so the false-positive rate here is a lower bound for real traffic.
* Each run deletes everything it created afterwards (`--keep` to keep it), and saves its metrics in
  `metric_runs`, shown on the Evaluation page.
