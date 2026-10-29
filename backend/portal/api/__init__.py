"""Registers every REST blueprint under /api."""

from flask import Blueprint

from portal.api.alerts_api import alerts_bp
from portal.api.attacker_api import attacker_bp
from portal.api.audit_api import audit_bp
from portal.api.auth_api import auth_bp
from portal.api.bank_demo_api import bank_demo_bp
from portal.api.cases_api import cases_bp
from portal.api.customer_api import customer_bp
from portal.api.customers_api import customers_bp
from portal.api.dashboard_api import dashboard_bp
from portal.api.demo_api import demo_bp
from portal.api.evaluation_api import evaluation_bp
from portal.api.otp_api import otp_bp
from portal.api.rules_api import rules_bp
from portal.api.simulator_api import simulator_bp
from portal.api.transactions_api import transactions_bp
from portal.api.users_api import users_bp
from portal.api.watchlist_api import watchlist_bp

BLUEPRINTS = [
    auth_bp, transactions_bp, alerts_bp, cases_bp, rules_bp, otp_bp, bank_demo_bp,
    simulator_bp, dashboard_bp, evaluation_bp, watchlist_bp, customers_bp, audit_bp, users_bp,
    customer_bp, attacker_bp, demo_bp,
]


def register_api(app):
    api = Blueprint("api", __name__, url_prefix="/api")
    for bp in BLUEPRINTS:
        api.register_blueprint(bp)
    app.register_blueprint(api)
