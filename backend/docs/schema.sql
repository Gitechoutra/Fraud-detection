-- ===========================================================================
-- schema.sql  --  FraudShield tables (MySQL 8, InnoDB)
-- ---------------------------------------------------------------------------
-- Generated from the SQLAlchemy models by `flask export-ddl`; do not edit by
-- hand. Run it in an empty database, then portal/sql/01..06_*.sql for the
-- indexes, views, triggers and stored procedures (the fraud engine).
-- `flask db upgrade` does all of this, plus the shared master data.
-- ===========================================================================

-- audit_chain
CREATE TABLE audit_chain (
	id SMALLINT NOT NULL, 
	last_hash CHAR(64), 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- audit_log
CREATE TABLE audit_log (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	actor VARCHAR(64) NOT NULL, 
	action VARCHAR(32) NOT NULL, 
	entity VARCHAR(32) NOT NULL, 
	entity_id VARCHAR(64), 
	old_value JSON, 
	new_value JSON, 
	logged_at DATETIME(3) NOT NULL, 
	prev_hash CHAR(64), 
	row_hash CHAR(64), 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_audit_logged_at ON audit_log (logged_at);

-- customers
CREATE TABLE customers (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	name VARCHAR(120) NOT NULL, 
	phone VARCHAR(20) NOT NULL, 
	email VARCHAR(120), 
	home_city VARCHAR(64) NOT NULL, 
	kyc_status VARCHAR(16) NOT NULL, 
	created_at DATETIME(3) NOT NULL, 
	typical_amount NUMERIC(14, 2) NOT NULL, 
	active_from_hour SMALLINT NOT NULL, 
	active_to_hour SMALLINT NOT NULL, 
	usual_channels VARCHAR(64) NOT NULL, 
	netbanking_id VARCHAR(64), 
	netbanking_password_hash VARCHAR(128), 
	PRIMARY KEY (id), 
	UNIQUE (netbanking_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- daily_stats
CREATE TABLE daily_stats (
	stat_date DATE NOT NULL, 
	total INTEGER NOT NULL, 
	approved INTEGER NOT NULL, 
	review INTEGER NOT NULL, 
	blocked INTEGER NOT NULL, 
	total_amount NUMERIC(16, 2) NOT NULL, 
	blocked_amount NUMERIC(16, 2) NOT NULL, 
	avg_decision_ms NUMERIC(10, 2), 
	refreshed_at DATETIME(3) NOT NULL, 
	PRIMARY KEY (stat_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- fraud_rules
CREATE TABLE fraud_rules (
	rule_code VARCHAR(4) NOT NULL, 
	name VARCHAR(80) NOT NULL, 
	simple_name VARCHAR(80) NOT NULL, 
	description VARCHAR(500) NOT NULL, 
	simple_explanation VARCHAR(500) NOT NULL, 
	param_1 NUMERIC(14, 2), 
	param_2 NUMERIC(14, 2), 
	param_3 NUMERIC(14, 2), 
	param_4 NUMERIC(14, 2), 
	param_labels JSON, 
	weight SMALLINT NOT NULL, 
	spec_weight SMALLINT, 
	is_active BOOL NOT NULL, 
	sort_order SMALLINT NOT NULL, 
	updated_by VARCHAR(64), 
	updated_at DATETIME(3) NOT NULL, 
	PRIMARY KEY (rule_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- fraudster_users
CREATE TABLE fraudster_users (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	username VARCHAR(64) NOT NULL, 
	password_hash VARCHAR(128) NOT NULL, 
	display_name VARCHAR(120) NOT NULL, 
	base_city VARCHAR(64) NOT NULL, 
	tokens_valid_after DATETIME(3), 
	created_at DATETIME(3) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- merchants
CREATE TABLE merchants (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	name VARCHAR(120) NOT NULL, 
	category VARCHAR(32) NOT NULL, 
	city VARCHAR(64) NOT NULL, 
	risk_level VARCHAR(8) NOT NULL, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- metric_runs
CREATE TABLE metric_runs (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	run_at DATETIME(3) NOT NULL, 
	total INTEGER NOT NULL, 
	tp INTEGER NOT NULL, 
	fp INTEGER NOT NULL, 
	tn INTEGER NOT NULL, 
	fn INTEGER NOT NULL, 
	precision_v NUMERIC(6, 4) NOT NULL, 
	recall_v NUMERIC(6, 4) NOT NULL, 
	f1 NUMERIC(6, 4) NOT NULL, 
	fpr NUMERIC(6, 4) NOT NULL, 
	p50_ms NUMERIC(10, 2) NOT NULL, 
	p95_ms NUMERIC(10, 2) NOT NULL, 
	tps NUMERIC(10, 2) NOT NULL, 
	fraud_ratio NUMERIC(5, 4), 
	mode VARCHAR(16), 
	explainability NUMERIC(6, 4), 
	alert_visible_ms NUMERIC(10, 2), 
	per_rule_json JSON, 
	per_scenario_json JSON, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- roles
CREATE TABLE roles (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	name VARCHAR(32) NOT NULL, 
	description VARCHAR(255), 
	PRIMARY KEY (id), 
	UNIQUE (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- system_settings
CREATE TABLE system_settings (
	setting_key VARCHAR(64) NOT NULL, 
	setting_value VARCHAR(255) NOT NULL, 
	description VARCHAR(255), 
	updated_by VARCHAR(64), 
	updated_at DATETIME(3) NOT NULL, 
	PRIMARY KEY (setting_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- token_blocklist
CREATE TABLE token_blocklist (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	jti VARCHAR(64) NOT NULL, 
	token_type VARCHAR(16) NOT NULL, 
	revoked_at DATETIME(3) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (jti)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- watchlist
CREATE TABLE watchlist (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	entry_type ENUM('IP','DEVICE','ACCOUNT','MERCHANT') NOT NULL, 
	entry_value VARCHAR(128) NOT NULL, 
	reason VARCHAR(255) NOT NULL, 
	added_by VARCHAR(64) NOT NULL, 
	added_at DATETIME(3) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_watchlist_type_value UNIQUE (entry_type, entry_value)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- accounts
CREATE TABLE accounts (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	customer_id INTEGER NOT NULL, 
	account_no VARCHAR(20) NOT NULL, 
	account_type VARCHAR(16) NOT NULL, 
	opened_on DATE NOT NULL, 
	last_txn_at DATETIME(3), 
	status VARCHAR(16) NOT NULL, 
	balance NUMERIC(14, 2) NOT NULL, 
	held_amount NUMERIC(14, 2) NOT NULL DEFAULT '0', 
	step_up_until DATETIME(3), 
	PRIMARY KEY (id), 
	CONSTRAINT ck_accounts_balance_not_negative CHECK (balance >= 0), 
	CONSTRAINT ck_accounts_held_within_balance CHECK (held_amount >= 0 AND held_amount <= balance), 
	FOREIGN KEY(customer_id) REFERENCES customers (id), 
	UNIQUE (account_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_accounts_customer_id ON accounts (customer_id);

-- customer_users
CREATE TABLE customer_users (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	customer_id INTEGER NOT NULL, 
	username VARCHAR(64) NOT NULL, 
	password_hash VARCHAR(128) NOT NULL, 
	is_locked BOOL NOT NULL, 
	failed_logins SMALLINT NOT NULL, 
	card_last4 VARCHAR(4), 
	tokens_valid_after DATETIME(3), 
	created_at DATETIME(3) NOT NULL, 
	last_login_at DATETIME(3), 
	PRIMARY KEY (id), 
	UNIQUE (customer_id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE, 
	UNIQUE (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- notifications
CREATE TABLE notifications (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	customer_id INTEGER NOT NULL, 
	channel ENUM('SMS','APP') NOT NULL, 
	kind VARCHAR(16) NOT NULL, 
	ref_id BIGINT, 
	title VARCHAR(120) NOT NULL, 
	body VARCHAR(500) NOT NULL, 
	created_at DATETIME(3) NOT NULL, 
	read_at DATETIME(3), 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_notifications_customer_created ON notifications (customer_id, created_at);

-- stolen_credentials
CREATE TABLE stolen_credentials (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	fraudster_id INTEGER NOT NULL, 
	customer_id INTEGER NOT NULL, 
	obtained_via ENUM('PHISHING_LINK','OTP_CALL','CARD_SKIMMING','SIM_SWAP') NOT NULL, 
	obtained_at DATETIME(3) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_stolen_fraudster_customer UNIQUE (fraudster_id, customer_id), 
	FOREIGN KEY(fraudster_id) REFERENCES fraudster_users (id) ON DELETE CASCADE, 
	FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_stolen_credentials_customer_id ON stolen_credentials (customer_id);

-- users
CREATE TABLE users (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	username VARCHAR(64) NOT NULL, 
	full_name VARCHAR(120) NOT NULL, 
	password_hash VARCHAR(128) NOT NULL, 
	role_id INTEGER NOT NULL, 
	is_active BOOL NOT NULL, 
	created_at DATETIME(3) NOT NULL, 
	last_login_at DATETIME(3), 
	PRIMARY KEY (id), 
	UNIQUE (username), 
	FOREIGN KEY(role_id) REFERENCES roles (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- beneficiaries
CREATE TABLE beneficiaries (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	account_id INTEGER NOT NULL, 
	payee_name VARCHAR(120) NOT NULL, 
	payee_account_no VARCHAR(20) NOT NULL, 
	payee_ifsc VARCHAR(11) NOT NULL, 
	added_at DATETIME(3) NOT NULL, 
	added_device_id VARCHAR(64), 
	cooling_until DATETIME(3), 
	PRIMARY KEY (id), 
	FOREIGN KEY(account_id) REFERENCES accounts (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_beneficiaries_account_added ON beneficiaries (account_id, added_at);

-- devices
CREATE TABLE devices (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	account_id INTEGER NOT NULL, 
	device_id VARCHAR(64) NOT NULL, 
	device_label VARCHAR(120), 
	first_seen DATETIME(3) NOT NULL, 
	last_seen DATETIME(3) NOT NULL, 
	is_trusted BOOL NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_devices_account_device UNIQUE (account_id, device_id), 
	FOREIGN KEY(account_id) REFERENCES accounts (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- sessions
CREATE TABLE sessions (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	account_id INTEGER NOT NULL, 
	device_id VARCHAR(64), 
	ip_address VARCHAR(45), 
	city VARCHAR(64), 
	event_type ENUM('LOGIN','OTP_REQUEST','OTP_VERIFY','PASSWORD_RESET','SIM_CHANGE','MOBILE_CHANGE') NOT NULL, 
	is_active BOOL NOT NULL, 
	created_at DATETIME(3) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(account_id) REFERENCES accounts (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_sessions_account_event_time ON sessions (account_id, event_type, created_at);

-- otp_requests
CREATE TABLE otp_requests (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	account_id INTEGER NOT NULL, 
	beneficiary_id INTEGER, 
	amount NUMERIC(14, 2) NOT NULL, 
	requesting_device_id VARCHAR(64), 
	ip_address VARCHAR(45), 
	city VARCHAR(64), 
	risk_points SMALLINT NOT NULL, 
	signals_json JSON, 
	decision ENUM('OTP_SENT','OTP_SENT_WITH_WARNING','OTP_BLOCKED_APPROVAL_REQUIRED') NOT NULL, 
	final_status ENUM('PENDING','VERIFIED','EXPIRED','LOCKED','APPROVED','DENIED') NOT NULL, 
	otp_hash VARCHAR(64), 
	attempts SMALLINT NOT NULL, 
	expires_at DATETIME(3), 
	verified_at DATETIME(3), 
	verified_device_id VARCHAR(64), 
	verified_ip VARCHAR(45), 
	txn_id BIGINT, 
	created_at DATETIME(3) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(account_id) REFERENCES accounts (id), 
	FOREIGN KEY(beneficiary_id) REFERENCES beneficiaries (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_otp_account_created ON otp_requests (account_id, created_at);

-- device_approvals
CREATE TABLE device_approvals (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	otp_request_id BIGINT NOT NULL, 
	account_id INTEGER NOT NULL, 
	status ENUM('PENDING','APPROVED','DENIED','EXPIRED') NOT NULL, 
	expires_at DATETIME(3) NOT NULL, 
	created_at DATETIME(3) NOT NULL, 
	responded_at DATETIME(3), 
	responded_device_id VARCHAR(64), 
	PRIMARY KEY (id), 
	FOREIGN KEY(otp_request_id) REFERENCES otp_requests (id) ON DELETE CASCADE, 
	FOREIGN KEY(account_id) REFERENCES accounts (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_device_approvals_account_id ON device_approvals (account_id);

-- transactions
CREATE TABLE transactions (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	external_ref VARCHAR(64) NOT NULL, 
	account_id INTEGER NOT NULL, 
	merchant_id INTEGER, 
	beneficiary_id INTEGER, 
	otp_request_id BIGINT, 
	amount NUMERIC(14, 2) NOT NULL, 
	currency VARCHAR(3) NOT NULL, 
	channel ENUM('CARD','UPI','NETBANKING','ATM') NOT NULL, 
	city VARCHAR(64), 
	device_id VARCHAR(64), 
	ip_address VARCHAR(45), 
	txn_time DATETIME(3) NOT NULL, 
	risk_score SMALLINT NOT NULL, 
	status ENUM('PENDING','APPROVED','REVIEW','BLOCKED') NOT NULL, 
	decision_ms NUMERIC(10, 2), 
	funds_status ENUM('DEBITED','HELD','PAID_AFTER_REVIEW','RELEASED','NOT_MOVED'), 
	stage_timings JSON, 
	model_score SMALLINT, 
	model_points SMALLINT, 
	is_fraud_label BOOL, 
	scenario VARCHAR(16), 
	source VARCHAR(16) NOT NULL, 
	created_at DATETIME(3) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (external_ref), 
	FOREIGN KEY(account_id) REFERENCES accounts (id), 
	FOREIGN KEY(merchant_id) REFERENCES merchants (id), 
	FOREIGN KEY(beneficiary_id) REFERENCES beneficiaries (id), 
	FOREIGN KEY(otp_request_id) REFERENCES otp_requests (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_txn_account_city_time ON transactions (account_id, city, txn_time);
CREATE INDEX ix_txn_account_time ON transactions (account_id, txn_time);
CREATE INDEX ix_txn_status_time ON transactions (status, txn_time);
CREATE INDEX ix_txn_time ON transactions (txn_time);

-- alerts
CREATE TABLE alerts (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	txn_id BIGINT, 
	otp_request_id BIGINT, 
	source VARCHAR(16) NOT NULL, 
	summary VARCHAR(255), 
	risk_score SMALLINT NOT NULL, 
	priority ENUM('MEDIUM','HIGH') NOT NULL, 
	alert_status ENUM('OPEN','IN_PROGRESS','CLOSED') NOT NULL, 
	assigned_to INTEGER, 
	created_at DATETIME(3) NOT NULL, 
	updated_at DATETIME(3) NOT NULL, 
	first_seen_at DATETIME(3), 
	PRIMARY KEY (id), 
	UNIQUE (txn_id), 
	FOREIGN KEY(txn_id) REFERENCES transactions (id) ON DELETE CASCADE, 
	FOREIGN KEY(otp_request_id) REFERENCES otp_requests (id) ON DELETE CASCADE, 
	FOREIGN KEY(assigned_to) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_alerts_status_created ON alerts (alert_status, created_at);

-- attack_events
CREATE TABLE attack_events (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	fraudster_id INTEGER NOT NULL, 
	customer_id INTEGER NOT NULL, 
	txn_id BIGINT, 
	scenario VARCHAR(16) NOT NULL, 
	step VARCHAR(160), 
	created_at DATETIME(3) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(fraudster_id) REFERENCES fraudster_users (id) ON DELETE CASCADE, 
	FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE, 
	UNIQUE (txn_id), 
	FOREIGN KEY(txn_id) REFERENCES transactions (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_attack_events_fraudster ON attack_events (fraudster_id, id);

-- customer_alerts
CREATE TABLE customer_alerts (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	customer_id INTEGER NOT NULL, 
	txn_id BIGINT, 
	severity ENUM('INFO','WARNING','DANGER') NOT NULL, 
	title VARCHAR(160) NOT NULL, 
	body VARCHAR(500) NOT NULL, 
	action_status ENUM('PENDING','CONFIRMED_ME','REPORTED_NOT_ME') NOT NULL, 
	created_at DATETIME(3) NOT NULL, 
	responded_at DATETIME(3), 
	read_at DATETIME(3), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_customer_alerts_txn_severity UNIQUE (txn_id, severity), 
	FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE, 
	FOREIGN KEY(txn_id) REFERENCES transactions (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_customer_alerts_customer_id ON customer_alerts (customer_id, id);

-- rule_hits
CREATE TABLE rule_hits (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	txn_id BIGINT NOT NULL, 
	rule_code VARCHAR(4) NOT NULL, 
	weight_applied SMALLINT NOT NULL, 
	observed_value VARCHAR(64), 
	detail_text VARCHAR(255), 
	hit_at DATETIME(3) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(txn_id) REFERENCES transactions (id) ON DELETE CASCADE, 
	FOREIGN KEY(rule_code) REFERENCES fraud_rules (rule_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_rule_hits_txn ON rule_hits (txn_id);

-- cases
CREATE TABLE cases (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	alert_id BIGINT NOT NULL, 
	analyst_id INTEGER, 
	outcome ENUM('CONFIRMED_FRAUD','FALSE_POSITIVE'), 
	customer_response ENUM('WAITING','CONFIRMED_ME','REPORTED_NOT_ME') NOT NULL DEFAULT 'WAITING', 
	notes TEXT, 
	created_at DATETIME(3) NOT NULL, 
	closed_at DATETIME(3), 
	PRIMARY KEY (id), 
	UNIQUE (alert_id), 
	FOREIGN KEY(alert_id) REFERENCES alerts (id) ON DELETE CASCADE, 
	FOREIGN KEY(analyst_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- case_notes
CREATE TABLE case_notes (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	case_id BIGINT NOT NULL, 
	author_id INTEGER NOT NULL, 
	body TEXT NOT NULL, 
	created_at DATETIME(3) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id) ON DELETE CASCADE, 
	FOREIGN KEY(author_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_case_notes_case_id ON case_notes (case_id);
