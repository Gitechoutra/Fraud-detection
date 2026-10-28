"""
200 customers with realistic Indian names, home cities and spending
profiles, 1-2 accounts each, 1-2 trusted devices, a couple of long-standing
payees, and about 5% dormant accounts (unused for 200-400 days).
"""

import random
from datetime import date, datetime, timedelta

from faker import Faker

from portal.extensions import db
from portal.models import Account, Beneficiary, Customer, Device
from portal.services.simulator import CITIES

CUSTOMER_COUNT = 200
DEVICE_MODELS = [
    "Samsung Galaxy M32", "Redmi Note 12", "iPhone 13", "OnePlus Nord CE", "Vivo Y21",
    "Realme Narzo 50", "Oppo A78", "Laptop (Chrome)", "Pixel 6a", "iPhone 11",
]
CHANNEL_SETS = ["UPI,CARD", "UPI", "UPI,CARD,NETBANKING", "CARD,ATM", "UPI,ATM", "UPI,NETBANKING"]
PAYEE_NAMES = ["Amma", "Appa", "House Owner", "Brother", "Sister", "Milk Vendor", "Tuition Fees", "Maid Salary"]


def _account_no(rng, used):
    while True:
        no = str(rng.randint(10**13, 10**14 - 1))
        if no not in used:
            used.add(no)
            return no


def run(log=print, count=CUSTOMER_COUNT, rng=None):
    # The demo customer (Ravi) is seeded separately and not counted here.
    existing = Customer.query.filter(Customer.netbanking_id.is_(None)).count()
    if existing >= count:
        log("  customers: already present")
        return
    rng = rng or random.Random(42)
    fake = Faker("en_IN")
    Faker.seed(42)
    used = {a.account_no for a in Account.query.all()}
    now = datetime.now()

    created_accounts = []
    for i in range(existing, count):
        name = fake.name()
        typical = round(10 ** rng.uniform(2.48, 3.9), 0)  # ~₹300 .. ~₹8,000, log-uniform
        frm = rng.randint(6, 10)
        customer = Customer(
            name=name,
            phone=f"+91{rng.choice('6789')}{rng.randint(100000000, 999999999)}",
            email=f"{name.lower().replace(' ', '.').replace('..', '.')}{i}@example.in",
            home_city=CITIES[i % 8] if rng.random() < 0.85 else rng.choice(CITIES),
            kyc_status="VERIFIED" if rng.random() < 0.95 else "PENDING",
            created_at=now - timedelta(days=rng.randint(400, 3000)),
            typical_amount=typical,
            active_from_hour=frm,
            active_to_hour=rng.randint(20, 23),
            usual_channels=rng.choice(CHANNEL_SETS),
        )
        db.session.add(customer)
        db.session.flush()

        devices = [
            (f"DEV-{customer.id:04d}-{n}", rng.choice(DEVICE_MODELS)) for n in range(1, rng.choice([2, 2, 3]))
        ]
        for k in range(2 if rng.random() < 0.3 else 1):
            account = Account(
                customer_id=customer.id,
                account_no=_account_no(rng, used),
                account_type="SAVINGS" if k == 0 else "CURRENT",
                opened_on=date.today() - timedelta(days=rng.randint(365, 3000)),
                status="ACTIVE",
                balance=round(typical * rng.uniform(20, 120), 2),
            )
            db.session.add(account)
            db.session.flush()
            created_accounts.append(account)
            first_seen = now - timedelta(days=rng.randint(120, 700))
            for device_id, label in devices:
                db.session.add(Device(account_id=account.id, device_id=device_id, device_label=label,
                                      first_seen=first_seen, last_seen=now - timedelta(days=1), is_trusted=True))
            for name_ in rng.sample(PAYEE_NAMES, rng.randint(1, 3)):
                db.session.add(Beneficiary(
                    account_id=account.id,
                    payee_name=name_,
                    payee_account_no=str(rng.randint(10**11, 10**12 - 1)),
                    payee_ifsc=f"{rng.choice(['SBIN', 'HDFC', 'ICIC', 'UTIB', 'KKBK'])}0{rng.randint(100000, 999999)}",
                    added_at=now - timedelta(days=rng.randint(60, 900)),
                    added_device_id=devices[0][0],
                ))

    # About 5% of accounts have been asleep for 200-400 days.
    for account in rng.sample(created_accounts, max(1, len(created_accounts) // 20)):
        account.status = "DORMANT"
        account.last_txn_at = now - timedelta(days=rng.randint(200, 400))
    db.session.commit()
    log(f"  customers: {count - existing} added, accounts: {len(created_accounts)} added")
