-- ===========================================================================
-- 02_views.sql  --  read-only views used by the dashboard and alert queue
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- v_alert_queue: one row per alert with its transaction, customer and case.
-- OTP Shield alerts have no transaction, so the joins are LEFT JOINs and the
-- account comes from either the transaction or the OTP request.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_alert_queue AS
SELECT
    al.id                 AS alert_id,
    al.source             AS alert_source,
    al.summary            AS summary,
    al.risk_score         AS risk_score,
    al.priority           AS priority,
    al.alert_status       AS alert_status,
    al.assigned_to        AS assigned_to,
    u.full_name           AS assigned_name,
    al.created_at         AS created_at,
    al.updated_at         AS updated_at,
    TIMESTAMPDIFF(MINUTE, al.created_at, NOW(3)) AS age_minutes,
    ca.id                 AS case_id,
    ca.outcome            AS outcome,
    t.id                  AS txn_id,
    t.external_ref        AS external_ref,
    COALESCE(t.amount, o.amount)          AS amount,
    t.channel             AS channel,
    COALESCE(t.city, o.city)              AS city,
    t.status              AS txn_status,
    t.txn_time            AS txn_time,
    al.otp_request_id     AS otp_request_id,
    a.id                  AS account_id,
    a.account_no          AS account_no,
    c.id                  AS customer_id,
    c.name                AS customer_name,
    (SELECT GROUP_CONCAT(rh.rule_code ORDER BY rh.rule_code SEPARATOR ',')
       FROM rule_hits rh WHERE rh.txn_id = t.id) AS rule_codes
FROM alerts al
LEFT JOIN transactions t ON t.id = al.txn_id
LEFT JOIN otp_requests o ON o.id = al.otp_request_id
LEFT JOIN accounts a     ON a.id = COALESCE(t.account_id, o.account_id)
LEFT JOIN customers c    ON c.id = a.customer_id
LEFT JOIN cases ca       ON ca.alert_id = al.id
LEFT JOIN users u        ON u.id = al.assigned_to;

-- ---------------------------------------------------------------------------
-- v_rule_precision: how often each rule is right, judged by the analysts'
-- case outcomes. precision = confirmed fraud / (confirmed + false positive).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_rule_precision AS
SELECT
    r.rule_code,
    r.simple_name,
    COUNT(rh.id)                                                 AS hits,
    COALESCE(SUM(ca.outcome = 'CONFIRMED_FRAUD'), 0)             AS confirmed_fraud,
    COALESCE(SUM(ca.outcome = 'FALSE_POSITIVE'), 0)              AS false_positives,
    COALESCE(SUM(ca.outcome IS NULL AND al.id IS NOT NULL), 0)   AS undecided,
    CASE
        WHEN COALESCE(SUM(ca.outcome IS NOT NULL), 0) = 0 THEN NULL
        ELSE ROUND(SUM(ca.outcome = 'CONFIRMED_FRAUD') / SUM(ca.outcome IS NOT NULL), 4)
    END                                                          AS precision_v
FROM fraud_rules r
LEFT JOIN rule_hits rh ON rh.rule_code = r.rule_code
LEFT JOIN alerts al    ON al.txn_id = rh.txn_id
LEFT JOIN cases ca     ON ca.alert_id = al.id
GROUP BY r.rule_code, r.simple_name, r.sort_order
ORDER BY r.sort_order;

-- ---------------------------------------------------------------------------
-- v_daily_stats: totals per calendar day (copied into daily_stats every
-- 5 minutes by the scheduler for fast dashboard charts).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_daily_stats AS
SELECT
    DATE(t.txn_time)                                    AS stat_date,
    COUNT(*)                                            AS total,
    SUM(t.status = 'APPROVED')                          AS approved,
    SUM(t.status = 'REVIEW')                            AS review,
    SUM(t.status = 'BLOCKED')                           AS blocked,
    SUM(t.amount)                                       AS total_amount,
    COALESCE(SUM(CASE WHEN t.status = 'BLOCKED' THEN t.amount END), 0) AS blocked_amount,
    ROUND(AVG(t.decision_ms), 2)                        AS avg_decision_ms
FROM transactions t
WHERE t.status <> 'PENDING'
GROUP BY DATE(t.txn_time);
