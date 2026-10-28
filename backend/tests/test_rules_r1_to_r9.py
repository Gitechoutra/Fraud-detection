"""Each rule R1-R9: one test where it fires, and tests where it must not.

Every check goes through the real stored procedure via fraud_engine.ingest.
"""

from datetime import timedelta

from sqlalchemy import text

from portal.extensions import db
from portal.models import Device, FraudRule, SessionEvent, WatchlistEntry
from tests.conftest import NOON, fired, make_account, make_payee, pay


# R1 -- unusually large amount ---------------------------------------------

def test_r1_fires_when_amount_far_above_average():
    acc = make_account(avg=2000, history=10)
    result = pay(acc, 15000)
    assert "R1" in fired(result)
    hit = next(h for h in result["rules"] if h["rule_code"] == "R1")
    assert "7.5" in hit["observed_value"]
    assert "₹15,000" in hit["detail_text"] and "₹2,000" in hit["detail_text"]


def test_r1_does_not_fire_for_normal_amount():
    acc = make_account(avg=2000, history=10)
    assert "R1" not in fired(pay(acc, 8000))


def test_r1_needs_enough_history():
    acc = make_account(avg=2000, history=2)
    assert "R1" not in fired(pay(acc, 50000))


# R2 -- too many payments too fast -----------------------------------------

def test_r2_fires_on_sixth_payment_in_ten_minutes():
    acc = make_account()
    results = [pay(acc, 200, at=NOON + timedelta(minutes=i)) for i in range(6)]
    assert all("R2" not in fired(r) for r in results[:5])
    assert "R2" in fired(results[5])


def test_r2_does_not_fire_when_spread_out():
    acc = make_account()
    results = [pay(acc, 200, at=NOON + timedelta(minutes=3 * i)) for i in range(6)]
    assert all("R2" not in fired(r) for r in results)


# R3 -- impossible travel --------------------------------------------------

def test_r3_fires_for_far_city_minutes_later():
    acc = make_account()
    pay(acc, 500, at=NOON, city="Hyderabad")
    result = pay(acc, 500, at=NOON + timedelta(minutes=12), city="Mumbai")
    assert "R3" in fired(result)
    hit = next(h for h in result["rules"] if h["rule_code"] == "R3")
    assert "Hyderabad" in hit["detail_text"] and "Mumbai" in hit["detail_text"]


def test_r3_does_not_fire_after_enough_time():
    acc = make_account()
    pay(acc, 500, at=NOON, city="Hyderabad")
    assert "R3" not in fired(pay(acc, 500, at=NOON + timedelta(minutes=45), city="Mumbai"))


def test_r3_does_not_fire_in_same_city():
    acc = make_account()
    pay(acc, 500, at=NOON)
    assert "R3" not in fired(pay(acc, 500, at=NOON + timedelta(minutes=5)))


def test_r3_ignores_blocked_attempts():
    acc = make_account()
    db.session.add(WatchlistEntry(entry_type="IP", entry_value="6.6.6.6", reason="test", added_by="test"))
    db.session.commit()
    db.session.get(FraudRule, "R6").weight = 80
    db.session.commit()
    blocked = pay(acc, 500, at=NOON, city="Delhi", ip_address="6.6.6.6")
    assert blocked["status"] == "BLOCKED"
    assert "R3" not in fired(pay(acc, 500, at=NOON + timedelta(minutes=5), city="Hyderabad"))


# R4 -- new device, big amount ---------------------------------------------

def test_r4_fires_for_unknown_device_and_big_amount():
    acc = make_account(avg=20000)
    assert "R4" in fired(pay(acc, 30000, device_id="NEW-PHONE"))


def test_r4_does_not_fire_for_known_device():
    acc = make_account(avg=20000)
    assert "R4" not in fired(pay(acc, 30000, device_id="DEV-T-1"))


def test_r4_does_not_fire_for_small_amount():
    acc = make_account(avg=20000)
    assert "R4" not in fired(pay(acc, 20000, device_id="NEW-PHONE"))


def test_device_is_registered_only_after_an_approved_payment():
    acc = make_account(avg=20000)
    pay(acc, 1000, device_id="PHONE-B")
    assert Device.query.filter_by(account_id=acc.id, device_id="PHONE-B").first() is not None
    # Now known, so a big payment from it no longer counts as "new device".
    assert "R4" not in fired(pay(acc, 30000, device_id="PHONE-B", at=NOON + timedelta(hours=1)))


# R5 -- late-night large payment -------------------------------------------

def test_r5_fires_at_night_for_large_amount():
    acc = make_account(avg=5000)
    night = NOON.replace(hour=2, minute=30)
    result = pay(acc, 15000, at=night)
    assert "R5" in fired(result)


def test_r5_does_not_fire_in_daytime():
    acc = make_account(avg=5000)
    assert "R5" not in fired(pay(acc, 15000, at=NOON))


def test_r5_does_not_fire_for_small_night_payment():
    acc = make_account(avg=5000)
    assert "R5" not in fired(pay(acc, 5000, at=NOON.replace(hour=2)))


# R6 -- known fraudster ----------------------------------------------------

def test_r6_fires_for_watchlisted_ip():
    acc = make_account()
    result = pay(acc, 500, ip_address="185.220.101.4")  # seeded watchlist IP
    assert "R6" in fired(result)
    assert "watchlist" in result["rules"][0]["detail_text"]


def test_r6_fires_for_watchlisted_payee_account():
    acc = make_account()
    payee = make_payee(acc, account_no="99887766554433")  # seeded mule account
    assert "R6" in fired(pay(acc, 500, beneficiary_id=payee.id, channel="NETBANKING"))


def test_r6_fires_for_watchlisted_device():
    acc = make_account()
    assert "R6" in fired(pay(acc, 500, device_id="DEV-STOLEN-0001"))


def test_r6_does_not_fire_for_clean_payment():
    acc = make_account()
    assert "R6" not in fired(pay(acc, 500))


# R7 -- structuring --------------------------------------------------------

def test_r7_fires_on_third_payment_just_under_50k():
    acc = make_account(avg=20000)
    results = [pay(acc, 46000 + i, at=NOON + timedelta(hours=i * 3)) for i in range(3)]
    assert "R7" not in fired(results[1])
    assert "R7" in fired(results[2])


def test_r7_does_not_fire_when_spread_over_more_than_a_day():
    acc = make_account(avg=20000)
    results = [pay(acc, 46000, at=NOON + timedelta(hours=i * 15)) for i in range(3)]
    assert "R7" not in fired(results[2])


def test_r7_does_not_fire_for_amounts_outside_band():
    acc = make_account(avg=20000)
    results = [pay(acc, 40000, at=NOON + timedelta(hours=i)) for i in range(3)]
    assert "R7" not in fired(results[2])


# R8 -- sleeping account wakes up -----------------------------------------

def test_r8_fires_for_dormant_account_large_amount():
    acc = make_account(history=0, last_txn_days=200, status="DORMANT")
    result = pay(acc, 25000)
    assert "R8" in fired(result)
    assert "200 days" in result["rules"][0]["detail_text"]


def test_r8_does_not_fire_for_small_amount():
    acc = make_account(history=0, last_txn_days=200, status="DORMANT")
    assert "R8" not in fired(pay(acc, 10000))


def test_r8_does_not_fire_for_active_account():
    acc = make_account(avg=10000, history=10)
    assert "R8" not in fired(pay(acc, 25000))


def test_r8_uses_opening_date_when_account_never_paid():
    acc = make_account(history=0, opened_days=400)
    assert "R8" in fired(pay(acc, 25000))


# R9 -- OTP / phishing pattern (payment-time safety net) ------------------

def _risky_login(acc, minutes_before=5, device="SCAM-PHONE", event="LOGIN"):
    db.session.add(SessionEvent(account_id=acc.id, device_id=device, ip_address="103.1.1.1", city="Delhi",
                                event_type=event, created_at=NOON - timedelta(minutes=minutes_before)))
    db.session.commit()


def test_r9_fires_after_new_device_login_and_new_payee():
    acc = make_account(avg=5000)
    _risky_login(acc)
    payee = make_payee(acc, added_ago=timedelta(minutes=3), name="Kumar")
    result = pay(acc, 15000, beneficiary_id=payee.id, device_id="SCAM-PHONE", channel="NETBANKING")
    assert "R9" in fired(result)
    hit = next(h for h in result["rules"] if h["rule_code"] == "R9")
    assert "Kumar" in hit["detail_text"] and "new device" in hit["detail_text"]


def test_r9_fires_after_sim_change():
    acc = make_account(avg=5000)
    _risky_login(acc, event="SIM_CHANGE", device="DEV-T-1")
    payee = make_payee(acc, added_ago=timedelta(hours=2))
    assert "R9" in fired(pay(acc, 12000, beneficiary_id=payee.id, channel="NETBANKING"))


def test_r9_fires_when_otp_typed_on_untrusted_device():
    acc = make_account(avg=5000)
    payee = make_payee(acc, added_ago=timedelta(hours=1))
    db.session.execute(text(
        "INSERT INTO otp_requests (id, account_id, beneficiary_id, amount, requesting_device_id, risk_points, "
        "decision, final_status, attempts, verified_at, verified_device_id, created_at) "
        "VALUES (777, :a, :b, 12000, 'DEV-T-1', 25, 'OTP_SENT_WITH_WARNING', 'VERIFIED', 1, :t, 'OTHER-PHONE', :t)"
    ), {"a": acc.id, "b": payee.id, "t": NOON - timedelta(minutes=1)})
    db.session.commit()
    assert "R9" in fired(pay(acc, 12000, beneficiary_id=payee.id, otp_request_id=777, channel="NETBANKING"))


def test_r9_does_not_fire_for_login_from_trusted_device():
    acc = make_account(avg=5000)
    _risky_login(acc, device="DEV-T-1")
    payee = make_payee(acc, added_ago=timedelta(minutes=3))
    assert "R9" not in fired(pay(acc, 15000, beneficiary_id=payee.id, channel="NETBANKING"))


def test_r9_does_not_fire_for_old_payee():
    acc = make_account(avg=5000)
    _risky_login(acc)
    payee = make_payee(acc, added_ago=timedelta(days=30))
    assert "R9" not in fired(pay(acc, 15000, beneficiary_id=payee.id, channel="NETBANKING"))


def test_r9_does_not_fire_for_small_amount():
    acc = make_account(avg=5000)
    _risky_login(acc)
    payee = make_payee(acc, added_ago=timedelta(minutes=3))
    assert "R9" not in fired(pay(acc, 5000, beneficiary_id=payee.id, channel="NETBANKING"))


# Thresholds come from fraud_rules, not code ------------------------------

def test_disabled_rule_does_not_fire():
    acc = make_account(avg=2000, history=10)
    db.session.get(FraudRule, "R1").is_active = False
    db.session.commit()
    assert "R1" not in fired(pay(acc, 15000))


def test_changed_threshold_applies_immediately():
    acc = make_account()
    rule = db.session.get(FraudRule, "R2")
    rule.param_1 = 2  # more than 2 payments in 10 minutes
    db.session.commit()
    results = [pay(acc, 100, at=NOON + timedelta(minutes=i)) for i in range(3)]
    assert "R2" in fired(results[2])
