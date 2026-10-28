"""A few known-bad IPs, devices, accounts and merchants."""

from portal.extensions import db
from portal.models import Merchant, WatchlistEntry

ENTRIES = [
    ("IP", "185.220.101.4", "Anonymous proxy used in a phishing campaign"),
    ("IP", "45.155.205.233", "Reported by another bank for card testing"),
    ("IP", "103.88.12.77", "Linked to a fake KYC-update call centre"),
    ("DEVICE", "DEV-STOLEN-0001", "Phone reported stolen by its owner"),
    ("DEVICE", "DEV-EMULATOR-9F2A", "Android emulator used for account takeovers"),
    ("ACCOUNT", "99887766554433", "Money-mule account (police complaint)"),
    ("ACCOUNT", "50100777888999", "Received money from 14 scam victims"),
]


def run(log=print):
    added = 0
    entries = list(ENTRIES)
    risky = Merchant.query.filter_by(name="QuickCash Gift Cards").first()
    if risky:
        entries.append(("MERCHANT", str(risky.id), "Gift-card shop used to cash out stolen money"))
    for entry_type, value, reason in entries:
        if WatchlistEntry.query.filter_by(entry_type=entry_type, entry_value=value).first() is None:
            db.session.add(WatchlistEntry(entry_type=entry_type, entry_value=value, reason=reason, added_by="seed"))
            added += 1
    db.session.commit()
    log(f"  watchlist: {added} added")
