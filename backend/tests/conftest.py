"""
Test setup.

The suite runs against the separate DB_TEST_NAME database (fraud_sql_test).
It is dropped and rebuilt once per run -- tables, SQL objects, roles, users,
rules, merchants and watchlist -- and every test starts from that baseline:
dynamic tables are emptied and the rules reset before each test. The main
fraud_sql database is never touched.
"""

import os

os.environ["FLASK_ENV"] = "testing"

import itertools  # noqa: E402
from datetime import date, datetime, timedelta  # noqa: E402

import pymysql  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

from portal import create_app  # noqa: E402
from portal.config import env  # noqa: E402
from portal.extensions import db  # noqa: E402
from portal.helpers.db_helpers import load_sql_objects  # noqa: E402
from portal.models import Account, Beneficiary, Customer, Device, Transaction  # noqa: E402
from portal.seeders import seed_admin, seed_merchants, seed_roles, seed_rules, seed_watchlist  # noqa: E402
from portal.services import fraud_engine  # noqa: E402

DYNAMIC_TABLES = [
    "case_notes", "cases", "alerts", "rule_hits", "device_approvals", "notifications", "transactions",
    "otp_requests", "sessions", "beneficiaries", "devices", "accounts", "customers", "audit_log",
    "token_blocklist", "metric_runs", "daily_stats",
]
_refs = itertools.count(1)


def quiet(*_args, **_kwargs):
    pass


@pytest.fixture(scope="session")
def app():
    app = create_app("testing")
    name = app.config["DB_NAME"]
    assert name.endswith("_test"), "Refusing to run tests against a non-test database"
    conn = pymysql.connect(host=env("DB_HOST", "127.0.0.1"), port=int(env("DB_PORT", "3306")),
                           user=env("DB_USER", "root"), password=env("DB_PASSWORD", ""))
    with conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS `{name}`")
        cur.execute(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    conn.close()
    with app.app_context():
        db.create_all()
        load_sql_objects(log=quiet)
        for seeder in (seed_roles, seed_admin, seed_rules, seed_merchants, seed_watchlist):
            seeder.run(log=quiet)
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture(autouse=True)
def ctx(app):
    with app.app_context():
        _reset()
        yield
        db.session.remove()


def _reset():
    db.session.rollback()
    db.session.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
    for table in DYNAMIC_TABLES:
        db.session.execute(text(f"DELETE FROM `{table}`"))
    db.session.execute(text("DELETE FROM watchlist WHERE added_by <> 'seed'"))
    db.session.execute(text("DELETE FROM users WHERE id > 3"))
    db.session.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    db.session.commit()
    seed_rules.reset_rules()
    db.session.execute(text("DELETE FROM audit_log"))
    db.session.commit()


@pytest.fixture
def client(app):
    return app.test_client()


# --------------------------------------------------------------------------
# Factories
# --------------------------------------------------------------------------

NOON = datetime.combine(date.today() - timedelta(days=1), datetime.min.time()) + timedelta(hours=12)


def make_account(home_city="Hyderabad", avg=2000, history=10, device="DEV-T-1", last_txn_days=None,
                 status="ACTIVE", opened_days=1000):
    """A customer + account + trusted device, with `history` approved payments
    of exactly `avg` on the days before NOON."""
    n = next(_refs)
    customer = Customer(name=f"Test Customer {n}", phone=f"+9190000{n:05d}", home_city=home_city,
                        typical_amount=avg)
    db.session.add(customer)
    db.session.flush()
    account = Account(customer_id=customer.id, account_no=f"9{n:013d}", opened_on=date.today() - timedelta(days=opened_days),
                      status=status, balance=500000)
    db.session.add(account)
    db.session.flush()
    db.session.add(Device(account_id=account.id, device_id=device, device_label="Test phone",
                          first_seen=NOON - timedelta(days=400), last_seen=NOON - timedelta(days=1), is_trusted=True))
    for i in range(history):
        t = NOON - timedelta(days=i + 1)
        db.session.add(Transaction(external_ref=f"HIST-{n}-{i}", account_id=account.id, amount=avg, channel="UPI",
                                   city=home_city, device_id=device, ip_address="49.1.1.1", txn_time=t,
                                   status="APPROVED", source="SEED", created_at=t))
    if last_txn_days is not None:
        account.last_txn_at = NOON - timedelta(days=last_txn_days)
    elif history:
        account.last_txn_at = NOON - timedelta(days=1)
    db.session.commit()
    return account


def make_payee(account, added_ago=timedelta(days=200), name="Old Friend", account_no=None):
    payee = Beneficiary(account_id=account.id, payee_name=name,
                        payee_account_no=account_no or f"5{next(_refs):011d}", payee_ifsc="SBIN0001234",
                        added_at=NOON - added_ago)
    db.session.add(payee)
    db.session.commit()
    return payee


def pay(account, amount, at=NOON, **kwargs):
    payload = {
        "external_ref": kwargs.pop("external_ref", f"T-{next(_refs)}"),
        "account_id": account.id,
        "amount": amount,
        "channel": kwargs.pop("channel", "UPI"),
        "city": kwargs.pop("city", "Hyderabad"),
        "device_id": kwargs.pop("device_id", "DEV-T-1"),
        "ip_address": kwargs.pop("ip_address", "49.1.1.1"),
        "txn_time": at,
    }
    payload.update(kwargs)
    return fraud_engine.ingest(payload, source="TEST")


def fired(result):
    return {h["rule_code"] for h in result["rules"]}


def staff_credentials(who="admin"):
    """(username, password) of the seeded admin / risk / analyst user, from
    .env (the same ones seed_admin used)."""
    role = {"admin": "ADMIN", "risk": "RISK_MANAGER", "analyst": "ANALYST"}[who]
    return next((u, p) for u, p, _, r in seed_admin.default_users() if r == role)


def staff_login(client, who="admin"):
    username, password = staff_credentials(who)
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]


def staff_token(client, who="admin"):
    return staff_login(client, who)["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}
