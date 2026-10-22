import re
from typing import Dict, Optional

import pdfplumber


def extract_text_from_pdf(file_obj) -> str:
    """Read a PDF file object and return all text content."""
    pages = []
    with pdfplumber.open(file_obj) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages.append(text)
    return "\n".join(page for page in pages if page)


def _first_match(pattern: str, text: str) -> Optional[str]:
    match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    if not match:
        return None
    return match.group(1).strip() if match.lastindex else match.group(0).strip()


def parse_invoice_text(text: str) -> Dict[str, object]:
    """Extract a small set of invoice values from raw text in a best-effort way."""
    normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not normalized:
        return {}

    invoice = {}

    invoice_number = _first_match(
        r"(?:invoice\s*(?:no|number)|inv(?:oice)?\s*#)\s*[:#-]?\s*([A-Z0-9-]+)", normalized
    )
    if invoice_number:
        invoice["invoice_number"] = invoice_number

    vendor_name = _first_match(
        r"(?:vendor|supplier|from)\s*[:\-]?\s*([A-Za-z0-9&.,' /-]+)", normalized
    )
    if vendor_name:
        invoice["vendor_name"] = vendor_name

    date_matches = re.findall(r"\b(?:\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}|\d{1,2}-[A-Za-z]{3}-\d{4})\b", normalized)
    if date_matches:
        invoice["invoice_date"] = date_matches[0]
    if len(date_matches) > 1:
        invoice["due_date"] = date_matches[1]

    # Use full-word matches so labels like "subtotal" do not accidentally match "total".
    amount_keys = ["subtotal", "tax", "total"]
    for key in amount_keys:
        pattern = rf"\b{key}\b\s*[:$]?\s*\$?\s*(\d+(?:\.\d{{2}})?)"
        match = re.search(pattern, normalized, re.IGNORECASE)
        if match:
            invoice[key] = match.group(1)

    if "total" not in invoice:
        total_matches = re.findall(r"\btotal\b\s*[:$]?\s*\$?\s*(\d+(?:\.\d{2})?)", normalized, re.IGNORECASE)
        if total_matches:
            invoice["total"] = total_matches[-1]

    return invoice


def extract_invoice_from_pdf(file_obj) -> Dict[str, object]:
    """Return extracted invoice keys and let the app decide whether they are valid."""
    text = extract_text_from_pdf(file_obj)
    return parse_invoice_text(text)
