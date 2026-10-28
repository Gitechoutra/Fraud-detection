from portal.extensions import db


class Merchant(db.Model):
    __tablename__ = "merchants"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(32), nullable=False)
    city = db.Column(db.String(64), nullable=False)
    risk_level = db.Column(db.String(8), nullable=False, default="LOW")  # LOW / MEDIUM / HIGH

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "city": self.city,
            "risk_level": self.risk_level,
        }
