"""
Tests for ai/email_generator.py

Run with:  pytest tests/test_email_generator.py -v

call_llm is faked via monkeypatch so no real API calls happen.
"""

import json

import pytest

from ai import email_generator


def test_generate_outreach_email_parses_valid_response(monkeypatch):
    fake_reply = json.dumps(
        {
            "subject": "Quick question about your engineering operations",
            "body": "Hello Jane, ... [Your Name]",
        }
    )
    monkeypatch.setattr(email_generator, "call_llm", lambda system, user, max_tokens=512: fake_reply)

    result = email_generator.generate_outreach_email(
        company_name="Example Corp",
        research_summary="Makes industrial sensors.",
        india_gcc_evidence="No mention of India found.",
        qualification_notes="[Heuristic] Possible fit.",
        contact_name="Jane Doe",
        contact_title="VP Engineering",
    )

    assert result["subject"] == "Quick question about your engineering operations"
    assert "[Your Name]" in result["body"]


def test_generate_outreach_email_works_without_contact_name(monkeypatch):
    fake_reply = json.dumps({"subject": "Subject line", "body": "Hello, ... [Your Name]"})
    monkeypatch.setattr(email_generator, "call_llm", lambda system, user, max_tokens=512: fake_reply)

    result = email_generator.generate_outreach_email(
        company_name="Example Corp",
        research_summary="Makes industrial sensors.",
        india_gcc_evidence="No mention of India found.",
        qualification_notes="[Heuristic] Possible fit.",
    )

    assert "subject" in result
    assert "body" in result


def test_generate_outreach_email_raises_on_invalid_json(monkeypatch):
    monkeypatch.setattr(email_generator, "call_llm", lambda system, user, max_tokens=512: "not json")

    with pytest.raises(ValueError):
        email_generator.generate_outreach_email(
            company_name="Example Corp",
            research_summary="text",
            india_gcc_evidence="text",
            qualification_notes="text",
        )


def test_generate_outreach_email_raises_on_missing_keys(monkeypatch):
    fake_reply = json.dumps({"subject": "only a subject"})  # missing "body"
    monkeypatch.setattr(email_generator, "call_llm", lambda system, user, max_tokens=512: fake_reply)

    with pytest.raises(ValueError):
        email_generator.generate_outreach_email(
            company_name="Example Corp",
            research_summary="text",
            india_gcc_evidence="text",
            qualification_notes="text",
        )
