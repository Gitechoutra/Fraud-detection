"""Backend entry point.

`python app.py` starts the development server on port 5000 with the
background scheduler. The module-level `app` is also what the Flask CLI
auto-discovers, so `flask db upgrade` / `flask seed` work from this
directory with no FLASK_APP set (the CLI does not start the scheduler).
"""

from portal import create_app
from portal.scheduler import init_scheduler

app = create_app()

if __name__ == "__main__":
    init_scheduler(app, reloader=app.debug)
    app.run(host="0.0.0.0", port=5000, debug=app.config["DEBUG"], threaded=True)
