"""
One JSON shape for every response:
    { "ok": true,  "data": ... }
    { "ok": false, "error": { "code": "...", "message": "..." } }
"""

import math

from flask import jsonify


class AppError(Exception):
    """Raise anywhere in a request to return a clean JSON error."""

    def __init__(self, message, code="BAD_REQUEST", status=400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


def ok(data=None, status=200):
    return jsonify({"ok": True, "data": data}), status


def error(message, code="BAD_REQUEST", status=400, details=None):
    body = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return jsonify({"ok": False, "error": body}), status


def page_args(default_per_page=25, max_per_page=200):
    """(page, per_page, offset) from ?page=&per_page= query args."""
    from flask import request

    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(max_per_page, max(1, int(request.args.get("per_page", default_per_page))))
    except ValueError:
        raise AppError("page and per_page must be numbers.", "BAD_REQUEST", 400)
    return page, per_page, (page - 1) * per_page


def paginated(items, total, page, per_page):
    return ok(
        {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": max(1, math.ceil(total / per_page)) if per_page else 1,
        }
    )
