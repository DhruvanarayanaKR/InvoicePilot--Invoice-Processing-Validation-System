from io import BytesIO

from invoicepilot import create_app


def test_pdf_extractor_reads_common_invoice_patterns():
    from invoicepilot.pdf_extractor import parse_invoice_text

    sample = """
    Invoice No: INV-2048
    Vendor: Northwind Supplies
    Invoice Date: 2026-02-15
    Due Date: 2026-03-17
    Subtotal $245.00
    Tax $19.60
    Total $264.60
    """

    extracted = parse_invoice_text(sample)

    assert extracted["invoice_number"] == "INV-2048"
    assert extracted["vendor_name"] == "Northwind Supplies"
    assert extracted["invoice_date"] == "2026-02-15"
    assert extracted["due_date"] == "2026-03-17"
    assert extracted["subtotal"] == "245.00"
    assert extracted["tax"] == "19.60"
    assert extracted["total"] == "264.60"


def test_pdf_upload_route_saves_uploaded_invoice(monkeypatch, tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "APP_ENV": "testing",
            "SECRET_KEY": "test-key",
            "DATABASE_PATH": str(tmp_path / "test-upload.sqlite3"),
        }
    )

    def fake_extract(file_obj):
        return {
            "invoice_number": "UP-101",
            "vendor_name": "Lakeview Studio",
            "invoice_date": "2026-06-04",
            "due_date": "2026-07-04",
            "subtotal": "900.00",
            "tax": "72.00",
            "total": "972.00",
        }

    import invoicepilot.routes as routes_module

    monkeypatch.setattr(routes_module, "extract_invoice_from_pdf", fake_extract)

    client = app.test_client()
    response = client.post(
        "/upload",
        data={"invoice_file": (BytesIO(b"fake pdf bytes"), "invoice.pdf")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 303
    assert b"Lakeview Studio" in client.get(response.headers["Location"]).data
    assert b"pending" in client.get(response.headers["Location"]).data.lower()


def test_pdf_with_missing_fields_is_saved_for_review(monkeypatch, tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "APP_ENV": "testing",
            "SECRET_KEY": "test-key",
            "DATABASE_PATH": str(tmp_path / "incomplete-upload.sqlite3"),
        }
    )

    monkeypatch.setattr(
        "invoicepilot.routes.extract_invoice_from_pdf",
        lambda file_obj: {"invoice_number": "PARTIAL-1", "subtotal": "25.00"},
    )

    client = app.test_client()
    response = client.post(
        "/upload",
        data={"invoice_file": (BytesIO(b"fake pdf bytes"), "partial.pdf")},
        content_type="multipart/form-data",
    )

    detail = client.get(response.headers["Location"])
    assert response.status_code == 303
    assert detail.status_code == 200
    assert b"needs review" in detail.data.lower()
    assert b"Vendor is missing." in detail.data
    assert b"Not extracted" in detail.data
