"""
portal/__init__.py
==================
Application factory.

`create_app()` builds the Flask app: config, logging, extensions, models,
routes, API blueprints, JWT callbacks, error handlers and CLI commands, in
that order. It is what `app.py`, `wsgi.py`, the tests and the Flask CLI use.

The background scheduler is NOT started here (the Flask CLI and the tests
build apps too); `app.py` and `wsgi.py` start it explicitly.
"""

import os

from flask import Flask
from marshmallow import ValidationError
from werkzeug.exceptions import HTTPException

from portal.config import get_config
from portal.extensions import cors, db, jwt, limiter, migrate
from portal.helpers.responses import AppError, error
from portal.logger import configure_logger


def init_jwt(app):
    from portal.models import TokenBlocklist

    @jwt.token_in_blocklist_loader
    def is_revoked(_header, payload):
        return db.session.query(TokenBlocklist.id).filter_by(jti=payload["jti"]).first() is not None

    @jwt.expired_token_loader
    def expired(_header, _payload):
        return error("Your session has expired. Please log in again.", "TOKEN_EXPIRED", 401)

    @jwt.invalid_token_loader
    def invalid(reason):
        return error("Invalid login token.", "INVALID_TOKEN", 401)

    @jwt.unauthorized_loader
    def missing(reason):
        return error("Please log in to continue.", "UNAUTHORIZED", 401)

    @jwt.revoked_token_loader
    def revoked(_header, _payload):
        return error("You have been logged out. Please log in again.", "TOKEN_REVOKED", 401)


def init_error_handlers(app):
    @app.errorhandler(AppError)
    def handle_app_error(exc):
        return error(exc.message, exc.code, exc.status)

    @app.errorhandler(ValidationError)
    def handle_validation(exc):
        return error("Some fields are missing or invalid.", "VALIDATION_ERROR", 422, exc.messages)

    @app.errorhandler(HTTPException)
    def handle_http(exc):
        codes = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            409: "CONFLICT",
            413: "FILE_TOO_LARGE",
            429: "TOO_MANY_REQUESTS",
        }
        messages = {
            404: "We couldn't find that.",
            405: "That action isn't allowed here.",
            413: "The file is too large (max 10 MB).",
            429: "Too many attempts. Please wait a moment and try again.",
        }
        return error(
            messages.get(exc.code, exc.description or "Request failed."),
            codes.get(exc.code, "HTTP_ERROR"),
            exc.code or 500,
        )

    @app.errorhandler(Exception)
    def handle_unexpected(exc):
        # Full details go to the log; the client only ever sees a generic message.
        db.session.rollback()
        app.logger.exception("Unhandled error: %s", exc)
        return error("Something went wrong on our side. Please try again.", "SERVER_ERROR", 500)


def create_app(config_name=None):
    app = Flask(__name__)
    app.config.from_object(get_config(config_name))
    app.json.sort_keys = False

    configure_logger(app)
    app.logger.info(
        "Initializing FraudShield -- environment: %s, database: %s",
        app.config["ENV_NAME"],
        app.config["DB_NAME"],
    )

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    limiter.init_app(app)
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
        expose_headers=["X-Request-ID"],
    )
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # Imported for the side effect of registering every table on db.metadata.
    from portal import models  # noqa: F401
    from portal.api import register_api
    from portal.cli import register_cli
    from portal.routes import register_routes

    init_jwt(app)
    register_routes(app)
    register_api(app)
    init_error_handlers(app)
    register_cli(app)
    return app


def sync_default_users(app):
    """Run at server start: ensures the roles and the admin / risk / analyst
    users exist with the credentials currently in .env."""
    from portal.seeders import seed_admin, seed_roles

    with app.app_context():
        try:
            seed_roles.run(log=app.logger.info)
            seed_admin.run(log=app.logger.info)
        except Exception as exc:
            db.session.rollback()
            app.logger.warning("Could not sync default users (run `flask db upgrade` first?): %s", exc)
        finally:
            db.session.remove()
