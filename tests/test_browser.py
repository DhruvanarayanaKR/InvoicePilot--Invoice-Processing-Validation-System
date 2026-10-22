from threading import Thread

import pytest
from werkzeug.serving import make_server

from invoicepilot import create_app
from invoicepilot.browser import check_dashboard, create_invoice_via_browser


@pytest.fixture
def live_app_server(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "APP_ENV": "testing",
            "SECRET_KEY": "test-key",
            "DATABASE_PATH": str(tmp_path / "browser-test.sqlite3"),
        }
    )
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_playwright_dashboard_and_invoice_review_flow(live_app_server):
    dashboard = check_dashboard(live_app_server)
    assert dashboard["heading"] == "Invoice dashboard"
    assert "No invoices yet" in dashboard["content"]

    result = create_invoice_via_browser(
        live_app_server,
        {
            "invoice_number": "PW-5001",
            "vendor_name": "Browser Test Supplies",
            "invoice_date": "2026-08-01",
            "due_date": "2026-08-31",
            "subtotal": "100.00",
            "tax": "8.00",
            "total": "125.00",
        },
    )

    assert result["invoice_number"] == "PW-5001"
    assert result["status"] == "needs review"
    assert "not been approved or paid" in result["needs_review"].lower()
