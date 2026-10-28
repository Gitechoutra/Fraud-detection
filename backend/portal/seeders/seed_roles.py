from portal.extensions import db
from portal.models import Role

ROLES = {
    "ADMIN": "Everything, including users and system settings.",
    "RISK_MANAGER": "Tune rules, manage the watchlist, run simulations and evaluations.",
    "ANALYST": "Monitor payments and investigate alerts and cases.",
}


def run(log=print):
    added = 0
    for name, description in ROLES.items():
        if Role.query.filter_by(name=name).first() is None:
            db.session.add(Role(name=name, description=description))
            added += 1
    db.session.commit()
    log(f"  roles: {added} added")
