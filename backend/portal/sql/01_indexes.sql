-- ===========================================================================
-- 01_indexes.sql  --  indexes the fraud rules depend on
-- ---------------------------------------------------------------------------
-- Every rule in sp_evaluate_transaction looks at ONE account's recent history,
-- so almost every index starts with account_id and ends with a time column:
-- MySQL can then jump straight to "this account, last N minutes" instead of
-- scanning the table. Re-running this file is safe: the loader skips an index
-- that already exists (error 1061).
-- ===========================================================================

-- R1 (90-day average), R2 (10-minute count), R7 (24-hour count)
CREATE INDEX ix_txn_account_time ON transactions (account_id, txn_time);

-- Live monitor, dashboard and alert queue: "latest payments by decision"
CREATE INDEX ix_txn_status_time ON transactions (status, txn_time);

-- R3 (impossible travel): previous payment of the account and its city
CREATE INDEX ix_txn_account_city_time ON transactions (account_id, city, txn_time);

-- Dashboard date ranges
CREATE INDEX ix_txn_time ON transactions (txn_time);

-- R9 / OTP Shield: "risky login or SIM change on this account in the last X minutes"
CREATE INDEX ix_sessions_account_event_time ON sessions (account_id, event_type, created_at);

-- R4 / R9: "has this account seen this device before / is it trusted?"
CREATE UNIQUE INDEX uq_devices_account_device ON devices (account_id, device_id);

-- R9: "payee added in the last 24 hours"
CREATE INDEX ix_beneficiaries_account_added ON beneficiaries (account_id, added_at);

-- R6: watchlist lookups by type + value (also prevents duplicates)
CREATE UNIQUE INDEX uq_watchlist_type_value ON watchlist (entry_type, entry_value);

-- Evidence for one transaction
CREATE INDEX ix_rule_hits_txn ON rule_hits (txn_id);

-- Alert queue tabs
CREATE INDEX ix_alerts_status_created ON alerts (alert_status, created_at);

-- OTP Shield rate limit: "OTP requests for this account in the last 10 minutes"
CREATE INDEX ix_otp_account_created ON otp_requests (account_id, created_at);
