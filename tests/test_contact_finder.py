"""
Tests for contacts/contact_finder.py

Run with:  pytest tests/test_contact_finder.py -v

call_llm is faked via monkeypatch so no real API calls happen.
"""

import json

import pytest

from contacts import contact_finder


def test_find_contact_parses_found_response(monkeypatch):
    fake_reply = json.dumps(
        {
            "status": "found",
            "name": "Jane Doe",
            "title": "VP Engineering",
            "email": None,
        }
    )
    monkeypatch.setattr(contact_finder, "call_llm", lambda system, user, max_tokens=512: fake_reply)

    result = contact_finder.find_contact("Example Corp", "Leadership page text mentioning Jane Doe, VP Engineering")

    assert result["status"] == "found"
    assert result["name"] == "Jane Doe"
    assert result["title"] == "VP Engineering"
    assert result["linkedin_url"] is None
    assert result["source"] == "company website text"


def test_find_contact_parses_not_found_response(monkeypatch):
    fake_reply = json.dumps({"status": "not_found", "name": None, "title": None, "email": None})
    monkeypatch.setattr(contact_finder, "call_llm", lambda system, user, max_tokens=512: fake_reply)

    result = contact_finder.find_contact("Example Corp", "Generic homepage text with no names")

    assert result["status"] == "not_found"
    assert result["name"] is None
    assert result["source"] is None


def test_find_contact_raises_on_invalid_json(monkeypatch):
    monkeypatch.setattr(contact_finder, "call_llm", lambda system, user, max_tokens=512: "not json")

    with pytest.raises(ValueError):
        contact_finder.find_contact("Example Corp", "some text")


def test_find_contact_raises_on_missing_keys(monkeypatch):
    fake_reply = json.dumps({"status": "found"})  # missing name/title/email
    monkeypatch.setattr(contact_finder, "call_llm", lambda system, user, max_tokens=512: fake_reply)

    with pytest.raises(ValueError):
        contact_finder.find_contact("Example Corp", "some text")


def test_find_contact_falls_back_to_not_found_on_unexpected_status(monkeypatch):
    fake_reply = json.dumps({"status": "maybe", "name": "Someone", "title": "Someone", "email": None})
    monkeypatch.setattr(contact_finder, "call_llm", lambda system, user, max_tokens=512: fake_reply)

    result = contact_finder.find_contact("Example Corp", "some text")

    assert result["status"] == "not_found"
