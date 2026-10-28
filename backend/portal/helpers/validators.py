"""
portal/helpers/validators.py
============================
marshmallow schemas for every request body. `load(Schema, data)` validates
and raises marshmallow.ValidationError, which the global handler turns into
a 422 with the per-field messages.
"""

from marshmallow import EXCLUDE, Schema, ValidationError, fields, validate, validates_schema

CHANNELS = ["CARD", "UPI", "NETBANKING", "ATM"]
ROLES = ["ADMIN", "RISK_MANAGER", "ANALYST"]


class BaseSchema(Schema):
    class Meta:
        unknown = EXCLUDE


def load(schema_cls, data, **kwargs):
    return schema_cls(**kwargs).load(data or {})


class LoginSchema(BaseSchema):
    username = fields.String(required=True, validate=validate.Length(min=1, max=64))
    password = fields.String(required=True, validate=validate.Length(min=1, max=128))


class LogoutSchema(BaseSchema):
    refresh_token = fields.String(load_default=None)


class TransactionSchema(BaseSchema):
    external_ref = fields.String(required=True, validate=validate.Length(min=1, max=64))
    account_id = fields.Integer(load_default=None, validate=validate.Range(min=1))
    account_no = fields.String(load_default=None, validate=validate.Length(max=20))
    merchant_id = fields.Integer(load_default=None, validate=validate.Range(min=1))
    beneficiary_id = fields.Integer(load_default=None, validate=validate.Range(min=1))
    otp_request_id = fields.Integer(load_default=None, validate=validate.Range(min=1))
    amount = fields.Decimal(required=True, places=2, validate=validate.Range(min=0.01, max=100000000))
    currency = fields.String(load_default="INR", validate=validate.OneOf(["INR"]))
    channel = fields.String(required=True, validate=validate.OneOf(CHANNELS))
    city = fields.String(load_default=None, validate=validate.Length(max=64))
    device_id = fields.String(load_default=None, validate=validate.Length(max=64))
    ip_address = fields.String(load_default=None, validate=validate.Length(max=45))
    txn_time = fields.DateTime(load_default=None)
    is_fraud_label = fields.Boolean(load_default=None, allow_none=True)
    scenario = fields.String(load_default=None, validate=validate.Length(max=16))
    source = fields.String(load_default=None, validate=validate.Length(max=16))

    @validates_schema
    def account_given(self, data, **kwargs):
        if not data.get("account_id") and not data.get("account_no"):
            raise ValidationError("Give either account_id or account_no.", "account_id")


class AlertUpdateSchema(BaseSchema):
    assign_to_me = fields.Boolean(load_default=False)
    assigned_to = fields.Integer(load_default=None, allow_none=True)
    alert_status = fields.String(load_default=None, validate=validate.OneOf(["OPEN", "IN_PROGRESS", "CLOSED"]))


class CaseNoteSchema(BaseSchema):
    body = fields.String(required=True, validate=validate.Length(min=1, max=4000))


class CaseOutcomeSchema(BaseSchema):
    outcome = fields.String(required=True, validate=validate.OneOf(["CONFIRMED_FRAUD", "FALSE_POSITIVE"]))
    notes = fields.String(load_default=None, validate=validate.Length(max=4000))


class RuleUpdateSchema(BaseSchema):
    param_1 = fields.Decimal(load_default=None, allow_none=True, places=2, validate=validate.Range(min=0))
    param_2 = fields.Decimal(load_default=None, allow_none=True, places=2, validate=validate.Range(min=0))
    param_3 = fields.Decimal(load_default=None, allow_none=True, places=2, validate=validate.Range(min=0))
    param_4 = fields.Decimal(load_default=None, allow_none=True, places=2, validate=validate.Range(min=0))
    weight = fields.Integer(load_default=None, validate=validate.Range(min=0, max=100))
    is_active = fields.Boolean(load_default=None)


class BandsSchema(BaseSchema):
    review_threshold = fields.Integer(required=True, validate=validate.Range(min=1, max=99))
    block_threshold = fields.Integer(required=True, validate=validate.Range(min=2, max=100))

    @validates_schema
    def hold_below_block(self, data, **kwargs):
        if data["review_threshold"] >= data["block_threshold"]:
            raise ValidationError("The 'hold' score must be lower than the 'block' score.", "review_threshold")


class WatchlistSchema(BaseSchema):
    entry_type = fields.String(required=True, validate=validate.OneOf(["IP", "DEVICE", "ACCOUNT", "MERCHANT"]))
    entry_value = fields.String(required=True, validate=validate.Length(min=1, max=128))
    reason = fields.String(required=True, validate=validate.Length(min=3, max=255))


class OtpRequestSchema(BaseSchema):
    beneficiary_id = fields.Integer(required=True)
    amount = fields.Decimal(required=True, places=2, validate=validate.Range(min=1, max=10000000))


class OtpVerifySchema(BaseSchema):
    otp_request_id = fields.Integer(required=True)
    otp = fields.String(required=True, validate=validate.Regexp(r"^\d{6}$", error="Enter the 6-digit OTP."))


class ApprovalResponseSchema(BaseSchema):
    answer = fields.String(required=True, validate=validate.OneOf(["YES", "NO"]))


class BankLoginSchema(BaseSchema):
    netbanking_id = fields.String(required=True, validate=validate.Length(min=1, max=64))
    password = fields.String(required=True, validate=validate.Length(min=1, max=128))
    device_id = fields.String(required=True, validate=validate.Length(min=3, max=64))
    device_label = fields.String(load_default=None, validate=validate.Length(max=120))
    ip_address = fields.String(load_default=None, validate=validate.Length(max=45))
    city = fields.String(load_default=None, validate=validate.Length(max=64))


class PayeeSchema(BaseSchema):
    payee_name = fields.String(required=True, validate=validate.Length(min=2, max=120))
    payee_account_no = fields.String(required=True, validate=validate.Regexp(r"^\d{9,18}$", error="Account number must be 9-18 digits."))
    payee_ifsc = fields.String(required=True, validate=validate.Regexp(r"^[A-Z]{4}0[A-Z0-9]{6}$", error="Enter a valid IFSC like HDFC0001234."))


class SendMoneySchema(BaseSchema):
    beneficiary_id = fields.Integer(required=True)
    amount = fields.Decimal(required=True, places=2, validate=validate.Range(min=1, max=10000000))


class UserCreateSchema(BaseSchema):
    username = fields.String(required=True, validate=validate.Regexp(r"^[a-zA-Z0-9_.-]{3,64}$"))
    full_name = fields.String(required=True, validate=validate.Length(min=2, max=120))
    password = fields.String(required=True, validate=validate.Length(min=8, max=128))
    role = fields.String(required=True, validate=validate.OneOf(ROLES))


class UserUpdateSchema(BaseSchema):
    full_name = fields.String(load_default=None, validate=validate.Length(min=2, max=120))
    password = fields.String(load_default=None, validate=validate.Length(min=8, max=128))
    role = fields.String(load_default=None, validate=validate.OneOf(ROLES))
    is_active = fields.Boolean(load_default=None)


class StreamStartSchema(BaseSchema):
    rate = fields.Float(load_default=2.0, validate=validate.Range(min=0.2, max=10))
    fraud_ratio = fields.Float(load_default=0.03, validate=validate.Range(min=0, max=0.5))


class EvaluationRunSchema(BaseSchema):
    size = fields.Integer(load_default=1000, validate=validate.Range(min=100, max=20000))
    fraud_ratio = fields.Float(load_default=0.03, validate=validate.Range(min=0.005, max=0.5))
