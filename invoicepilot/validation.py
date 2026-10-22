from datetime import date
from decimal import Decimal, InvalidOperation
from math import isfinite


REQUIRED_FIELDS = (
    ("invoice_number", "Invoice number"),
    ("vendor_name", "Vendor"),
    ("invoice_date", "Invoice date"),
    ("due_date", "Due date"),
    ("subtotal", "Subtotal"),
    ("tax", "Tax"),
    ("total", "Total"),
)
AMOUNT_FIELDS = ("subtotal", "tax", "total")


def parse_invoice_form(form):
    """Normalize submitted form values and return field errors without saving."""
    invoice = {}
    errors = []

    for field, label in REQUIRED_FIELDS:
        value = form.get(field, "").strip()
        if not value:
            errors.append(f"{label} is required.")
        invoice[field] = value

    for field, label in (("invoice_date", "Invoice date"), ("due_date", "Due date")):
        value = invoice.get(field, "")
        if value:
            try:
                date.fromisoformat(value)
            except ValueError:
                errors.append(f"{label} must be a valid date.")

    for field in AMOUNT_FIELDS:
        value = invoice.get(field, "")
        if value:
            try:
                amount = Decimal(value)
                if not amount.is_finite() or amount < 0 or not isfinite(float(amount)):
                    raise InvalidOperation
                invoice[field] = amount
            except InvalidOperation:
                errors.append(f"{field.capitalize()} must be a valid non-negative number.")

    source_filename = form.get("source_filename", "").strip()
    invoice["source_filename"] = source_filename or None
    return invoice, errors


def validate_invoice(invoice, duplicate=False):
    """Return deterministic exception messages; exceptions always require human review."""
    reasons = []
    for field, label in REQUIRED_FIELDS:
        value = invoice.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            reasons.append(f"{label} is missing.")

    if duplicate:
        reasons.append("Invoice number duplicates an existing record.")

    for field, label in (("invoice_date", "Invoice date"), ("due_date", "Due date")):
        value = invoice.get(field)
        if value and isinstance(value, str):
            try:
                date.fromisoformat(value)
            except ValueError:
                reasons.append(f"{label} is invalid.")

    for field in AMOUNT_FIELDS:
        value = invoice.get(field)
        if value is not None and (
            not isinstance(value, Decimal) or not value.is_finite() or value < 0
        ):
            reasons.append(f"{field.capitalize()} is invalid.")

    subtotal = invoice.get("subtotal")
    tax = invoice.get("tax")
    total = invoice.get("total")
    if all(isinstance(value, Decimal) for value in (subtotal, tax, total)):
        if abs((subtotal + tax) - total) > Decimal("0.01"):
            reasons.append("Total does not equal subtotal plus tax.")

    return reasons
