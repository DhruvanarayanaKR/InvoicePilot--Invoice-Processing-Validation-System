from typing import Any


def check_dashboard(url: str) -> dict[str, Any]:
    """Open the dashboard in Chromium and return basic page information."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded")
            heading = page.locator("h1").first.text_content() or ""
            body = page.locator("body").text_content() or ""
            return {
                "title": page.title(),
                "heading": heading.strip(),
                "content": body.strip(),
                "url": page.url,
            }
        finally:
            browser.close()


def create_invoice_via_browser(url: str, invoice: dict[str, str]) -> dict[str, Any]:
    """Submit an invoice through the UI and report its visible processing result."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded")
            for field in (
                "invoice_number",
                "vendor_name",
                "invoice_date",
                "due_date",
                "subtotal",
                "tax",
                "total",
            ):
                page.get_by_label(_field_label(field), exact=True).fill(invoice[field])
            page.get_by_role("button", name="Save invoice record").click()
            page.wait_for_url("**/invoices/*")

            return {
                "invoice_number": page.locator("h1").text_content().strip(),
                "status": page.locator(".detail-heading .status").text_content().strip(),
                "needs_review": page.locator(".review-notice").text_content().strip(),
                "url": page.url,
            }
        finally:
            browser.close()


def _field_label(field: str) -> str:
    return {
        "invoice_number": "Invoice number",
        "vendor_name": "Vendor",
        "invoice_date": "Invoice date",
        "due_date": "Due date",
        "subtotal": "Subtotal",
        "tax": "Tax",
        "total": "Total",
    }[field]
