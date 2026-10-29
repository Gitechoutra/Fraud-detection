"""
portal/config.py
================
Development / Testing / Production configuration, all read from `.env`.

The database URL is always *built* from the separate DB_* variables, never
written by hand: the password goes through `quote_plus`, so characters such
as `@` (which would otherwise end the user:password part of the URL) are safe.
"""

import os
from datetime import timedelta
from urllib.parse import quote_plus

from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def env(name, default=None):
    return os.environ.get(name, default)


def build_db_url(db_name=None, include_db=True):
    """mysql+pymysql URL from DB_* settings. include_db=False gives a server
    URL (no schema), used to CREATE DATABASE before the schema exists."""
    user = quote_plus(env("DB_USER", "root"))
    password = quote_plus(env("DB_PASSWORD", ""))
    host = env("DB_HOST", "127.0.0.1")
    port = env("DB_PORT", "3306")
    name = db_name or env("DB_NAME", "fraude")
    path = f"/{name}" if include_db else "/"
    return f"mysql+pymysql://{user}:{password}@{host}:{port}{path}?charset=utf8mb4"


class BaseConfig:
    ENV_NAME = "base"
    DEBUG = False
    TESTING = False

    SECRET_KEY = env("SECRET_KEY", "change-me")
    JWT_SECRET_KEY = env("JWT_SECRET_KEY", "change-me-too")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=7)
    JWT_TOKEN_LOCATION = ["headers"]

    DB_NAME = env("DB_NAME", "fraude")
    SQLALCHEMY_DATABASE_URI = build_db_url(DB_NAME)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # No pre-ping on every checkout (it costs a round trip per payment);
    # connections are recycled well before MySQL's 8-hour wait_timeout.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 1800,
        "pool_size": 20,
        "max_overflow": 20,
    }

    FRONTEND_ORIGIN = env("FRONTEND_ORIGIN", "http://localhost:5173")
    CORS_ORIGINS = [o.strip() for o in FRONTEND_ORIGIN.split(",") if o.strip()]
    INGEST_API_KEY = env("INGEST_API_KEY", "dev-ingest-key")

    UPLOAD_FOLDER = os.path.join(BASE_DIR, "portal", "uploads")
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB CSV uploads

    RATELIMIT_ENABLED = True
    RATELIMIT_STORAGE_URI = "memory://"
    RATELIMIT_HEADERS_ENABLED = True

    NOTIFIER = env("NOTIFIER", "console")
    MSG91_AUTH_KEY = env("MSG91_AUTH_KEY", "")
    MSG91_SENDER = env("MSG91_SENDER", "FRSHLD")
    TWILIO_SID = env("TWILIO_SID", "")
    TWILIO_TOKEN = env("TWILIO_TOKEN", "")
    TWILIO_FROM = env("TWILIO_FROM", "")

    # OTP Shield
    OTP_TTL_SECONDS = 180
    APPROVAL_TTL_SECONDS = 300
    OTP_MAX_REQUESTS_PER_WINDOW = 5
    OTP_REQUEST_WINDOW_MINUTES = 10
    OTP_MAX_VERIFY_ATTEMPTS = 3

    SCHEDULER_ENABLED = True

    # Customer app demo data and the fraudster simulation console (/attacker).
    DEMO_MODE = env("DEMO_MODE", "true").lower() in ("1", "true", "yes")


class DevelopmentConfig(BaseConfig):
    ENV_NAME = "development"
    DEBUG = True


class TestingConfig(BaseConfig):
    ENV_NAME = "testing"
    TESTING = True
    DB_NAME = env("DB_TEST_NAME", "fraude_test")
    SQLALCHEMY_DATABASE_URI = build_db_url(DB_NAME)
    RATELIMIT_ENABLED = False
    SCHEDULER_ENABLED = False
    NOTIFIER = "console"


class ProductionConfig(BaseConfig):
    ENV_NAME = "production"
    # The simulation console must be switched on deliberately in production.
    DEMO_MODE = env("DEMO_MODE", "false").lower() in ("1", "true", "yes")


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name=None):
    return CONFIGS.get(name or env("FLASK_ENV", "development"), DevelopmentConfig)
