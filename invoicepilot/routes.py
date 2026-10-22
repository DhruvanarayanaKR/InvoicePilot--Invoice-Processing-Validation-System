import sqlite3

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from invoicepilot.excel_service import (
    create_import_template,
    export_invoices_to_excel,
    import_invoices_from_excel,
)
from invoicepilot.ai_service import AIServiceError, generate_invoice_explanation
from invoicepilot.models import (
    add_invoice,
    get_invoice,
    get_invoice_ai_note,
    get_invoice_counts,
    invoice_number_exists,
    list_invoices,
    save_invoice_ai_note,
)
from invoicepilot.pdf_extractor import extract_invoice_from_pdf
from invoicepilot.validation import parse_invoice_form, validate_invoice


main = Blueprint("main", __name__)


@main.get("/")
def index():
    return render_template(
        "index.html",
        invoices=list_invoices(),
        counts=get_invoice_counts(),
        errors=[],
        form_values={},
    )


@main.post("/invoices")
def create_invoice():
    invoice, errors = parse_invoice_form(request.form)
    if errors:
        return (
            render_template(
                "index.html",
                invoices=list_invoices(),
                counts=get_invoice_counts(),
                errors=errors,
                form_values=request.form,
            ),
            400,
        )

    reasons = validate_invoice(
        invoice,
        duplicate=invoice_number_exists(invoice["invoice_number"]),
    )
    try:
        invoice_id = add_invoice(invoice, reasons)
    except sqlite3.Error:
        current_app.logger.exception("Could not save invoice record")
        flash("The invoice could not be saved. Please try again.", "error")
        return redirect(url_for("main.index")), 303

    if reasons:
        flash(
            "Invoice saved and flagged for human review: " + " ".join(reasons),
            "warning",
        )
    else:
        flash("Invoice record saved with pending status.", "success")
    return redirect(url_for("main.invoice_detail", invoice_id=invoice_id), code=303)


@main.post("/upload")
def upload_invoice():
    file = request.files.get("invoice_file")
    if file is None or not file.filename:
        flash("Please select a PDF invoice before uploading.", "error")
        return redirect(url_for("main.index")), 303

    filename = secure_filename(file.filename)
    if not filename or not filename.lower().endswith(".pdf"):
        flash("Only PDF invoice files are supported for upload.", "error")
        return redirect(url_for("main.index")), 303

    try:
        extracted = extract_invoice_from_pdf(file)
    except Exception:
        current_app.logger.exception("Failed to read uploaded PDF")
        flash("The PDF could not be read. Please check the file and try again.", "error")
        return redirect(url_for("main.index")), 303

    invoice, reasons = _prepare_review_invoice(
        extracted,
        source_filename=filename,
    )

    try:
        invoice_id = add_invoice(invoice, reasons)
    except sqlite3.Error:
        current_app.logger.exception("Could not save uploaded invoice")
        flash("The uploaded invoice could not be saved.", "error")
        return redirect(url_for("main.index")), 303

    if reasons:
        flash(
            "Uploaded invoice saved for human review. " + " ".join(reasons),
            "warning",
        )
    else:
        flash("Uploaded invoice saved with pending status.", "success")
    return redirect(url_for("main.invoice_detail", invoice_id=invoice_id), code=303)


@main.get("/excel/export")
def export_invoices_excel():
    workbook = export_invoices_to_excel(list_invoices())
    return (
        workbook.getvalue(),
        200,
        {
            "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "Content-Disposition": "attachment; filename=invoicepilot_invoices.xlsx",
        },
    )


@main.get("/excel/template")
def download_excel_template():
    workbook = create_import_template()
    return (
        workbook.getvalue(),
        200,
        {
            "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "Content-Disposition": "attachment; filename=invoicepilot_import_template.xlsx",
        },
    )


@main.post("/excel/import")
def import_invoices_excel():
    file = request.files.get("excel_file")
    if file is None or not file.filename:
        flash("Please select an Excel file to import.", "error")
        return redirect(url_for("main.index")), 303

    filename = secure_filename(file.filename)
    if not filename or not filename.lower().endswith(".xlsx"):
        flash("Only Excel files are supported for import.", "error")
        return redirect(url_for("main.index")), 303

    try:
        records = import_invoices_from_excel(file)
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("main.index")), 303
    except Exception:
        current_app.logger.exception("Could not import Excel invoice file")
        flash("The Excel file could not be read. Please confirm the template format.", "error")
        return redirect(url_for("main.index")), 303

    if not records:
        flash("The Excel file did not contain any invoice rows.", "warning")
        return redirect(url_for("main.index")), 303

    added = 0
    flagged = 0
    for record in records:
        invoice, reasons = _prepare_review_invoice(
            record,
            source_filename=record.get("source_filename") or filename,
        )
        try:
            add_invoice(invoice, reasons)
        except sqlite3.Error:
            current_app.logger.exception("Could not save imported Excel invoice")
            flash(
                "Excel import stopped because a row could not be saved. "
                f"{added} earlier row(s) were saved; check the application log.",
                "error",
            )
            return redirect(url_for("main.index")), 303
        added += 1
        flagged += bool(reasons)

    flash(
        f"Imported {added} invoice record(s); {flagged} flagged for human review.",
        "warning" if flagged else "success",
    )
    return redirect(url_for("main.index")), 303


@main.get("/invoices/<int:invoice_id>")
def invoice_detail(invoice_id):
    invoice = get_invoice(invoice_id)
    if invoice is None:
        return render_template("invoice_detail.html", invoice=None, ai_note=None), 404
    return render_template(
        "invoice_detail.html",
        invoice=invoice,
        ai_note=get_invoice_ai_note(invoice_id),
        ai_configured=bool(current_app.config["GROQ_API_KEY"]),
    )


@main.post("/invoices/<int:invoice_id>/ai-explanation")
def explain_invoice(invoice_id):
    invoice = get_invoice(invoice_id)
    if invoice is None:
        return render_template("invoice_detail.html", invoice=None, ai_note=None), 404

    invoice_fields = {
        field: invoice.get(field)
        for field in (
            "invoice_number",
            "vendor_name",
            "invoice_date",
            "due_date",
            "subtotal",
            "tax",
            "total",
        )
    }
    model = current_app.config["GROQ_MODEL"]
    try:
        explanation = generate_invoice_explanation(
            invoice_fields,
            invoice["exception_reasons"],
            api_key=current_app.config["GROQ_API_KEY"],
            model=model,
        )
        save_invoice_ai_note(invoice_id, model, explanation)
    except AIServiceError as error:
        current_app.logger.warning("AI explanation was not generated: %s", error)
        flash(str(error), "error")
    except sqlite3.Error:
        current_app.logger.exception("Could not save the AI explanation")
        flash("The explanation was generated but could not be saved.", "error")
    else:
        flash("AI explanation generated. Validation status was not changed.", "success")

    return redirect(url_for("main.invoice_detail", invoice_id=invoice_id), code=303)


def _prepare_review_invoice(values, source_filename=None):
    form_values = {}
    for field in (
        "invoice_number",
        "vendor_name",
        "invoice_date",
        "due_date",
        "subtotal",
        "tax",
        "total",
    ):
        value = values.get(field)
        form_values[field] = "" if value is None else str(value).strip()

    form_values["source_filename"] = source_filename or values.get("source_filename") or ""
    invoice, _form_errors = parse_invoice_form(form_values)
    duplicate = bool(
        invoice["invoice_number"]
        and invoice_number_exists(invoice["invoice_number"])
    )
    reasons = validate_invoice(invoice, duplicate=duplicate)

    for field in ("invoice_number", "vendor_name", "invoice_date", "due_date"):
        if not invoice[field]:
            invoice[field] = None
    for field in ("subtotal", "tax", "total"):
        if not hasattr(invoice[field], "is_finite") or not invoice[field].is_finite():
            invoice[field] = None
    return invoice, reasons
