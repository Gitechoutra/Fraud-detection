"""
The nine fraud rules with their default thresholds and weights, plus the
decision bands. Inserted only if missing, so tuning done in the Rules page
survives a re-seed. `reset_rules()` restores these defaults (used by tests).

Weights were tuned from the specification's starting values
(R1 30, R2 25, R3 35, R4 20, R5 10, R6 50, R7 15, R8 20, R9 45): with those, a
fraud that trips a single rule stayed below the 40-point hold line and
evaluation recall was 34%. Thresholds were not changed. See docs/RULES.md.
"""


from datetime import datetime

from portal.extensions import db
from portal.models import FraudRule, SystemSetting

RULES = [
    {
        "rule_code": "R1",
        "name": "Amount spike vs 90-day average",
        "simple_name": "Unusually large amount",
        "description": "Amount greater than param_1 x the account's average approved amount over the last "
                       "param_3 days, when the account has at least param_2 earlier payments.",
        "simple_explanation": "The payment is many times bigger than what this person usually spends.",
        "params": [5, 3, 90, None],
        "param_labels": ["Times bigger than usual", "Past payments needed", "Look-back days"],
        "weight": 40,
    },
    {
        "rule_code": "R2",
        "name": "Velocity (count in sliding window)",
        "simple_name": "Too many payments too fast",
        "description": "More than param_1 payments from the account within param_2 minutes, including this one.",
        "simple_explanation": "Lots of payments in a few minutes is how fraudsters test or drain stolen cards.",
        "params": [5, 10, None, None],
        "param_labels": ["Max payments allowed", "Within minutes"],
        "weight": 40,
    },
    {
        "rule_code": "R3",
        "name": "Geo-velocity (impossible travel)",
        "simple_name": "Impossible travel",
        "description": "Previous payment (LAG window function) was in a different city less than param_1 minutes ago.",
        "simple_explanation": "Nobody can be in two far-apart cities within minutes, so the card details may be stolen.",
        "params": [30, None, None, None],
        "param_labels": ["Minutes between cities"],
        "weight": 45,
    },
    {
        "rule_code": "R4",
        "name": "Unseen device with high amount",
        "simple_name": "New device, big amount",
        "description": "Device never seen on this account and amount greater than param_1.",
        "simple_explanation": "A big payment from a phone or computer the customer has never used before.",
        "params": [25000, None, None, None],
        "param_labels": ["Amount above (₹)"],
        "weight": 40,
    },
    {
        "rule_code": "R5",
        "name": "Odd-hour high amount",
        "simple_name": "Late-night large payment",
        "description": "Payment hour between param_1 and param_2 and amount greater than param_3.",
        "simple_explanation": "Large payments in the middle of the night are often made while the owner sleeps.",
        "params": [0, 5, 10000, None],
        "param_labels": ["From hour", "To hour", "Amount above (₹)"],
        "weight": 40,
    },
    {
        "rule_code": "R6",
        "name": "Watchlist match",
        "simple_name": "Known fraudster",
        "description": "IP address, device, merchant, payee account or the account itself is on the watchlist.",
        "simple_explanation": "Something in the payment was already reported for fraud.",
        "params": [None, None, None, None],
        "param_labels": [],
        "weight": 70,
    },
    {
        "rule_code": "R7",
        "name": "Structuring below reporting limit",
        "simple_name": "Splitting money to dodge limits",
        "description": "At least param_1 payments between param_2 and param_3 within param_4 hours, this one included.",
        "simple_explanation": "Breaking a big amount into pieces just under ₹50,000 to avoid extra checks.",
        "params": [3, 45000, 49999, 24],
        "param_labels": ["Number of payments", "From amount (₹)", "To amount (₹)", "Within hours"],
        "weight": 40,
    },
    {
        "rule_code": "R8",
        "name": "Dormant account reactivation",
        "simple_name": "Sleeping account wakes up",
        "description": "No activity for param_1 days and amount greater than param_2.",
        "simple_explanation": "An account unused for months suddenly sends a lot of money.",
        "params": [180, 20000, None, None],
        "param_labels": ["Days without activity", "Amount above (₹)"],
        "weight": 40,
    },
    {
        "rule_code": "R9",
        "name": "OTP / phishing takeover pattern",
        "simple_name": "OTP / phishing-link fraud",
        "description": "Payee added less than param_1 hours ago, amount at least param_3, and either the OTP was "
                       "verified on an untrusted device or the payment is within param_2 minutes of a login from a "
                       "new device, SIM change, password reset or mobile-number change.",
        "simple_explanation": "Money sent to a brand-new payee right after a risky login is the classic OTP scam.",
        "params": [24, 15, 10000, None],
        "param_labels": ["Payee newer than (hours)", "Risky login within (minutes)", "Amount from (₹)"],
        "weight": 55,
    },
]

SETTINGS = [
    ("REVIEW_THRESHOLD", "40", "Risk score from which a payment is held for review"),
    ("BLOCK_THRESHOLD", "70", "Risk score from which a payment is blocked"),
]


def _apply(rule, spec):
    rule.name = spec["name"]
    rule.simple_name = spec["simple_name"]
    rule.description = spec["description"]
    rule.simple_explanation = spec["simple_explanation"]
    rule.param_1, rule.param_2, rule.param_3, rule.param_4 = spec["params"]
    rule.param_labels = spec["param_labels"]
    rule.weight = spec["weight"]
    rule.is_active = True


def run(log=print):
    added = 0
    for order, spec in enumerate(RULES, start=1):
        if db.session.get(FraudRule, spec["rule_code"]) is None:
            rule = FraudRule(rule_code=spec["rule_code"], sort_order=order, updated_by="seed",
                             updated_at=datetime.now())
            _apply(rule, spec)
            db.session.add(rule)
            added += 1
    for key, value, description in SETTINGS:
        if db.session.get(SystemSetting, key) is None:
            db.session.add(SystemSetting(setting_key=key, setting_value=value, description=description,
                                         updated_by="seed"))
    db.session.commit()
    log(f"  fraud_rules: {added} added")


def reset_rules():
    """Restores every rule and band to the defaults above."""
    for order, spec in enumerate(RULES, start=1):
        rule = db.session.get(FraudRule, spec["rule_code"])
        if rule is None:
            rule = FraudRule(rule_code=spec["rule_code"], sort_order=order)
            db.session.add(rule)
        _apply(rule, spec)
        rule.updated_by = "seed"
    for key, value, description in SETTINGS:
        setting = db.session.get(SystemSetting, key)
        if setting is None:
            db.session.add(SystemSetting(setting_key=key, setting_value=value, description=description))
        else:
            setting.setting_value = value
    db.session.commit()
