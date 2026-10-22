from decimal import Decimal

import pytest

from invoicepilot import create_app


@pytest.fixture
def app(tmp_path):
    database_path = tmp_path / "test-invoices.sqlite3"
    return create_app(
        {
            "TESTING": True,
            "APP_ENV": "testing",
            "SECRET_KEY": "test-key",
            "DATABASE_PATH": str(database_path),
        }
    )


@pytest.fixture
def client(app):
    return app.test_client()


def valid_form(**overrides):
    values = {
        "invoice_number": "INV-1001",
        "vendor_name": "Acme Supplies",
        "invoice_date": "2026-05-01",
        "due_date": "2026-05-31",
        "subtotal": "100.00",
        "tax": "8.00",
        "total": "108.00",
        "source_filename": "invoice.pdf",
    }
    values.update(overrides)
    return values


def test_dashboard_loads_with_empty_state_and_counts(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"No invoices yet" in response.data
    assert b"Total records" in response.data


def test_create_invoice_and_view_details(client):
    response = client.post("/invoices", data=valid_form())

    assert response.status_code == 303
    detail = client.get(response.headers["Location"])
    assert detail.status_code == 200
    assert b"INV-1001" in detail.data
    assert b"Acme Supplies" in detail.data
    assert b"pending" in detail.data
    assert b"not approved or paid" in detail.data.lower()

    dashboard = client.get("/")
    assert b"1 total" in dashboard.data


def test_invalid_form_is_rejected_with_helpful_errors(client):
    response = client.post(
        "/invoices",
        data=valid_form(vendor_name="", subtotal="not-a-number"),
    )

    assert response.status_code == 400
    assert b"Vendor is required." in response.data
    assert b"Subtotal must be a valid non-negative number." in response.data
    assert b"0 total" in response.data


@pytest.mark.parametrize("amount", ["-1", "NaN", "Infinity", "1e9999"])
def test_negative_or_non_finite_amount_is_rejected(client, amount):
    response = client.post("/invoices", data=valid_form(subtotal=amount))

    assert response.status_code == 400
    assert b"Subtotal must be a valid non-negative number." in response.data


def test_duplicate_invoice_is_saved_for_human_review(client):
    client.post("/invoices", data=valid_form())
    response = client.post(
        "/invoices",
        data=valid_form(invoice_number="inv-1001", vendor_name="Another Vendor"),
    )

    detail = client.get(response.headers["Location"])
    assert response.status_code == 303
    assert b"needs review" in detail.data.lower()
    assert b"duplicates an existing record" in detail.data
    assert b"not been approved or paid" in detail.data


def test_arithmetic_discrepancy_is_saved_for_human_review(client):
    response = client.post("/invoices", data=valid_form(total="110.00"))

    detail = client.get(response.headers["Location"])
    assert b"needs review" in detail.data.lower()
    assert b"Total does not equal subtotal plus tax." in detail.data


def test_records_persist_after_app_is_recreated(app):
    client = app.test_client()
    client.post("/invoices", data=valid_form())

    second_app = create_app(
        {
            "TESTING": True,
            "APP_ENV": "testing",
            "SECRET_KEY": "test-key",
            "DATABASE_PATH": app.config["DATABASE_PATH"],
        }
    )
    response = second_app.test_client().get("/")

    assert response.status_code == 200
    assert b"INV-1001" in response.data


def test_unknown_invoice_returns_not_found(client):
    assert client.get("/invoices/999").status_code == 404


def test_money_parser_returns_decimal_values():
    from invoicepilot.validation import parse_invoice_form

    parsed, errors = parse_invoice_form(valid_form())

    assert errors == []
    assert parsed["subtotal"] == Decimal("100.00")


def test_demo_seed_is_repeatable_and_development_only(tmp_path):
    app = create_app(
        {
            "TESTING": False,
            "APP_ENV": "development",
            "SECRET_KEY": "test-key",
            "DATABASE_PATH": str(tmp_path / "seeded.sqlite3"),
        }
    )
    runner = app.test_cli_runner()

    first_run = runner.invoke(args=["seed-demo"])
    second_run = runner.invoke(args=["seed-demo"])

    assert first_run.exit_code == 0
    assert "Added 2 demo invoice(s)" in first_run.output
    assert second_run.exit_code == 0
    assert "Added 0 demo invoice(s)" in second_run.output

    app.config["APP_ENV"] = "production"
    production_run = runner.invoke(args=["seed-demo"])
    assert production_run.exit_code != 0
