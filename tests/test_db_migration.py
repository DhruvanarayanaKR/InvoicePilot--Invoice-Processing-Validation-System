import sqlite3

from invoicepilot import create_app


def test_existing_day_one_database_is_migrated_without_losing_records(tmp_path):
    database_path = tmp_path / "existing.sqlite3"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_number TEXT NOT NULL,
            vendor_name TEXT NOT NULL,
            invoice_date TEXT NOT NULL,
            due_date TEXT NOT NULL,
            subtotal REAL NOT NULL CHECK (subtotal >= 0),
            tax REAL NOT NULL CHECK (tax >= 0),
            total REAL NOT NULL CHECK (total >= 0),
            processing_status TEXT NOT NULL DEFAULT 'pending'
                CHECK (processing_status IN ('pending', 'needs_review')),
            exception_reasons TEXT NOT NULL DEFAULT '[]',
            source_filename TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO invoices (
            invoice_number, vendor_name, invoice_date, due_date,
            subtotal, tax, total
        ) VALUES ('OLD-1', 'Existing Vendor', '2026-01-01', '2026-01-31', 10, 1, 11);
        """
    )
    connection.commit()
    connection.close()

    app = create_app(
        {
            "TESTING": True,
            "APP_ENV": "testing",
            "SECRET_KEY": "test-key",
            "DATABASE_PATH": str(database_path),
        }
    )

    response = app.test_client().get("/")
    connection = sqlite3.connect(database_path)
    columns = connection.execute("PRAGMA table_info(invoices)").fetchall()
    connection.close()

    assert response.status_code == 200
    assert b"OLD-1" in response.data
    assert not next(column for column in columns if column[1] == "invoice_number")[3]
