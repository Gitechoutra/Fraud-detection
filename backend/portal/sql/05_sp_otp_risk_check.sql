-- ===========================================================================
-- 05_sp_otp_risk_check.sql  --  OTP SHIELD, checkpoint R9-A
-- ---------------------------------------------------------------------------
-- CALL sp_otp_risk_check(account_id, beneficiary_id, amount, device_id, ip, city, at);
--
-- Runs BEFORE any OTP is generated. Adds up risk points from who is asking:
--
--   Requesting device is not a trusted device of this account          +15
--   Payee was added less than R9.param_1 (24) hours ago                 +15
--   Within R9.param_2 (15) minutes of a LOGIN from an untrusted device  +10
--   New IP address, or a city different from the customer's home city   +5
--   PASSWORD_RESET / SIM_CHANGE / MOBILE_CHANGE in the last 48 hours    +10
--   Amount > 3 x the account's 90-day average                           +10
--   Device, IP or payee account on the watchlist                        +40
--
-- Decision:  0-19 OTP_SENT  |  20-39 OTP_SENT_WITH_WARNING
--            40+  OTP_BLOCKED_APPROVAL_REQUIRED (no OTP is generated at all)
--
-- Returns one row: risk_points, signals (JSON array explaining each point),
-- decision. The caller stores it in otp_requests.
-- ===========================================================================

DROP PROCEDURE IF EXISTS sp_otp_risk_check;

DELIMITER $$

CREATE PROCEDURE sp_otp_risk_check(
    IN p_account_id     INT,
    IN p_beneficiary_id INT,
    IN p_amount         DECIMAL(14,2),
    IN p_device_id      VARCHAR(64),
    IN p_ip             VARCHAR(45),
    IN p_city           VARCHAR(64),
    IN p_at             DATETIME(3)
)
BEGIN
    DECLARE v_points      INT DEFAULT 0;
    DECLARE v_signals     JSON;
    DECLARE v_home        VARCHAR(64);
    DECLARE v_payee_added DATETIME(3);
    DECLARE v_payee_acct  VARCHAR(20);
    DECLARE v_payee_name  VARCHAR(120);
    DECLARE v_payee_hours INT DEFAULT 24;
    DECLARE v_login_mins  INT DEFAULT 15;
    DECLARE v_avg         DECIMAL(14,2);
    DECLARE v_mins        INT;
    DECLARE v_obs         VARCHAR(160);

    DECLARE CONTINUE HANDLER FOR NOT FOUND BEGIN END;

    SET v_signals = JSON_ARRAY();

    -- Windows come from rule R9, so one change in the Rules page applies to
    -- both OTP Shield checkpoints.
    SELECT CAST(param_1 AS UNSIGNED), CAST(param_2 AS UNSIGNED)
      INTO v_payee_hours, v_login_mins
      FROM fraud_rules WHERE rule_code = 'R9';

    SELECT c.home_city INTO v_home
      FROM accounts a JOIN customers c ON c.id = a.customer_id
     WHERE a.id = p_account_id;

    SELECT added_at, payee_account_no, payee_name INTO v_payee_added, v_payee_acct, v_payee_name
      FROM beneficiaries
     WHERE id = p_beneficiary_id AND account_id = p_account_id;

    -- 1. Untrusted device (+15)
    IF p_device_id IS NULL OR NOT EXISTS (
           SELECT 1 FROM devices
            WHERE account_id = p_account_id AND device_id = p_device_id AND is_trusted = 1) THEN
        SET v_points = v_points + 15;
        SET v_signals = JSON_ARRAY_APPEND(v_signals, '$', JSON_OBJECT(
            'code', 'UNTRUSTED_DEVICE', 'points', 15,
            'text', 'This phone or computer is not one of the customer''s trusted devices'));
    END IF;

    -- 2. New payee (+15)
    IF v_payee_added IS NOT NULL
       AND v_payee_added >= p_at - INTERVAL v_payee_hours HOUR THEN
        SET v_mins = GREATEST(0, TIMESTAMPDIFF(MINUTE, v_payee_added, p_at));
        SET v_points = v_points + 15;
        SET v_signals = JSON_ARRAY_APPEND(v_signals, '$', JSON_OBJECT(
            'code', 'NEW_PAYEE', 'points', 15,
            'text', CONCAT('The payee ', v_payee_name, ' was added only ', v_mins, ' min ago')));
    END IF;

    -- 3. Login from an untrusted device just before (+10)
    SET v_mins = NULL;
    SELECT TIMESTAMPDIFF(MINUTE, s.created_at, p_at) INTO v_mins
      FROM sessions s
     WHERE s.account_id = p_account_id
       AND s.event_type = 'LOGIN'
       AND s.created_at BETWEEN p_at - INTERVAL v_login_mins MINUTE AND p_at
       AND NOT EXISTS (SELECT 1 FROM devices d
                        WHERE d.account_id = p_account_id
                          AND d.device_id = s.device_id
                          AND d.is_trusted = 1)
     ORDER BY s.created_at DESC
     LIMIT 1;
    IF v_mins IS NOT NULL THEN
        SET v_points = v_points + 10;
        SET v_signals = JSON_ARRAY_APPEND(v_signals, '$', JSON_OBJECT(
            'code', 'NEW_DEVICE_LOGIN', 'points', 10,
            'text', CONCAT('Someone logged in from a new device ', v_mins, ' min ago')));
    END IF;

    -- 4. Away from home city, or an internet address never used before (+5)
    IF p_city IS NOT NULL AND v_home IS NOT NULL AND p_city <> v_home THEN
        SET v_points = v_points + 5;
        SET v_signals = JSON_ARRAY_APPEND(v_signals, '$', JSON_OBJECT(
            'code', 'NEW_LOCATION', 'points', 5,
            'text', CONCAT('The request comes from ', p_city, ', but the customer lives in ', v_home)));
    ELSEIF p_ip IS NOT NULL AND NOT EXISTS (
           SELECT 1 FROM transactions
            WHERE account_id = p_account_id AND ip_address = p_ip AND status = 'APPROVED') THEN
        SET v_points = v_points + 5;
        SET v_signals = JSON_ARRAY_APPEND(v_signals, '$', JSON_OBJECT(
            'code', 'NEW_LOCATION', 'points', 5,
            'text', 'The request comes from an internet address this customer never used'));
    END IF;

    -- 5. Recent security change (+10)
    SET v_obs = NULL;
    SELECT event_type INTO v_obs
      FROM sessions
     WHERE account_id = p_account_id
       AND event_type IN ('PASSWORD_RESET', 'SIM_CHANGE', 'MOBILE_CHANGE')
       AND created_at BETWEEN p_at - INTERVAL 48 HOUR AND p_at
     ORDER BY created_at DESC
     LIMIT 1;
    IF v_obs IS NOT NULL THEN
        SET v_points = v_points + 10;
        SET v_signals = JSON_ARRAY_APPEND(v_signals, '$', JSON_OBJECT(
            'code', 'SECURITY_CHANGE', 'points', 10,
            'text', CONCAT(CASE v_obs
                               WHEN 'SIM_CHANGE'     THEN 'The SIM card was changed'
                               WHEN 'PASSWORD_RESET' THEN 'The password was reset'
                               ELSE 'The mobile number was changed'
                           END, ' in the last 48 hours')));
    END IF;

    -- 6. Much bigger than usual (+10)
    SET v_avg = NULL;
    SELECT AVG(amount) INTO v_avg
      FROM transactions
     WHERE account_id = p_account_id
       AND status = 'APPROVED'
       AND txn_time >= p_at - INTERVAL 90 DAY
       AND txn_time < p_at;
    IF v_avg IS NOT NULL AND v_avg > 0 AND p_amount > 3 * v_avg THEN
        SET v_points = v_points + 10;
        SET v_signals = JSON_ARRAY_APPEND(v_signals, '$', JSON_OBJECT(
            'code', 'LARGE_AMOUNT', 'points', 10,
            'text', CONCAT(fn_inr(p_amount), ' is ', ROUND(p_amount / v_avg, 1),
                           '× the usual ', fn_inr(v_avg))));
    END IF;

    -- 7. Watchlist (+40)
    SET v_obs = NULL;
    SELECT CONCAT(LOWER(entry_type), ' ', entry_value) INTO v_obs
      FROM watchlist
     WHERE (entry_type = 'IP'      AND entry_value = p_ip)
        OR (entry_type = 'DEVICE'  AND entry_value = p_device_id)
        OR (entry_type = 'ACCOUNT' AND entry_value = v_payee_acct)
     LIMIT 1;
    IF v_obs IS NOT NULL THEN
        SET v_points = v_points + 40;
        SET v_signals = JSON_ARRAY_APPEND(v_signals, '$', JSON_OBJECT(
            'code', 'WATCHLIST', 'points', 40,
            'text', CONCAT('The ', v_obs, ' is on the fraud watchlist')));
    END IF;

    SELECT v_points  AS risk_points,
           v_signals AS signals,
           CASE
               WHEN v_points >= 40 THEN 'OTP_BLOCKED_APPROVAL_REQUIRED'
               WHEN v_points >= 20 THEN 'OTP_SENT_WITH_WARNING'
               ELSE 'OTP_SENT'
           END       AS decision;
END$$

DELIMITER ;
