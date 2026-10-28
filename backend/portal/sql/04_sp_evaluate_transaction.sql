-- ===========================================================================
-- 04_sp_evaluate_transaction.sql  --  THE FRAUD ENGINE (all 9 rules, in SQL)
-- ---------------------------------------------------------------------------
-- CALL sp_evaluate_transaction(<transactions.id>);
--
-- The caller (portal/services/fraud_engine.py) has just INSERTed the payment
-- with status PENDING, and calls this on the SAME connection inside the SAME
-- database transaction, then commits once. So a payment can never exist
-- without its decision and its evidence.
--
-- Steps:
--   1. Load the payment and the decision bands.
--   2. For each active rule R1..R9: read its thresholds and weight from
--      fraud_rules (never hard-coded), test it, and if it fires write one
--      rule_hits row with the observed value and a plain-English sentence.
--   3. Score = LEAST(100, SUM(weight of fired rules)).
--   4. Decide: >= BLOCK_THRESHOLD -> BLOCKED, >= REVIEW_THRESHOLD -> REVIEW,
--      else APPROVED.
--   5. REVIEW/BLOCKED -> alert (HIGH if blocked) + investigation case.
--   6. Only after the rules ran: remember the device and update
--      accounts.last_txn_at (for APPROVED payments only -- a blocked attempt
--      must not "wake up" a dormant account or make a fraudster's phone look
--      familiar the next time).
--   7. Return score, status, per-stage timings and the rule hits (as JSON)
--      as a final SELECT, so the caller needs no extra query.
-- ===========================================================================

DROP FUNCTION IF EXISTS fn_inr;
DROP PROCEDURE IF EXISTS sp_evaluate_transaction;

DELIMITER $$

-- Indian-style rupee formatting for the explanation sentences: ₹1,25,000
CREATE FUNCTION fn_inr(p_amount DECIMAL(16,2)) RETURNS VARCHAR(40)
DETERMINISTIC NO SQL
BEGIN
    RETURN CONCAT('₹', FORMAT(p_amount, 0, 'en_IN'));
END$$

CREATE PROCEDURE sp_evaluate_transaction(IN p_txn_id BIGINT)
proc: BEGIN
    -- The payment being checked
    DECLARE v_account_id    INT;
    DECLARE v_account_no    VARCHAR(20);
    DECLARE v_amount        DECIMAL(14,2);
    DECLARE v_city          VARCHAR(64);
    DECLARE v_device        VARCHAR(64);
    DECLARE v_ip            VARCHAR(45);
    DECLARE v_time          DATETIME(3);
    DECLARE v_merchant      INT;
    DECLARE v_merchant_str  VARCHAR(20);   -- the id as text, in the database's collation
    DECLARE v_merchant_name VARCHAR(120);
    DECLARE v_benef         INT;
    DECLARE v_otp           BIGINT;
    DECLARE v_status        VARCHAR(16);
    DECLARE v_last_txn      DATETIME(3);
    DECLARE v_opened        DATE;
    DECLARE v_payee_acct    VARCHAR(20);
    DECLARE v_payee_name    VARCHAR(120);
    DECLARE v_payee_added   DATETIME(3);

    -- The rule currently being evaluated (loaded from fraud_rules)
    DECLARE r_active TINYINT DEFAULT 0;
    DECLARE r_weight INT DEFAULT 0;
    DECLARE r_p1     DECIMAL(14,2);
    DECLARE r_p2     DECIMAL(14,2);
    DECLARE r_p3     DECIMAL(14,2);
    DECLARE r_p4     DECIMAL(14,2);

    -- Decision bands (system_settings); defaults if the rows are missing
    DECLARE v_review INT DEFAULT 40;
    DECLARE v_block  INT DEFAULT 70;

    -- Working variables
    DECLARE v_score     INT DEFAULT 0;
    DECLARE v_hits      INT DEFAULT 0;
    DECLARE v_avg       DECIMAL(14,2);
    DECLARE v_cnt       INT;
    DECLARE v_prev_city VARCHAR(64);
    DECLARE v_prev_time DATETIME(3);
    DECLARE v_mins      INT;
    DECLARE v_days      INT;
    DECLARE v_obs       VARCHAR(160);
    DECLARE v_txt       VARCHAR(255);
    DECLARE v_event     VARCHAR(32);
    DECLARE v_alert_id  BIGINT DEFAULT NULL;

    -- Stage timings (SYSDATE(6) is the real clock, not the statement start)
    DECLARE t_start  DATETIME(6);
    DECLARE t_rules  DATETIME(6);
    DECLARE t_score  DATETIME(6);
    DECLARE t_decide DATETIME(6);
    DECLARE t_alert  DATETIME(6);

    -- A lookup that finds no row simply leaves its variables unchanged.
    DECLARE CONTINUE HANDLER FOR NOT FOUND BEGIN END;

    SET t_start = SYSDATE(6);

    -- ------------------------------------------------------------------
    -- 1. Load the payment (row-locked so it is evaluated exactly once)
    -- ------------------------------------------------------------------
    SELECT t.account_id, a.account_no, t.amount, t.city, t.device_id, t.ip_address,
           t.txn_time, t.merchant_id, m.name, t.beneficiary_id, t.otp_request_id,
           t.status, a.last_txn_at, a.opened_on,
           b.payee_account_no, b.payee_name, b.added_at
      INTO v_account_id, v_account_no, v_amount, v_city, v_device, v_ip,
           v_time, v_merchant, v_merchant_name, v_benef, v_otp,
           v_status, v_last_txn, v_opened,
           v_payee_acct, v_payee_name, v_payee_added
      FROM transactions t
      JOIN accounts a           ON a.id = t.account_id
      LEFT JOIN merchants m     ON m.id = t.merchant_id
      LEFT JOIN beneficiaries b ON b.id = t.beneficiary_id
     WHERE t.id = p_txn_id
     FOR UPDATE OF t;

    IF v_account_id IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'sp_evaluate_transaction: transaction not found';
    END IF;

    -- Already decided (e.g. a retry): return the existing decision unchanged.
    IF v_status <> 'PENDING' THEN
        SELECT t.risk_score AS risk_score, t.status AS status, al.id AS alert_id,
               (SELECT COUNT(*) FROM rule_hits rh WHERE rh.txn_id = t.id) AS hits,
               0 AS rules_ms, 0 AS score_ms, 0 AS decide_ms, 0 AS alert_ms,
               (SELECT JSON_ARRAYAGG(JSON_OBJECT('rule_code', rh.rule_code, 'weight_applied', rh.weight_applied,
                                                 'observed_value', rh.observed_value, 'detail_text', rh.detail_text))
                  FROM rule_hits rh WHERE rh.txn_id = t.id) AS hits_json
          FROM transactions t
          LEFT JOIN alerts al ON al.txn_id = t.id
         WHERE t.id = p_txn_id;
        LEAVE proc;
    END IF;

    SELECT CAST(setting_value AS SIGNED) INTO v_review
      FROM system_settings WHERE setting_key = 'REVIEW_THRESHOLD';
    SELECT CAST(setting_value AS SIGNED) INTO v_block
      FROM system_settings WHERE setting_key = 'BLOCK_THRESHOLD';

    -- ------------------------------------------------------------------
    -- R1  Unusually large amount
    --     amount > param_1 x the account's average over the last param_3
    --     days, needing at least param_2 earlier approved payments.
    -- ------------------------------------------------------------------
    SET r_active = 0;
    SELECT is_active, weight, param_1, param_2, param_3, param_4
      INTO r_active, r_weight, r_p1, r_p2, r_p3, r_p4
      FROM fraud_rules WHERE rule_code = 'R1';
    IF r_active = 1 THEN
        SET v_avg = NULL, v_cnt = 0;
        SELECT AVG(amount), COUNT(*) INTO v_avg, v_cnt
          FROM transactions
         WHERE account_id = v_account_id
           AND txn_time >= v_time - INTERVAL CAST(r_p3 AS UNSIGNED) DAY
           AND txn_time < v_time
           AND status = 'APPROVED'
           AND id <> p_txn_id;
        IF v_cnt >= r_p2 AND v_avg > 0 AND v_amount > r_p1 * v_avg THEN
            INSERT INTO rule_hits (txn_id, rule_code, weight_applied, observed_value, detail_text, hit_at)
            VALUES (p_txn_id, 'R1', r_weight,
                    CONCAT(ROUND(v_amount / v_avg, 1), 'x usual'),
                    CONCAT(fn_inr(v_amount), ' is ', ROUND(v_amount / v_avg, 1),
                           '× this account''s usual ', fn_inr(v_avg)),
                    v_time);
        END IF;
    END IF;

    -- ------------------------------------------------------------------
    -- R2  Too many payments too fast
    --     more than param_1 payments (including this one) in param_2 minutes.
    -- ------------------------------------------------------------------
    SET r_active = 0;
    SELECT is_active, weight, param_1, param_2, param_3, param_4
      INTO r_active, r_weight, r_p1, r_p2, r_p3, r_p4
      FROM fraud_rules WHERE rule_code = 'R2';
    IF r_active = 1 THEN
        SET v_cnt = 0;
        SELECT COUNT(*) INTO v_cnt
          FROM transactions
         WHERE account_id = v_account_id
           AND txn_time BETWEEN v_time - INTERVAL CAST(r_p2 AS UNSIGNED) MINUTE AND v_time;
        IF v_cnt > r_p1 THEN
            INSERT INTO rule_hits (txn_id, rule_code, weight_applied, observed_value, detail_text, hit_at)
            VALUES (p_txn_id, 'R2', r_weight,
                    CONCAT(v_cnt, ' in ', CAST(r_p2 AS UNSIGNED), ' min'),
                    CONCAT(v_cnt, ' payments in ', CAST(r_p2 AS UNSIGNED),
                           ' minutes — the safe limit is ', CAST(r_p1 AS UNSIGNED)),
                    v_time);
        END IF;
    END IF;

    -- ------------------------------------------------------------------
    -- R3  Impossible travel
    --     LAG() finds the account's previous payment; it fires when that
    --     payment was in a different city less than param_1 minutes ago.
    --     Blocked attempts are ignored, so a stopped fraud attempt elsewhere
    --     doesn't flag the real customer's next payment.
    -- ------------------------------------------------------------------
    SET r_active = 0;
    SELECT is_active, weight, param_1, param_2, param_3, param_4
      INTO r_active, r_weight, r_p1, r_p2, r_p3, r_p4
      FROM fraud_rules WHERE rule_code = 'R3';
    IF r_active = 1 THEN
        SET v_prev_city = NULL, v_prev_time = NULL;
        SELECT x.prev_city, x.prev_time INTO v_prev_city, v_prev_time
          FROM (
                SELECT id,
                       LAG(city)     OVER w AS prev_city,
                       LAG(txn_time) OVER w AS prev_time
                  FROM transactions
                 WHERE account_id = v_account_id
                   AND txn_time BETWEEN v_time - INTERVAL CAST(r_p1 AS UNSIGNED) MINUTE AND v_time
                   AND (status <> 'BLOCKED' OR id = p_txn_id)
                WINDOW w AS (ORDER BY txn_time, id)
               ) x
         WHERE x.id = p_txn_id;
        IF v_prev_city IS NOT NULL AND v_city IS NOT NULL AND v_prev_city <> v_city THEN
            SET v_mins = TIMESTAMPDIFF(MINUTE, v_prev_time, v_time);
            INSERT INTO rule_hits (txn_id, rule_code, weight_applied, observed_value, detail_text, hit_at)
            VALUES (p_txn_id, 'R3', r_weight,
                    LEFT(CONCAT(v_prev_city, ' → ', v_city, ' in ', v_mins, ' min'), 64),
                    LEFT(CONCAT('Used in ', v_prev_city, ' and then in ', v_city, ' just ', v_mins,
                                ' min later — nobody can travel that fast'), 255),
                    v_time);
        END IF;
    END IF;

    -- ------------------------------------------------------------------
    -- R4  New device, big amount
    --     the device has never been seen on this account (checked BEFORE the
    --     device is registered below) and amount > param_1.
    -- ------------------------------------------------------------------
    SET r_active = 0;
    SELECT is_active, weight, param_1, param_2, param_3, param_4
      INTO r_active, r_weight, r_p1, r_p2, r_p3, r_p4
      FROM fraud_rules WHERE rule_code = 'R4';
    IF r_active = 1 AND v_device IS NOT NULL AND v_amount > r_p1 THEN
        IF NOT EXISTS (SELECT 1 FROM devices
                        WHERE account_id = v_account_id AND device_id = v_device) THEN
            INSERT INTO rule_hits (txn_id, rule_code, weight_applied, observed_value, detail_text, hit_at)
            VALUES (p_txn_id, 'R4', r_weight,
                    LEFT(v_device, 64),
                    CONCAT(fn_inr(v_amount), ' from a device never seen on this account (limit for new devices ',
                           fn_inr(r_p1), ')'),
                    v_time);
        END IF;
    END IF;

    -- ------------------------------------------------------------------
    -- R5  Late-night large payment
    --     hour between param_1 (inclusive) and param_2 (exclusive), amount > param_3.
    -- ------------------------------------------------------------------
    SET r_active = 0;
    SELECT is_active, weight, param_1, param_2, param_3, param_4
      INTO r_active, r_weight, r_p1, r_p2, r_p3, r_p4
      FROM fraud_rules WHERE rule_code = 'R5';
    IF r_active = 1 AND HOUR(v_time) >= r_p1 AND HOUR(v_time) < r_p2 AND v_amount > r_p3 THEN
        INSERT INTO rule_hits (txn_id, rule_code, weight_applied, observed_value, detail_text, hit_at)
        VALUES (p_txn_id, 'R5', r_weight,
                DATE_FORMAT(v_time, '%H:%i'),
                CONCAT(fn_inr(v_amount), ' at ', DATE_FORMAT(v_time, '%l:%i %p'),
                       ', in the middle of the night (more than ', fn_inr(r_p3), ')'),
                v_time);
    END IF;

    -- ------------------------------------------------------------------
    -- R6  Known fraudster
    --     the IP, device, merchant, payee account or the account itself is on
    --     the watchlist. Each branch is an index lookup on (type, value).
    -- ------------------------------------------------------------------
    SET r_active = 0;
    SELECT is_active, weight, param_1, param_2, param_3, param_4
      INTO r_active, r_weight, r_p1, r_p2, r_p3, r_p4
      FROM fraud_rules WHERE rule_code = 'R6';
    IF r_active = 1 THEN
        -- (CAST(... AS CHAR) would take the connection's collation and clash
        --  with the table's, so the id is copied into a declared variable.)
        SET v_obs = NULL, v_txt = NULL, v_event = NULL, v_merchant_str = v_merchant;
        SELECT w.entry_type, w.entry_value, w.reason INTO v_event, v_obs, v_txt
          FROM watchlist w
         WHERE (w.entry_type = 'IP'       AND w.entry_value = v_ip)
            OR (w.entry_type = 'DEVICE'   AND w.entry_value = v_device)
            OR (w.entry_type = 'MERCHANT' AND w.entry_value IN (v_merchant_str, v_merchant_name))
            OR (w.entry_type = 'ACCOUNT'  AND w.entry_value IN (v_payee_acct, v_account_no))
         ORDER BY FIELD(w.entry_type, 'DEVICE', 'IP', 'ACCOUNT', 'MERCHANT')
         LIMIT 1;
        IF v_obs IS NOT NULL THEN
            INSERT INTO rule_hits (txn_id, rule_code, weight_applied, observed_value, detail_text, hit_at)
            VALUES (p_txn_id, 'R6', r_weight,
                    LEFT(CONCAT(v_event, ' ', v_obs), 64),
                    LEFT(CONCAT('The ', CASE v_event
                                            WHEN 'IP'      THEN 'internet address'
                                            WHEN 'DEVICE'  THEN 'device'
                                            WHEN 'ACCOUNT' THEN 'account'
                                            ELSE 'shop'
                                        END, ' ', v_obs, ' is on the fraud watchlist: ', v_txt), 255),
                    v_time);
        END IF;
    END IF;

    -- ------------------------------------------------------------------
    -- R7  Splitting money to dodge limits ("structuring")
    --     this payment is between param_2 and param_3, and at least param_1
    --     such payments happened in the last param_4 hours (incl. this one).
    -- ------------------------------------------------------------------
    SET r_active = 0;
    SELECT is_active, weight, param_1, param_2, param_3, param_4
      INTO r_active, r_weight, r_p1, r_p2, r_p3, r_p4
      FROM fraud_rules WHERE rule_code = 'R7';
    IF r_active = 1 AND v_amount BETWEEN r_p2 AND r_p3 THEN
        SET v_cnt = 0;
        SELECT COUNT(*) INTO v_cnt
          FROM transactions
         WHERE account_id = v_account_id
           AND amount BETWEEN r_p2 AND r_p3
           AND txn_time BETWEEN v_time - INTERVAL CAST(r_p4 AS UNSIGNED) HOUR AND v_time;
        IF v_cnt >= r_p1 THEN
            INSERT INTO rule_hits (txn_id, rule_code, weight_applied, observed_value, detail_text, hit_at)
            VALUES (p_txn_id, 'R7', r_weight,
                    CONCAT(v_cnt, ' in ', CAST(r_p4 AS UNSIGNED), ' h'),
                    CONCAT(v_cnt, ' payments between ', fn_inr(r_p2), ' and ', fn_inr(r_p3), ' in ',
                           CAST(r_p4 AS UNSIGNED), ' hours — looks like one big amount split up'),
                    v_time);
        END IF;
    END IF;

    -- ------------------------------------------------------------------
    -- R8  Sleeping account wakes up
    --     no activity for param_1 days (since last payment, or since opening
    --     if it never paid) and amount > param_2.
    -- ------------------------------------------------------------------
    SET r_active = 0;
    SELECT is_active, weight, param_1, param_2, param_3, param_4
      INTO r_active, r_weight, r_p1, r_p2, r_p3, r_p4
      FROM fraud_rules WHERE rule_code = 'R8';
    IF r_active = 1 AND v_amount > r_p2 THEN
        SET v_days = DATEDIFF(v_time, COALESCE(v_last_txn, v_opened));
        IF v_days >= r_p1 THEN
            INSERT INTO rule_hits (txn_id, rule_code, weight_applied, observed_value, detail_text, hit_at)
            VALUES (p_txn_id, 'R8', r_weight,
                    CONCAT(v_days, ' days idle'),
                    CONCAT('No activity for ', v_days, ' days, then suddenly ', fn_inr(v_amount)),
                    v_time);
        END IF;
    END IF;

    -- ------------------------------------------------------------------
    -- R9  OTP / phishing-link fraud (OTP Shield safety net, "R9-B")
    --     payee added less than param_1 hours ago, amount >= param_3, AND
    --       (a) the OTP for this payment was typed on a device that is not
    --           one of the customer's trusted devices, OR
    --       (b) within param_2 minutes before the payment there was a login
    --           from an untrusted device, a SIM change, a password reset or
    --           a mobile-number change.
    -- ------------------------------------------------------------------
    SET r_active = 0;
    SELECT is_active, weight, param_1, param_2, param_3, param_4
      INTO r_active, r_weight, r_p1, r_p2, r_p3, r_p4
      FROM fraud_rules WHERE rule_code = 'R9';
    IF r_active = 1 AND v_benef IS NOT NULL AND v_payee_added IS NOT NULL AND v_amount >= r_p3
       AND v_payee_added BETWEEN v_time - INTERVAL CAST(r_p1 AS UNSIGNED) HOUR AND v_time THEN

        SET v_obs = NULL, v_txt = NULL, v_event = NULL, v_mins = NULL;

        IF v_otp IS NOT NULL THEN
            SELECT o.verified_device_id INTO v_obs
              FROM otp_requests o
             WHERE o.id = v_otp
               AND o.verified_device_id IS NOT NULL
               AND NOT EXISTS (SELECT 1 FROM devices d
                                WHERE d.account_id = v_account_id
                                  AND d.device_id = o.verified_device_id
                                  AND d.is_trusted = 1);
            IF v_obs IS NOT NULL THEN
                SET v_txt = 'the OTP was typed on a device the customer has never trusted';
            END IF;
        END IF;

        IF v_txt IS NULL THEN
            SELECT s.event_type, TIMESTAMPDIFF(MINUTE, s.created_at, v_time) INTO v_event, v_mins
              FROM sessions s
             WHERE s.account_id = v_account_id
               AND s.created_at BETWEEN v_time - INTERVAL CAST(r_p2 AS UNSIGNED) MINUTE AND v_time
               AND (   s.event_type IN ('SIM_CHANGE', 'PASSWORD_RESET', 'MOBILE_CHANGE')
                    OR (s.event_type = 'LOGIN'
                        AND NOT EXISTS (SELECT 1 FROM devices d
                                         WHERE d.account_id = v_account_id
                                           AND d.device_id = s.device_id
                                           AND d.is_trusted = 1)))
             ORDER BY s.created_at DESC
             LIMIT 1;
            IF v_event IS NOT NULL THEN
                SET v_obs = v_event;
                SET v_txt = CONCAT(CASE v_event
                                       WHEN 'LOGIN'          THEN 'a login from a new device'
                                       WHEN 'SIM_CHANGE'     THEN 'a SIM card change'
                                       WHEN 'PASSWORD_RESET' THEN 'a password reset'
                                       ELSE 'a mobile number change'
                                   END, ' ', v_mins, ' min earlier');
            END IF;
        END IF;

        IF v_txt IS NOT NULL THEN
            INSERT INTO rule_hits (txn_id, rule_code, weight_applied, observed_value, detail_text, hit_at)
            VALUES (p_txn_id, 'R9', r_weight,
                    LEFT(v_obs, 64),
                    LEFT(CONCAT('New payee ', v_payee_name, ' (added ',
                                TIMESTAMPDIFF(MINUTE, v_payee_added, v_time), ' min ago) was sent ',
                                fn_inr(v_amount), ' right after ', v_txt), 255),
                    v_time);
        END IF;
    END IF;

    SET t_rules = SYSDATE(6);

    -- ------------------------------------------------------------------
    -- 3. Score
    -- ------------------------------------------------------------------
    SELECT COALESCE(SUM(weight_applied), 0), COUNT(*) INTO v_score, v_hits
      FROM rule_hits WHERE txn_id = p_txn_id;
    SET v_score = LEAST(100, v_score);
    SET t_score = SYSDATE(6);

    -- ------------------------------------------------------------------
    -- 4. Decide
    -- ------------------------------------------------------------------
    SET v_status = CASE
                       WHEN v_score >= v_block  THEN 'BLOCKED'
                       WHEN v_score >= v_review THEN 'REVIEW'
                       ELSE 'APPROVED'
                   END;
    UPDATE transactions SET risk_score = v_score, status = v_status WHERE id = p_txn_id;
    SET t_decide = SYSDATE(6);

    -- ------------------------------------------------------------------
    -- 5. Alert + case for anything held or blocked
    -- ------------------------------------------------------------------
    IF v_status <> 'APPROVED' THEN
        INSERT INTO alerts (txn_id, source, summary, risk_score, priority, alert_status, created_at, updated_at)
        VALUES (p_txn_id, 'TRANSACTION',
                LEFT(CONCAT(IF(v_status = 'BLOCKED', 'Blocked ', 'Held '), fn_inr(v_amount), ' — ',
                            v_hits, ' warning sign', IF(v_hits = 1, '', 's')), 255),
                v_score, IF(v_status = 'BLOCKED', 'HIGH', 'MEDIUM'), 'OPEN', NOW(3), NOW(3));
        SET v_alert_id = LAST_INSERT_ID();
        INSERT INTO cases (alert_id, created_at) VALUES (v_alert_id, NOW(3));
    END IF;

    -- ------------------------------------------------------------------
    -- 6. Remember the device and the activity (after the rules ran)
    -- ------------------------------------------------------------------
    IF v_device IS NOT NULL THEN
        IF v_status = 'APPROVED' THEN
            INSERT INTO devices (account_id, device_id, device_label, first_seen, last_seen, is_trusted)
            VALUES (v_account_id, v_device, 'First seen in a payment', v_time, v_time, 0)
            ON DUPLICATE KEY UPDATE last_seen = GREATEST(last_seen, v_time);
        ELSE
            UPDATE devices SET last_seen = GREATEST(last_seen, v_time)
             WHERE account_id = v_account_id AND device_id = v_device;
        END IF;
    END IF;

    IF v_status = 'APPROVED' THEN
        UPDATE accounts
           SET last_txn_at = IF(last_txn_at IS NULL OR last_txn_at < v_time, v_time, last_txn_at),
               status      = IF(status = 'DORMANT', 'ACTIVE', status)
         WHERE id = v_account_id;
    END IF;

    SET t_alert = SYSDATE(6);

    -- ------------------------------------------------------------------
    -- 7. Result
    -- ------------------------------------------------------------------
    SELECT v_score    AS risk_score,
           v_status   AS status,
           v_alert_id AS alert_id,
           v_hits     AS hits,
           ROUND(TIMESTAMPDIFF(MICROSECOND, t_start,  t_rules)  / 1000, 3) AS rules_ms,
           ROUND(TIMESTAMPDIFF(MICROSECOND, t_rules,  t_score)  / 1000, 3) AS score_ms,
           ROUND(TIMESTAMPDIFF(MICROSECOND, t_score,  t_decide) / 1000, 3) AS decide_ms,
           ROUND(TIMESTAMPDIFF(MICROSECOND, t_decide, t_alert)  / 1000, 3) AS alert_ms,
           (SELECT JSON_ARRAYAGG(JSON_OBJECT('rule_code', rh.rule_code, 'weight_applied', rh.weight_applied,
                                             'observed_value', rh.observed_value, 'detail_text', rh.detail_text))
              FROM rule_hits rh WHERE rh.txn_id = p_txn_id) AS hits_json;
END$$

DELIMITER ;
