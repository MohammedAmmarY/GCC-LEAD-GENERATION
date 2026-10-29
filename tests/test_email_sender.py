import json

import pytest

from ai import email_generator


@pytest.fixture
def prompts(monkeypatch):
    captured = {}

    def fake_llm(system, user, max_tokens=1024):
        captured["system"] = system
        captured["user"] = user
        return json.dumps({"subject": "s", "body": "b"})

    monkeypatch.setattr(email_generator, "call_llm", fake_llm)
    return captured


def _set_sender(monkeypatch, name="", title="", company="", offer=""):
    for key, value in (("SENDER_NAME", name), ("SENDER_TITLE", title), ("SENDER_COMPANY", company), ("SENDER_OFFER", offer)):
        monkeypatch.setattr(email_generator.settings, key, value)


def _generate():
    return email_generator.generate_outreach_email("Acme", "summary", "evidence", "notes")


def test_sender_details_are_included_when_configured(monkeypatch, prompts):
    _set_sender(monkeypatch, "Priya Nair", "Director", "Example Advisory", "We help engineering firms set up India centers.")

    _generate()

    user = prompts["user"]
    assert "Sender details" in user
    assert "Name: Priya Nair" in user
    assert "Title: Director" in user
    assert "Company: Example Advisory" in user
    assert "What the sender's company offers: We help engineering firms set up India centers." in user
    assert "[Your Name]" not in user


def test_only_the_configured_sender_fields_appear(monkeypatch, prompts):
    _set_sender(monkeypatch, name="Priya Nair")

    _generate()

    assert "Name: Priya Nair" in prompts["user"]
    assert "Title:" not in prompts["user"]
    assert "Company:" not in prompts["user"]


def test_without_sender_details_the_prompt_asks_for_a_placeholder(monkeypatch, prompts):
    _set_sender(monkeypatch)

    _generate()

    assert "No sender details were provided" in prompts["user"]
    assert "[Your Name]" in prompts["user"]
    assert email_generator.build_sender_block() == ""


def test_system_prompt_forbids_inventing_the_offer(monkeypatch, prompts):
    _set_sender(monkeypatch)

    _generate()

    assert "ONLY the" in prompts["system"]
    assert "Never invent services, clients, case studies or results" in prompts["system"]