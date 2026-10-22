import json
from types import SimpleNamespace

import pytest

from invoicepilot import ai_service
from invoicepilot.ai_service import AIServiceError, generate_invoice_explanation


class FakeGroqClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.chat = SimpleNamespace(completions=self)
        self.request = None

    def create(self, **kwargs):
        self.request = kwargs
        if self.error:
            raise self.error
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self.response)
                )
            ]
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


def invoice_fields():
    return {
        "invoice_number": "AI-101",
        "vendor_name": "Maple Street Studio",
        "invoice_date": "2026-10-01",
        "due_date": "2026-10-31",
        "subtotal": 100.0,
        "tax": 8.0,
        "total": 115.0,
        "processing_status": "pending",
        "source_filename": "private-invoice.pdf",
    }


def valid_response():
    return json.dumps(
        {
            "summary": "Maple Street Studio billed $115.00.",
            "explanation": "The total is $7.00 above subtotal plus tax.",
            "relevant_fields": ["subtotal", "tax", "total"],
            "suggested_checks": ["Check for an omitted fee."],
        }
    )


def test_successful_response_uses_only_invoice_fields_and_findings(monkeypatch):
    client = FakeGroqClient(valid_response())
    monkeypatch.setattr(ai_service, "Groq", lambda api_key: client)

    result = generate_invoice_explanation(
        invoice_fields(),
        ["Total does not equal subtotal plus tax."],
        api_key="test-key",
        model="test-model",
    )

    sent_context = json.loads(client.request["messages"][1]["content"])
    assert result["summary"] == "Maple Street Studio billed $115.00."
    assert sent_context["invoice_fields"]["invoice_number"] == "AI-101"
    assert "processing_status" not in sent_context["invoice_fields"]
    assert "source_filename" not in sent_context["invoice_fields"]
    assert sent_context["deterministic_validation_findings"] == [
        "Total does not equal subtotal plus tax."
    ]
    assert client.request["response_format"] == {"type": "json_object"}
    assert client.request["model"] == "test-model"


def test_missing_api_key_returns_explicit_configuration_error(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "environment-key")

    with pytest.raises(AIServiceError, match="GROQ_API_KEY"):
        generate_invoice_explanation(invoice_fields(), [], api_key="")


@pytest.mark.parametrize("content", ["not json", '{"summary": "Only a summary"}'])
def test_malformed_or_incomplete_response_is_rejected(monkeypatch, content):
    client = FakeGroqClient(content)
    monkeypatch.setattr(ai_service, "Groq", lambda api_key: client)

    with pytest.raises(AIServiceError, match="Groq returned"):
        generate_invoice_explanation(
            invoice_fields(), [], api_key="test-key", model="test-model"
        )


def test_provider_failure_is_reported_as_safe_service_error(monkeypatch):
    client = FakeGroqClient(error=RuntimeError("provider details"))
    monkeypatch.setattr(ai_service, "Groq", lambda api_key: client)

    with pytest.raises(AIServiceError, match="Check your connection"):
        generate_invoice_explanation(
            invoice_fields(), [], api_key="test-key", model="test-model"
        )
