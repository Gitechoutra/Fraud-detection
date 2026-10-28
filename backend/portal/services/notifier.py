"""
portal/services/notifier.py
===========================
Customer notifications behind one interface.

Every provider first writes the message to the `notifications` table (that
is what the demo "Customer phone" screens show), then delivers it:
  - ConsoleNotifier (default): prints to the log.
  - Msg91Notifier / TwilioNotifier: real SMS, enabled only when NOTIFIER is
    set and their keys exist in .env. A delivery failure is logged, never
    raised -- a fraud decision must not fail because an SMS gateway did.
"""

from datetime import datetime

import requests
from flask import current_app

from portal.extensions import db
from portal.models import Customer, Notification


class BaseNotifier:
    name = "base"

    def send(self, customer_id, channel, title, body, kind="INFO", ref_id=None):
        """Records the notification (in the caller's DB transaction) and
        delivers it. Returns the Notification row."""
        note = Notification(
            customer_id=customer_id,
            channel=channel,
            kind=kind,
            ref_id=ref_id,
            title=title,
            body=body,
            created_at=datetime.now(),
        )
        db.session.add(note)
        db.session.flush()
        current_app.logger.info("[%s] %s to customer %s: %s", self.name, channel, customer_id, body)
        if channel == "SMS":
            customer = db.session.get(Customer, customer_id)
            if customer and customer.phone:
                try:
                    self.deliver_sms(customer.phone, body)
                except Exception:
                    current_app.logger.exception("SMS delivery via %s failed", self.name)
        return note

    def deliver_sms(self, phone, body):
        """Console provider: the log line above is the delivery."""


class ConsoleNotifier(BaseNotifier):
    name = "console"


class Msg91Notifier(BaseNotifier):
    name = "msg91"

    def deliver_sms(self, phone, body):
        cfg = current_app.config
        requests.get(
            "https://api.msg91.com/api/sendhttp.php",
            params={
                "authkey": cfg["MSG91_AUTH_KEY"],
                "mobiles": phone.lstrip("+"),
                "message": body,
                "sender": cfg["MSG91_SENDER"],
                "route": "4",
                "country": "91",
            },
            timeout=5,
        ).raise_for_status()


class TwilioNotifier(BaseNotifier):
    name = "twilio"

    def deliver_sms(self, phone, body):
        cfg = current_app.config
        requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{cfg['TWILIO_SID']}/Messages.json",
            data={"To": phone, "From": cfg["TWILIO_FROM"], "Body": body},
            auth=(cfg["TWILIO_SID"], cfg["TWILIO_TOKEN"]),
            timeout=5,
        ).raise_for_status()


def get_notifier():
    cfg = current_app.config
    choice = (cfg.get("NOTIFIER") or "console").lower()
    if choice == "msg91" and cfg.get("MSG91_AUTH_KEY"):
        return Msg91Notifier()
    if choice == "twilio" and cfg.get("TWILIO_SID") and cfg.get("TWILIO_TOKEN") and cfg.get("TWILIO_FROM"):
        return TwilioNotifier()
    return ConsoleNotifier()
