"""
portal/cli.py
=============
Flask CLI commands (run from backend/ with the venv active):

    flask create-db          create the fraude database if missing
    flask init-db-objects    load portal/sql/*.sql (indexes, views, triggers, procedures)
    flask seed               load all demo data (idempotent)
    flask seed-demo [--reset] customer-app / fraudster demo logins; --reset replays the demo
    flask export-master-data snapshot this DB so teammates get it on `flask db upgrade`
    flask load-master-data   load that snapshot by hand (--replace for an exact copy)
    flask reset-rules        restore default rule thresholds and weights
                             (--spec-weights: the specification's Table 4.4 weights)
    flask show-db-objects    list procedures, triggers and views
    flask simulate-scenario R3   (or a combination such as R1+R4)
    flask evaluate --size 5000
    flask benchmark-indexes  evaluate with and without the composite indexes
    flask verify-audit       prove the audit log was not changed
    flask export-ddl         write docs/schema.sql (the CREATE TABLE script)
    flask export-dataset     write a labelled evaluation data set to docs/evaluation_dataset.csv
    flask evaluation-report  evaluate against Table 3.1 and write docs/EVALUATION.md
"""

import click
from flask import current_app
from sqlalchemy import text

from portal.extensions import db


def register_cli(app):
    @app.cli.command("create-db")
    def create_db_command():
        """Create the app database if it does not exist. The test suite
        creates (and drops) its own DB_TEST_NAME database."""
        from portal.config import env
        from portal.helpers.db_helpers import create_databases

        names = [env("DB_NAME", "fraude")]
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

    @app.cli.command("seed-demo")
    @click.option("--reset", is_flag=True, help="Put the five demo customers back to their seeded state.")
    def seed_demo_command(reset):
        """Customer-app and fraudster demo logins (safe to run again)."""
        from portal.seeders import seed_demo_users

        seed_demo_users.run(log=click.echo)
        if reset:
            click.echo(f"Reset: {seed_demo_users.reset_demo()}")

    @app.cli.command("export-master-data")
    @click.option("--master-only", is_flag=True, help="Skip payments, alerts and cases; share only reference data.")
    def export_master_data_command(master_only):
        """Snapshot this database so teammates get it with `flask db upgrade`."""
        from alembic import command

        from portal.services.master_data import export_snapshot, new_revision, write_migration

        config = current_app.extensions["migrate"].migrate.get_config()
        revision = new_revision()
        click.echo(f"Exporting from {current_app.config['DB_NAME']}:")
        export_snapshot(revision, include_history=not master_only, log=click.echo)
        write_migration(config, revision, log=click.echo)
        # This database already holds the data, so mark the migration as applied here.
        command.stamp(config, revision)
        click.echo("Done. Commit backend/portal/master_data/ and backend/migrations/versions/, then push.")

    @app.cli.command("load-master-data")
    @click.option("--replace", is_flag=True, help="Empty the shared tables first, for an exact copy.")
    def load_master_data_command(replace):
        """Load portal/master_data/snapshot.json.gz into this database."""
        from portal.services.master_data import load_snapshot

        if replace:
            click.confirm(f"This deletes the existing rows in {current_app.config['DB_NAME']} first. Continue?",
                          abort=True)
        load_snapshot(replace=replace, log=click.echo)

    @app.cli.command("reset-rules")
    @click.option("--spec-weights", is_flag=True, help="Use the specification's starting weights (Table 4.4).")
    def reset_rules_command(spec_weights):
        """Restore default rule thresholds, weights and decision bands."""
        from portal.seeders.seed_rules import reset_rules

        reset_rules(spec_weights=spec_weights)
        click.echo("Rules restored to defaults" + (" with the specification's weights." if spec_weights else "."))

    @app.cli.command("simulate-scenario")
    @click.argument("code")
    def simulate_scenario_command(code):
        """Run one fraud story (NORMAL, R1..R9, R1+R4, R3+R6, R5+R8) and print the decision."""
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

    @app.cli.command("benchmark-indexes")
    @click.option("--size", default=2000, show_default=True)
    @click.option("--workers", default=8, show_default=True)
    @click.option("--api-url", default="http://127.0.0.1:5000/api", show_default=True,
                  help="Send the load through this ingestion API (falls back to in-process if it is not running).")
    @click.option("--in-process", is_flag=True, help="Call the engine directly instead of the API.")
    def benchmark_indexes_command(size, workers, api_url, in_process):
        """Load test with and without the composite indexes and compare."""
        from portal.services import index_benchmark

        submit, _ = _submitter(api_url, in_process)
        index_benchmark.run(size=size, workers=workers, submit=submit, log=click.echo)

    def _submitter(api_url, in_process):
        from portal.services.evaluator import api_reachable, http_submitter

        if in_process:
            return None, "IN_PROCESS"
        if api_reachable(api_url):
            return http_submitter(api_url, current_app.config["INGEST_API_KEY"]), "API"
        click.echo(f"API at {api_url} is not reachable -- running in-process instead.")
        return None, "IN_PROCESS"

    @app.cli.command("export-dataset")
    @click.option("--size", default=5000, show_default=True)
    @click.option("--seed", default=None, type=int, help="Same seed, same mix of stories.")
    @click.option("--api-url", default="http://127.0.0.1:5000/api", show_default=True)
    @click.option("--in-process", is_flag=True)
    def export_dataset_command(size, seed, api_url, in_process):
        """Evaluate a fresh labelled data set and write it to docs/evaluation_dataset.csv."""
        from portal.services import dataset

        submit, mode = _submitter(api_url, in_process)
        dataset.export(size=size, seed=seed, submit=submit, mode=mode, log=click.echo)

    @app.cli.command("evaluation-report")
    @click.option("--size", default=5000, show_default=True, help="Payments in the evaluation.")
    @click.option("--bench-size", default=2000, show_default=True, help="Payments per index-benchmark run.")
    @click.option("--seed", default=None, type=int)
    @click.option("--skip-benchmark", is_flag=True, help="Leave out the with/without-index load test.")
    @click.option("--api-url", default="http://127.0.0.1:5000/api", show_default=True)
    @click.option("--in-process", is_flag=True)
    def evaluation_report_command(size, bench_size, seed, skip_benchmark, api_url, in_process):
        """Evaluate against Table 3.1 and write docs/EVALUATION.md (+ the dataset CSV)."""
        from portal.services import eval_report

        submit, mode = _submitter(api_url, in_process)
        eval_report.run(size=size, bench_size=bench_size, seed=seed, submit=submit, mode=mode,
                        benchmark=not skip_benchmark, log=click.echo)

    @app.cli.command("export-ddl")
    def export_ddl_command():
        """Write docs/schema.sql (CREATE TABLE script) from the models."""
        from portal.services.schema_ddl import export

        click.echo(f"Wrote {export()}")

    @app.cli.command("verify-audit")
    def verify_audit_command():
        """Re-compute the audit log's hash chain."""
        from portal.services.audit_chain import verify

        result = verify()
        if result["intact"]:
            click.echo(f"Audit log intact: {result['rows']} entries, chain head {result['head_hash']}")
        else:
            raise click.ClickException(result["problem"])
