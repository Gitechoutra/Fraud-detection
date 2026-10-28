"""GET /health (is the database reachable?) and GET / (what is this?)."""

from flask import Blueprint, current_app
from sqlalchemy import text

from portal.extensions import db
from portal.helpers.responses import error, ok

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
        procs = db.session.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.ROUTINES "
                "WHERE ROUTINE_SCHEMA = DATABASE() AND ROUTINE_TYPE = 'PROCEDURE'"
            )
        ).scalar()
    except Exception:
        current_app.logger.exception("Health check failed")
        return error("Database is not reachable.", "DB_DOWN", 503)
    return ok({"status": "healthy", "database": current_app.config["DB_NAME"], "procedures": procs})


@health_bp.get("/")
def index():
    return ok(
        {
            "name": "FraudShield API",
            "description": "SQL-based real-time fraud detection and transaction monitoring.",
            "docs": "See backend/docs/API.md",
            "health": "/health",
            "api_base": "/api",
        }
    )
