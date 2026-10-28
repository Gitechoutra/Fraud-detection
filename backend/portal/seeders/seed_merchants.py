"""60 merchants across categories and cities (a few high-risk ones)."""

import random

from portal.extensions import db
from portal.models import Merchant
from portal.services.simulator import CITIES

PREFIXES = ["Sri", "New", "Royal", "City", "Green", "Annapurna", "Lakshmi", "Metro", "Star", "Ganesh"]
CATEGORIES = {
    "Grocery": ["Supermarket", "Kirana Store", "Fresh Mart"],
    "Restaurants": ["Biryani House", "Tiffin Centre", "Cafe"],
    "Fuel": ["Fuel Station", "Petroleum"],
    "Pharmacy": ["Medicals", "Pharmacy"],
    "Electronics": ["Electronics", "Mobile World"],
    "Clothing": ["Textiles", "Fashion Hub"],
    "Utilities": ["Electricity Bill Pay", "Broadband"],
    "Travel": ["Travels", "Tours"],
    "Entertainment": ["Cinemas", "Gaming Zone"],
    "Online Shopping": ["Online Store", "Deals Online"],
    "Jewellery": ["Jewellers", "Gold Palace"],
    "Education": ["Coaching Centre", "Book Depot"],
}
HIGH_RISK = [
    ("QuickCash Gift Cards", "Online Shopping"),
    ("CryptoFast Exchange", "Online Shopping"),
    ("Lucky Win Gaming", "Entertainment"),
]
TOTAL = 60


def run(log=print, rng=None):
    if Merchant.query.count() >= TOTAL:
        log("  merchants: already present")
        return
    rng = rng or random.Random(7)
    names = set(m.name for m in Merchant.query.all())
    rows = []
    for name, category in HIGH_RISK:
        if name not in names:
            rows.append(Merchant(name=name, category=category, city=rng.choice(CITIES), risk_level="HIGH"))
            names.add(name)
    cats = list(CATEGORIES)
    i = 0
    while len(names) < TOTAL:
        city = CITIES[i % len(CITIES)]
        category = cats[i % len(cats)]
        name = f"{rng.choice(PREFIXES)} {rng.choice(CATEGORIES[category])} {city}"
        i += 1
        if name in names:
            continue
        names.add(name)
        rows.append(Merchant(name=name, category=category, city=city,
                             risk_level="MEDIUM" if category in ("Jewellery", "Travel") else "LOW"))
    db.session.add_all(rows)
    db.session.commit()
    log(f"  merchants: {len(rows)} added")
