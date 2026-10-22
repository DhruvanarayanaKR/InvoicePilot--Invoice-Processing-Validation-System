import os

import click
from flask import Flask, flash, redirect, url_for

from config import Config
from invoicepilot.db import close_db, init_db
from invoicepilot.models import add_invoice, invoice_number_exists
from invoicepilot.routes import main


def create_app(test_config=None):
    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder="../templates",
        static_folder="../static",
    )
    app.config.from_object(Config)
    app.config["DATABASE_PATH"] = os.environ.get(
        "DATABASE_PATH", os.path.join(app.instance_path, "invoicepilot.sqlite3")
    )

    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)
    app.register_blueprint(main)
    app.teardown_appcontext(close_db)

    @app.errorhandler(413)
    def request_too_large(_error):
        flash("Files must be 10 MB or smaller.", "error")
        return redirect(url_for("main.index")), 303

    with app.app_context():
        init_db()

    @app.cli.command("seed-demo")
    def seed_demo():
        """Add a small, repeatable sample dataset in development only."""
        if app.config["APP_ENV"] != "development" or app.testing:
            raise click.ClickException(
                "Demo data can only be seeded in a non-test development environment."
            )

        examples = [
            {
                "invoice_number": "DEMO-1001",
                "vendor_name": "Northstar Office Supplies",
                "invoice_date": "2026-01-12",
                "due_date": "2026-02-11",
                "subtotal": 240.00,
                "tax": 19.20,
                "total": 259.20,
                "source_filename": "demo-office-supplies.pdf",
            },
            {
                "invoice_number": "DEMO-1002",
                "vendor_name": "Cedar Cloud Services",
                "invoice_date": "2026-01-18",
                "due_date": "2026-02-17",
                "subtotal": 500.00,
                "tax": 40.00,
                "total": 545.00,
                "source_filename": "demo-cloud-services.pdf",
            },
        ]

        added = 0
        for example in examples:
            if not invoice_number_exists(example["invoice_number"]):
                reasons = (
                    ["Total does not equal subtotal plus tax."]
                    if example["total"] != example["subtotal"] + example["tax"]
                    else []
                )
                add_invoice(example, reasons)
                added += 1

        click.echo(f"Added {added} demo invoice(s); existing demo records were left unchanged.")

    return app
