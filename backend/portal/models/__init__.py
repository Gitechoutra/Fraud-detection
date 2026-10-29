"""
portal/models
=============
SQLAlchemy models, one file per table group. Importing this package registers
every table on db.metadata, which is what Flask-Migrate autogenerates from.

Index names here match portal/sql/01_indexes.sql exactly, so the SQL file and
the models describe the same indexes (the loader skips ones that exist).
"""

from portal.models.types import DT, MONEY  # noqa: F401
from portal.models.user import Role, TokenBlocklist, User  # noqa: F401
from portal.models.customer import Customer  # noqa: F401
from portal.models.account import Account  # noqa: F401
from portal.models.merchant import Merchant  # noqa: F401
from portal.models.device import Device  # noqa: F401
from portal.models.session import SessionEvent  # noqa: F401
from portal.models.beneficiary import Beneficiary  # noqa: F401
from portal.models.otp_request import OtpRequest  # noqa: F401
from portal.models.transaction import Transaction  # noqa: F401
from portal.models.fraud_rule import FraudRule, SystemSetting  # noqa: F401
from portal.models.rule_hit import RuleHit  # noqa: F401
from portal.models.watchlist import WatchlistEntry  # noqa: F401
from portal.models.alert import Alert  # noqa: F401
from portal.models.case import Case, CaseNote  # noqa: F401
from portal.models.device_approval import DeviceApproval  # noqa: F401
from portal.models.notification import Notification  # noqa: F401
from portal.models.audit_log import AuditChain, AuditLog  # noqa: F401
from portal.models.metric_run import DailyStat, MetricRun  # noqa: F401
from portal.models.demo_users import (  # noqa: F401
    AttackEvent,
    CustomerAlert,
    CustomerUser,
    FraudsterUser,
    StolenCredential,
)
