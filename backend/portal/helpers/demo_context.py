"""
portal/helpers/demo_context.py
==============================
Device, city and network address for the customer app and the fraudster
console.

The browser sends its own random device id (X-Device-Id, kept in its local
storage, so a private window gets a new one) and the demo city it says it is
in (X-Demo-City). Both are *claims*, used only as inputs to the fraud rules
-- exactly like the device and city a real bank receives from a phone. They
never prove identity: a device is trusted only after the server has verified
the customer (password, or an OTP Shield approval).

The network address is never taken from the client. Behind localhost every
request comes from 127.0.0.1, which would make all demo users look like one
machine (and a single watchlist entry would block everyone), so for local or
private addresses a stable demo address is derived from the device id; any
public address is used as is.
"""

import hashlib
import ipaddress
import re
from datetime import datetime, timedelta

from flask import request
from flask_jwt_extended import create_access_token

from portal.helpers.responses import AppError
from portal.services.simulator import CITIES, ip_for_device

DEVICE_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
SESSION_MINUTES = 30


def device_id():
    value = (request.headers.get("X-Device-Id") or "").strip()
    if not DEVICE_RE.fullmatch(value):
        raise AppError("This browser did not send a valid device id.", "BAD_DEVICE", 400)
    return value


def demo_city(default):
    city = (request.headers.get("X-Demo-City") or "").strip()
    return city if city in CITIES else default


def network_address(device, fraudster=False):
    remote = request.remote_addr or "127.0.0.1"
    try:
        local = ipaddress.ip_address(remote).is_private or ipaddress.ip_address(remote).is_loopback
    except ValueError:
        local = True
    if not local:
        return remote
    if fraudster:
        h = hashlib.sha1(f"fraud:{device}".encode("utf-8")).digest()
        return f"103.{h[0] % 200 + 20}.{h[1] % 254 + 1}.{h[2] % 254 + 1}"
    return ip_for_device(device)


def issue_token(kind, uid, **claims):
    """Short-lived access token of the given kind. iat_ms lets a forced
    logout (tokens_valid_after) end sessions issued in the same second."""
    now = datetime.now()
    return create_access_token(
        identity=f"{kind}:{uid}",
        expires_delta=timedelta(minutes=SESSION_MINUTES),
        additional_claims={"kind": kind, "uid": uid, "iat_ms": int(now.timestamp() * 1000), **claims},
    )
