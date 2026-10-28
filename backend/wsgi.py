"""Production entry point.

Linux / Docker:  gunicorn -w 1 --threads 16 -b 0.0.0.0:5000 wsgi:app
Windows:         python wsgi.py   (serves with Waitress on port 5000)

One worker process with many threads: the live-traffic simulator and the
evaluation progress live in process memory, so they must not be split
across several worker processes.
"""

import os

from portal import create_app
from portal.scheduler import init_scheduler

app = create_app(os.environ.get("FLASK_ENV", "production"))
init_scheduler(app)

if __name__ == "__main__":
    from waitress import serve

    serve(app, host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), threads=16)
