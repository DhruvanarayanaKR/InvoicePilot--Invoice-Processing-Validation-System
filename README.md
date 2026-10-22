# InvoicePilot AI

InvoicePilot is a local portfolio prototype for invoice intake, deterministic validation, and browser workflow verification. It uses Flask and SQLite; uploaded PDFs are read with `pdfplumber`, Excel workbooks with `openpyxl`, and browser checks with Playwright for Python.

**Safety boundary:** the app can set records to `pending` or `needs_review` only. It never approves or pays invoices. AI only explains invoice fields and deterministic findings; it cannot change validation results.

## Requirements

- Python 3.10 or newer
- Windows PowerShell, macOS, or Linux terminal

## Setup on Windows (PowerShell)

Run from the folder containing `app.py` and `requirements.txt`:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
Copy-Item .env.example .env
flask --app app run --debug
```

Open `http://127.0.0.1:5000`. The SQLite database is initialized automatically at `instance\invoicepilot.sqlite3`.

If activation is blocked by PowerShell, keep the machine's execution policy unchanged and use the environment's interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m flask --app app run --debug
```

## Features

- Add invoice records manually and retain them in SQLite.
- Upload a text-based PDF for best-effort field extraction.
- Import an `.xlsx` file using the **Download import template** workbook.
- Export the invoice register as `.xlsx`.
- View invoice details, exception reasons, and pending/review counts.
- Use the browser tests to submit an invoice and verify the exception-review flow.
- Optionally request a Groq-generated invoice summary and discrepancy explanation.

Required invoice fields are invoice number, vendor, invoice date, due date, subtotal, tax, and total. Manual entry rejects missing or invalid values. PDF and Excel ingestion keep incomplete rows and flag missing or malformed values for human review. Duplicate invoice numbers and total/subtotal/tax discrepancies are also flagged.

Excel files use the canonical columns in the downloadable template. Imported `processing_status` and exception text are not trusted; the application recalculates status and exceptions using its own deterministic rules. This lets UiPath read/write the spreadsheet and orchestrate processing without becoming the source of invoice decisions.

Uploads are limited to 10 MB. Invoice numbers may repeat in the database so duplicates can be retained and flagged instead of silently discarded. Database initialization migrates the earlier Day 1 schema while preserving existing invoice records.

## Tests

Run the complete suite:

```powershell
python -m pytest
```

The Playwright browser test requires Chromium; install it with `python -m playwright install chromium` as shown in setup. It launches the local Flask test app, opens the dashboard, submits an invoice with an arithmetic discrepancy, and checks that the record is visibly flagged for review.

## Development sample data

Sample data is opt-in and only available when `APP_ENV=development`:

```powershell
flask --app app seed-demo
```

The seed command is repeatable and does not create duplicate demo invoice numbers.

## Optional Groq explanations

AI is disabled unless `GROQ_API_KEY` is configured. Create a local `.env` file from `.env.example`, add your key there, and optionally set `GROQ_MODEL` to a model enabled for your Groq account. Never put the API key in source code or commit `.env`. Groq account access, model availability, and usage limits are controlled by Groq; the app does not require AI to run.

Open an invoice and select **Generate AI summary and explanation**. The app sends only the displayed invoice fields and the deterministic exception reasons to Groq; it does not send the source PDF. The returned summary, explanation, relevant fields, and suggested reviewer checks are stored locally in SQLite. Provider failures and malformed responses are shown as errors and do not change invoice status. AI output may be inaccurate, so a human must verify it against the original invoice.

## Project layout

```text
app.py                    Flask entry point
config.py                 Environment-based settings
invoicepilot/
  db.py                   SQLite setup and Day 1 schema migration
  models.py               Invoice persistence
  routes.py               Dashboard, PDF, Excel, and optional AI endpoints
  ai_service.py           Groq explanation client and response validation
  validation.py           Deterministic invoice validation
  pdf_extractor.py        PDF text extraction and field parsing
  excel_service.py        UiPath-friendly Excel template/import/export
  browser.py              Playwright browser workflow
templates/                Flask/Jinja pages
static/                   CSS
tests/                    Route, persistence, Excel, PDF, and browser tests
```

## Current boundaries and next extensions

- PDF extraction is pattern-based and works best on text-based PDFs with common field labels. Scanned PDFs and OCR are out of scope.
- There is no authentication, cloud deployment, or payment integration.
- Groq explanations are optional and require the user to configure their own key; they never alter validation outcomes.
- UiPath can orchestrate Excel records now; a later integration can add an authenticated API if the workflow needs one.
