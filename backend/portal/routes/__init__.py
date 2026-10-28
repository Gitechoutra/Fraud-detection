"""Non-API routes (health check and the API info page)."""


def register_routes(app):
    from portal.routes.health import health_bp

    app.register_blueprint(health_bp)
