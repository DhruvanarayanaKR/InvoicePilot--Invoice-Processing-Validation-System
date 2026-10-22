import sqlite3

from flask import current_app, g


def get_db():
    if "db" not in g:
        connection = sqlite3.connect(current_app.config["DATABASE_PATH"])
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        g.db = connection
    return g.db


def close_db(_error=None):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_number TEXT,
            vendor_name TEXT,
            invoice_date TEXT,
            due_date TEXT,
            subtotal REAL CHECK (subtotal >= 0),
            tax REAL CHECK (tax >= 0),
            total REAL CHECK (total >= 0),
            processing_status TEXT NOT NULL DEFAULT 'pending'
                CHECK (processing_status IN ('pending', 'needs_review')),
            exception_reasons TEXT NOT NULL DEFAULT '[]',
            source_filename TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    _allow_incomplete_invoice_records(db)
    db.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_invoices_created_at
            ON invoices (created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_invoices_number
            ON invoices (invoice_number COLLATE NOCASE);
        CREATE TABLE IF NOT EXISTS invoice_ai_notes (
            invoice_id INTEGER PRIMARY KEY REFERENCES invoices (id) ON DELETE CASCADE,
            model TEXT NOT NULL,
            summary TEXT NOT NULL,
            explanation TEXT NOT NULL,
            relevant_fields TEXT NOT NULL,
            suggested_checks TEXT NOT NULL,
            generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    db.commit()


def _allow_incomplete_invoice_records(db):
    columns = {
        row["name"]: row for row in db.execute("PRAGMA table_info(invoices)").fetchall()
    }
    nullable_fields = {
        "invoice_number",
        "vendor_name",
        "invoice_date",
        "due_date",
        "subtotal",
        "tax",
        "total",
    }
    if not any(columns[field]["notnull"] for field in nullable_fields):
        return

    db.executescript(
        """
        CREATE TABLE invoices_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_number TEXT,
            vendor_name TEXT,
            invoice_date TEXT,
            due_date TEXT,
            subtotal REAL CHECK (subtotal >= 0),
            tax REAL CHECK (tax >= 0),
            total REAL CHECK (total >= 0),
            processing_status TEXT NOT NULL DEFAULT 'pending'
                CHECK (processing_status IN ('pending', 'needs_review')),
            exception_reasons TEXT NOT NULL DEFAULT '[]',
            source_filename TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO invoices_new (
            id, invoice_number, vendor_name, invoice_date, due_date,
            subtotal, tax, total, processing_status, exception_reasons,
            source_filename, created_at
        )
        SELECT
            id, invoice_number, vendor_name, invoice_date, due_date,
            subtotal, tax, total, processing_status, exception_reasons,
            source_filename, created_at
        FROM invoices;
        DROP TABLE invoices;
        ALTER TABLE invoices_new RENAME TO invoices;
        """
    )
