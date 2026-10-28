"""
portal/cli.py
=============
Flask CLI commands (run from backend/ with the venv active):

    flask create-db          create fraud_sql and fraud_sql_test if missing
    flask init-db-objects    load portal/sql/*.sql (indexes, views, triggers, procedures)
    flask seed               load all demo data (idempotent)
    flask reset-rules        restore default rule thresholds and weights
    flask show-db-objects    list procedures, triggers and views
    flask simulate-scenario R3
    flask evaluate --size 5000
"""

import click
from flask import current_app
from sqlalchemy import text

from portal.extensions import db


def register_cli(app):
    @app.cli.command("create-db")
    def create_db_command():
        """Create the main and test databases if they do not exist."""
        from portal.config import env
        from portal.helpers.db_helpers import create_databases

        names = [env("DB_NAME", "fraud_sql"), env("DB_TEST_NAME", "fraud_sql_test")]
        create_databases(names, env("DB_HOST", "127.0.0.1"), env("DB_PORT", "3306"),
                         env("DB_USER", "root"), env("DB_PASSWORD", ""))
        click.echo(f"Databases ready: {', '.join(names)}")

    @app.cli.command("init-db-objects")
    def init_db_objects_command():
        """Load indexes, views, triggers and stored procedures."""
        from portal.helpers.db_helpers import load_sql_objects

        click.echo(f"Loading SQL objects into {current_app.config['DB_NAME']}:")
        load_sql_objects(log=click.echo)
        click.echo("Done.")

    @app.cli.command("show-db-objects")
    def show_db_objects_command():
        """List the stored procedures, triggers and views."""
        for title, sql in (
            ("Procedures", "SHOW PROCEDURE STATUS WHERE Db = DATABASE()"),
            ("Functions", "SHOW FUNCTION STATUS WHERE Db = DATABASE()"),
            ("Triggers", "SHOW TRIGGERS"),
            ("Views", "SHOW FULL TABLES WHERE Table_type = 'VIEW'"),
        ):
            rows = db.session.execute(text(sql)).fetchall()
            click.echo(f"{title} ({len(rows)}):")
            for r in rows:
                click.echo(f"  - {r[1] if title in ('Procedures', 'Functions') else r[0]}")

    @app.cli.command("seed")
    @click.option("--customers", default=200, show_default=True)
    def seed_command(customers):
        """Load all demo data (safe to run again)."""
        from portal.seeds import run_all

        run_all(log=click.echo, customers=customers)

    @app.cli.command("reset-rules")
    def reset_rules_command():
        """Restore default rule thresholds, weights and decision bands."""
        from portal.seeders.seed_rules import reset_rules

        reset_rules()
        click.echo("Rules restored to defaults.")

    @app.cli.command("simulate-scenario")
    @click.argument("code")
    def simulate_scenario_command(code):
        """Run one fraud story (R1..R9 or NORMAL) and print the decision."""
        from portal.services.simulator import run_scenario

        result = run_scenario(code)
        click.echo(result["story"])
        click.echo(result["summary"])

    @app.cli.command("evaluate")
    @click.option("--size", default=5000, show_default=True)
    @click.option("--fraud-ratio", default=0.03, show_default=True)
    @click.option("--workers", default=8, show_default=True)
    @click.option("--keep", is_flag=True, help="Keep the evaluation rows instead of deleting them.")
    def evaluate_command(size, fraud_ratio, workers, keep):
        """Run an in-process evaluation and print the metrics."""
        from portal.services.evaluator import run_evaluation

        m = run_evaluation(size=size, fraud_ratio=fraud_ratio, workers=workers, keep=keep, log=click.echo)
        click.echo(f"TP={m['tp']} FP={m['fp']} TN={m['tn']} FN={m['fn']}")
