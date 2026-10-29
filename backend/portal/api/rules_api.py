"""Rules console: thresholds, weights, on/off, and the decision bands.

Changes are written straight to fraud_rules / system_settings, which the
stored procedure reads on every payment -- so they apply to the very next
payment. The audit trigger records who changed what.
"""

from datetime import datetime

from flask import Blueprint, request

from portal.extensions import db
from portal.helpers.auth_helpers import current_user, min_role
from portal.helpers.db_helpers import fetch_all, jsonable, set_actor
from portal.helpers.responses import AppError, ok
from portal.helpers.validators import BandsSchema, RuleUpdateSchema, load
from portal.models import AuditLog, FraudRule, SystemSetting

rules_bp = Blueprint("rules", __name__, url_prefix="/rules")


def _bands():
    values = {s.setting_key: int(s.setting_value) for s in SystemSetting.query.all()}
    return {"review_threshold": values.get("REVIEW_THRESHOLD", 40), "block_threshold": values.get("BLOCK_THRESHOLD", 70),
            "model_weight": values.get("MODEL_SCORE_WEIGHT", 0)}


@rules_bp.get("")
@min_role("ANALYST")
def list_rules():
    rules = [r.to_dict() for r in FraudRule.query.order_by(FraudRule.sort_order).all()]
    stats = {r["rule_code"]: jsonable(r) for r in fetch_all("SELECT * FROM v_rule_precision")}
    for r in rules:
        r["stats"] = stats.get(r["rule_code"])
    history = [jsonable(h) for h in fetch_all(
        "SELECT id, actor, action, entity_id, old_value, new_value, logged_at FROM audit_log "
        "WHERE entity IN ('fraud_rules', 'system_settings') ORDER BY logged_at DESC LIMIT 30")]
    return ok({"rules": rules, "bands": _bands(), "history": history})


@rules_bp.put("/<code>")
@min_role("RISK_MANAGER")
def update_rule(code):
    rule = db.session.get(FraudRule, code.upper())
    if rule is None:
        raise AppError("That rule does not exist.", "NOT_FOUND", 404)
    body = request.get_json(silent=True) or {}
    data = load(RuleUpdateSchema, body)
    for key in ("param_1", "param_2", "param_3", "param_4"):
        if key in body:
            setattr(rule, key, data[key])
    if data["weight"] is not None:
        rule.weight = data["weight"]
    if data["is_active"] is not None:
        rule.is_active = data["is_active"]
    me = current_user()
    rule.updated_by = me.username
    rule.updated_at = datetime.now()
    set_actor(me.username)
    db.session.commit()
    return ok(rule.to_dict())


@rules_bp.put("/bands")
@min_role("RISK_MANAGER")
def update_bands():
    data = load(BandsSchema, request.get_json(silent=True))
    me = current_user()
    old = _bands()
    if data["model_weight"] is None:
        data["model_weight"] = old["model_weight"]
    for key, value in (("REVIEW_THRESHOLD", data["review_threshold"]), ("BLOCK_THRESHOLD", data["block_threshold"]),
                       ("MODEL_SCORE_WEIGHT", data["model_weight"])):
        setting = db.session.get(SystemSetting, key)
        if setting is None:
            setting = SystemSetting(setting_key=key, setting_value=str(value))
            db.session.add(setting)
        setting.setting_value = str(value)
        setting.updated_by = me.username
    db.session.add(AuditLog(actor=me.username, action="BANDS_UPDATED", entity="system_settings",
                            entity_id="bands", old_value=old, new_value=data))
    db.session.commit()
    return ok(_bands())
