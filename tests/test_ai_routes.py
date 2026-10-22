from invoicepilot import create_app


def _app(tmp_path, api_key="test-groq-key"):
    return create_app(
        {
            "TESTING": True,
            "APP_ENV": "testing",
            "SECRET_KEY": "test-key",
            "DATABASE_PATH": str(tmp_path / "ai-route-test.sqlite3"),
            "GROQ_API_KEY": api_key,
            "GROQ_MODEL": "test-model",
        }
    )


def _invoice_form():
    return {
        "invoice_number": "AI-200",
        "vendor_name": "Juniper Design",
        "invoice_date": "2026-10-01",
        "due_date": "2026-10-30",
        "subtotal": "100.00",
        "tax": "8.00",
        "total": "115.00",
    }


def _fake_explanation():
    return {
        "summary": "Juniper Design billed $115.00.",
        "explanation": "The total does not match subtotal plus tax.",
        "relevant_fields": ["subtotal", "tax", "total"],
        "suggested_checks": ["Check the invoice for an additional fee."],
    }


def test_ai_explanation_persists_but_does_not_change_validation(monkeypatch, tmp_path):
    app = _app(tmp_path)
    client = app.test_client()
    create_response = client.post("/invoices", data=_invoice_form())
    invoice_url = create_response.headers["Location"]
    received = {}

    def fake_generate(invoice, findings, *, api_key, model):
        received["invoice"] = invoice
        received["findings"] = findings
        received["api_key"] = api_key
        received["model"] = model
        return _fake_explanation()

    monkeypatch.setattr("invoicepilot.routes.generate_invoice_explanation", fake_generate)
    detail_before = client.get(invoice_url)
    response = client.post(f"{invoice_url}/ai-explanation")
    detail_after = client.get(invoice_url)

    assert response.status_code == 303
    assert b"needs review" in detail_before.data.lower()
    assert b"needs review" in detail_after.data.lower()
    assert b"Juniper Design billed $115.00." in detail_after.data
    assert b"Check the invoice for an additional fee." in detail_after.data
    assert "processing_status" not in received["invoice"]
    assert received["findings"] == ["Total does not equal subtotal plus tax."]
    assert received["api_key"] == "test-groq-key"
    assert received["model"] == "test-model"


def test_missing_api_key_keeps_ai_disabled_and_shows_message(tmp_path):
    app = _app(tmp_path, api_key="")
    client = app.test_client()
    create_response = client.post("/invoices", data=_invoice_form())
    invoice_url = create_response.headers["Location"]

    page = client.get(invoice_url)
    response = client.post(f"{invoice_url}/ai-explanation", follow_redirects=True)

    assert b"AI is disabled" in page.data
    assert b"GROQ_API_KEY" in response.data
    assert b"needs review" in response.data.lower()


def test_unavailable_or_invalid_ai_response_does_not_change_status(monkeypatch, tmp_path):
    app = _app(tmp_path)
    client = app.test_client()
    create_response = client.post("/invoices", data=_invoice_form())
    invoice_url = create_response.headers["Location"]

    def failed_generate(*args, **kwargs):
        from invoicepilot.ai_service import AIServiceError

        raise AIServiceError("Groq returned an incomplete explanation. Please try again.")

    monkeypatch.setattr("invoicepilot.routes.generate_invoice_explanation", failed_generate)
    response = client.post(f"{invoice_url}/ai-explanation", follow_redirects=True)

    assert b"Groq returned an incomplete explanation" in response.data
    assert b"needs review" in response.data.lower()
    assert b"Juniper Design billed $115.00." not in response.data
