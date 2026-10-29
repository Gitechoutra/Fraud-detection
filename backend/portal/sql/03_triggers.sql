-- ===========================================================================
-- 03_triggers.sql  --  automatic audit trail
-- ---------------------------------------------------------------------------
-- Changes to rules, the watchlist and case outcomes are recorded by the
-- database itself, so they are captured no matter which code path made them.
-- The app sets the session variable @app_actor to the logged-in username;
-- if it is not set we fall back to the MySQL user.
--
-- The audit log itself is made tamper-evident in 06_audit_chain.sql.
-- ===========================================================================

DROP TRIGGER IF EXISTS trg_fraud_rules_audit_update;
DROP TRIGGER IF EXISTS trg_watchlist_audit_insert;
DROP TRIGGER IF EXISTS trg_watchlist_audit_delete;
DROP TRIGGER IF EXISTS trg_cases_audit_update;

DELIMITER $$

CREATE TRIGGER trg_fraud_rules_audit_update
AFTER UPDATE ON fraud_rules
FOR EACH ROW
BEGIN
    INSERT INTO audit_log (actor, action, entity, entity_id, old_value, new_value, logged_at)
    VALUES (
        COALESCE(NEW.updated_by, @app_actor, CURRENT_USER()),
        'RULE_UPDATED',
        'fraud_rules',
        NEW.rule_code,
        JSON_OBJECT('param_1', OLD.param_1, 'param_2', OLD.param_2, 'param_3', OLD.param_3,
                    'param_4', OLD.param_4, 'weight', OLD.weight, 'is_active', OLD.is_active),
        JSON_OBJECT('param_1', NEW.param_1, 'param_2', NEW.param_2, 'param_3', NEW.param_3,
                    'param_4', NEW.param_4, 'weight', NEW.weight, 'is_active', NEW.is_active),
        NOW(3)
    );
END$$

CREATE TRIGGER trg_watchlist_audit_insert
AFTER INSERT ON watchlist
FOR EACH ROW
BEGIN
    INSERT INTO audit_log (actor, action, entity, entity_id, old_value, new_value, logged_at)
    VALUES (
        COALESCE(@app_actor, NEW.added_by, CURRENT_USER()),
        'WATCHLIST_ADDED',
        'watchlist',
        CAST(NEW.id AS CHAR),
        NULL,
        JSON_OBJECT('entry_type', NEW.entry_type, 'entry_value', NEW.entry_value, 'reason', NEW.reason),
        NOW(3)
    );
END$$

CREATE TRIGGER trg_watchlist_audit_delete
AFTER DELETE ON watchlist
FOR EACH ROW
BEGIN
    INSERT INTO audit_log (actor, action, entity, entity_id, old_value, new_value, logged_at)
    VALUES (
        COALESCE(@app_actor, CURRENT_USER()),
        'WATCHLIST_REMOVED',
        'watchlist',
        CAST(OLD.id AS CHAR),
        JSON_OBJECT('entry_type', OLD.entry_type, 'entry_value', OLD.entry_value, 'reason', OLD.reason),
        NULL,
        NOW(3)
    );
END$$

CREATE TRIGGER trg_cases_audit_update
AFTER UPDATE ON cases
FOR EACH ROW
BEGIN
    INSERT INTO audit_log (actor, action, entity, entity_id, old_value, new_value, logged_at)
    VALUES (
        COALESCE(@app_actor, CURRENT_USER()),
        CASE
            WHEN NEW.outcome IS NOT NULL AND OLD.outcome IS NULL THEN 'CASE_CLOSED'
            WHEN NOT (NEW.customer_response <=> OLD.customer_response) THEN 'CUSTOMER_RESPONDED'
            ELSE 'CASE_UPDATED'
        END,
        'cases',
        CAST(NEW.id AS CHAR),
        JSON_OBJECT('outcome', OLD.outcome, 'analyst_id', OLD.analyst_id, 'closed_at', OLD.closed_at,
                    'customer_response', OLD.customer_response),
        JSON_OBJECT('outcome', NEW.outcome, 'analyst_id', NEW.analyst_id, 'closed_at', NEW.closed_at,
                    'customer_response', NEW.customer_response),
        NOW(3)
    );
END$$

DELIMITER ;
