-- ===========================================================================
-- 06_audit_chain.sql  --  tamper-evident audit log
-- ---------------------------------------------------------------------------
--   * every new row is chained to the one before it: row_hash =
--     SHA-256(previous row_hash + the row's content), and audit_chain keeps
--     the newest hash (so removing rows from the end is noticed too);
--   * UPDATE and DELETE on audit_log are refused. (An UPDATE is allowed only
--     to give a row written before the chain existed its hashes, once.)
-- services/audit_chain.py re-computes the chain with fn_audit_hash and
-- reports the first row that no longer matches.
-- ===========================================================================

DROP TRIGGER IF EXISTS trg_audit_log_chain;
DROP TRIGGER IF EXISTS trg_audit_log_no_update;
DROP TRIGGER IF EXISTS trg_audit_log_no_delete;
DROP FUNCTION IF EXISTS fn_audit_hash;

DELIMITER $$

CREATE FUNCTION fn_audit_hash(p_prev CHAR(64), p_actor VARCHAR(64), p_action VARCHAR(32),
                              p_entity VARCHAR(32), p_entity_id VARCHAR(64),
                              p_old JSON, p_new JSON, p_at DATETIME(3)) RETURNS CHAR(64)
DETERMINISTIC NO SQL
BEGIN
    RETURN SHA2(CONCAT_WS('|', COALESCE(p_prev, 'GENESIS'), p_actor, p_action, p_entity,
                          COALESCE(p_entity_id, ''), COALESCE(CAST(p_old AS CHAR), ''),
                          COALESCE(CAST(p_new AS CHAR), ''),
                          DATE_FORMAT(p_at, '%Y-%m-%d %H:%i:%s.%f')), 256);
END$$

CREATE TRIGGER trg_audit_log_chain
BEFORE INSERT ON audit_log
FOR EACH ROW
BEGIN
    DECLARE v_prev CHAR(64) DEFAULT NULL;
    -- Takes an exclusive lock on the chain head, so concurrent inserts are
    -- chained one after the other (released at commit).
    INSERT INTO audit_chain (id, last_hash) VALUES (1, NULL)
        ON DUPLICATE KEY UPDATE id = id;
    SELECT last_hash INTO v_prev FROM audit_chain WHERE id = 1 FOR UPDATE;
    IF NEW.logged_at IS NULL THEN
        SET NEW.logged_at = NOW(3);
    END IF;
    SET NEW.prev_hash = v_prev;
    SET NEW.row_hash = fn_audit_hash(v_prev, NEW.actor, NEW.action, NEW.entity, NEW.entity_id,
                                     NEW.old_value, NEW.new_value, NEW.logged_at);
    UPDATE audit_chain SET last_hash = NEW.row_hash WHERE id = 1;
END$$

CREATE TRIGGER trg_audit_log_no_update
BEFORE UPDATE ON audit_log
FOR EACH ROW
BEGIN
    IF OLD.row_hash IS NOT NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'audit_log is append-only: rows cannot be changed';
    END IF;
END$$

CREATE TRIGGER trg_audit_log_no_delete
BEFORE DELETE ON audit_log
FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'audit_log is append-only: rows cannot be deleted';
END$$

DELIMITER ;
