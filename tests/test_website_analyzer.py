"""
Tests for ai/website_analyzer.py

Run with:  pytest tests/test_website_analyzer.py -v

call_llm is faked via monkeypatch so no real API calls happen - these
tests check our JSON parsing and validation logic, not the LLM itself.
"""

import json

import pytest

from ai import website_analyzer


def test_analyze_company_website_parses_valid_response(monkeypatch):
    fake_reply = json.dumps(
        {
            "india_presence_status": "clear_india_gcc_evidence",
            "india_gcc_evidence": "The Careers page mentions an 'India Engineering Capability Center' in Bengaluru.",
            "research_summary": "The company makes industrial sensors and automation equipment.",
            "qualification_notes": "[Heuristic] Already has an India GCC, so may be lower priority.",
        }
    )
    monkeypatch.setattr(website_analyzer, "call_llm", lambda system, user, max_tokens=1024: fake_reply)

    result = website_analyzer.analyze_company_website("Example Corp", "some website text")

    assert result["india_presence_status"] == "clear_india_gcc_evidence"
    assert "Bengaluru" in result["india_gcc_evidence"]


def test_analyze_company_website_raises_on_invalid_json(monkeypatch):
    monkeypatch.setattr(website_analyzer, "call_llm", lambda system, user, max_tokens=1024: "not json at all")

    with pytest.raises(ValueError):
        website_analyzer.analyze_company_website("Example Corp", "some website text")


def test_analyze_company_website_raises_on_missing_keys(monkeypatch):
    fake_reply = json.dumps({"india_presence_status": "no_evidence_found"})  # missing other required keys
    monkeypatch.setattr(website_analyzer, "call_llm", lambda system, user, max_tokens=1024: fake_reply)

    with pytest.raises(ValueError):
        website_analyzer.analyze_company_website("Example Corp", "some website text")


def test_analyze_company_website_falls_back_on_unexpected_status(monkeypatch):
    fake_reply = json.dumps(
        {
            "india_presence_status": "definitely_yes",  # not one of our four valid categories
            "india_gcc_evidence": "text",
            "research_summary": "text",
            "qualification_notes": "text",
        }
    )
    monkeypatch.setattr(website_analyzer, "call_llm", lambda system, user, max_tokens=1024: fake_reply)

    result = website_analyzer.analyze_company_website("Example Corp", "some website text")

    assert result["india_presence_status"] == website_analyzer.INSUFFICIENT_INFORMATION
