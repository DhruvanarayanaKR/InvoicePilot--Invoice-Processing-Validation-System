import json
from decimal import Decimal
from math import isfinite

from invoicepilot.db import get_db


def list_invoices():
    rows = get_db().execute(
        "SELECT * FROM invoices ORDER BY created_at DESC, id DESC"
    ).fetchall()
    return [_invoice_from_row(row) for row in rows]


def get_invoice(invoice_id):
    row = get_db().execute(
        "SELECT * FROM invoices WHERE id = ?", (invoice_id,)
    ).fetchone()
    return _invoice_from_row(row) if row else None


def invoice_number_exists(invoice_number):
    row = get_db().execute(
        "SELECT 1 FROM invoices WHERE invoice_number = ? COLLATE NOCASE LIMIT 1",
        (invoice_number,),
    ).fetchone()
    return row is not None


def add_invoice(invoice, exception_reasons):
    status = "needs_review" if exception_reasons else "pending"
    cursor = get_db().execute(
        """
        INSERT INTO invoices (
            invoice_number, vendor_name, invoice_date, due_date,
            subtotal, tax, total, processing_status, exception_reasons,
            source_filename
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            invoice["invoice_number"],
            invoice["vendor_name"],
            invoice["invoice_date"],
            invoice["due_date"],
            _database_amount(invoice.get("subtotal")),
            _database_amount(invoice.get("tax")),
            _database_amount(invoice.get("total")),
            status,
            json.dumps(exception_reasons),
            invoice.get("source_filename"),
        ),
    )
    get_db().commit()
    return cursor.lastrowid


def get_invoice_counts():
    row = get_db().execute(
        """
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN processing_status = 'pending' THEN 1 ELSE 0 END) AS pending,
               SUM(CASE WHEN processing_status = 'needs_review' THEN 1 ELSE 0 END) AS needs_review
        FROM invoices
        """
    ).fetchone()
    return {
        "total": row["total"],
        "pending": row["pending"] or 0,
        "needs_review": row["needs_review"] or 0,
    }


def get_invoice_ai_note(invoice_id):
    row = get_db().execute(
        "SELECT * FROM invoice_ai_notes WHERE invoice_id = ?", (invoice_id,)
    ).fetchone()
    if row is None:
        return None
    note = dict(row)
    note["relevant_fields"] = json.loads(note["relevant_fields"])
    note["suggested_checks"] = json.loads(note["suggested_checks"])
    return note


def save_invoice_ai_note(invoice_id, model, explanation):
    get_db().execute(
        """
        INSERT INTO invoice_ai_notes (
            invoice_id, model, summary, explanation, relevant_fields,
            suggested_checks, generated_at
        ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(invoice_id) DO UPDATE SET
            model = excluded.model,
            summary = excluded.summary,
            explanation = excluded.explanation,
            relevant_fields = excluded.relevant_fields,
            suggested_checks = excluded.suggested_checks,
            generated_at = CURRENT_TIMESTAMP
        """,
        (
            invoice_id,
            model,
            explanation["summary"],
            explanation["explanation"],
            json.dumps(explanation["relevant_fields"]),
            json.dumps(explanation["suggested_checks"]),
        ),
    )
    get_db().commit()


def _invoice_from_row(row):
    if row is None:
        return None
    invoice = dict(row)
    invoice["exception_reasons"] = json.loads(invoice["exception_reasons"])
    return invoice


def _database_amount(value):
    if not isinstance(value, (int, float, Decimal)):
        return None
    decimal_value = Decimal(str(value))
    if not decimal_value.is_finite() or decimal_value < 0:
        return None
    amount = float(decimal_value)
    return amount if isfinite(amount) else None
