"""
portal/logger.py
================
Rotating file log (logs/app.log, 5 MB x 5) plus console output.

Every request gets a short request ID (or reuses an incoming X-Request-ID),
which is stamped on each log line and echoed back in the response header, so
one transaction can be followed through the log.
"""

import logging
import os
import uuid
from logging.handlers import RotatingFileHandler

from flask import g, has_request_context, request

LOG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "logs"))
LOG_FORMAT = "%(asctime)s %(levelname)s [%(request_id)s] [%(name)s] %(message)s"


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = g.get("request_id", "-") if has_request_context() else "-"
        return True


def configure_logger(app):
    os.makedirs(LOG_DIR, exist_ok=True)
    formatter = logging.Formatter(LOG_FORMAT)
    request_filter = RequestIdFilter()

    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "app.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    console_handler = logging.StreamHandler()

    for handler in (file_handler, console_handler):
        handler.setFormatter(formatter)
        handler.addFilter(request_filter)
        handler.setLevel(logging.INFO)

    # Replace rather than append, so building several apps in one process
    # (the test suite does) doesn't print every line several times.
    app.logger.handlers = [file_handler, console_handler]
    app.logger.setLevel(logging.INFO)
    app.logger.propagate = False

    # Per-payment decision latency: file only (the console would slow the engine).
    decisions = logging.getLogger("portal.decisions")
    decisions.handlers = [file_handler]
    decisions.setLevel(logging.INFO)
    decisions.propagate = False

    @app.before_request
    def assign_request_id():
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]

    @app.after_request
    def echo_request_id(response):
        response.headers["X-Request-ID"] = g.get("request_id", "-")
        return response

    return app.logger
