"""Backend entry point.

`python app.py` starts the development server on port 5000 with the
background scheduler. The module-level `app` is also what the Flask CLI
auto-discovers, so `flask db upgrade` / `flask seed` work from this
directory with no FLASK_APP set (the CLI does not start the scheduler).
"""

import os

from portal import create_app, sync_default_users
from portal.scheduler import init_scheduler

app = create_app()

if __name__ == "__main__":
    # Under the debug reloader only the serving child process syncs.
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        sync_default_users(app)
    init_scheduler(app, reloader=app.debug)
    app.run(host="0.0.0.0", port=5000, debug=app.config["DEBUG"], threaded=True)
