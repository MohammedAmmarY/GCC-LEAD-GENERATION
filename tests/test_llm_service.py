"""
Tests for ai/llm_service.py

Run with:  pytest tests/test_llm_service.py -v

genai.Client is replaced with a small fake class so no network call or
real API key is ever needed to run these tests.
"""

import pytest

from ai import llm_service


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeModels:
    def __init__(self, reply_text):
        self._reply_text = reply_text

    def generate_content(self, **kwargs):
        return FakeResponse(self._reply_text)


class FakeGenaiClient:
    def __init__(self, api_key, reply_text="hello from gemini"):
        self.models = FakeModels(reply_text)


def test_call_llm_raises_without_api_key(monkeypatch):
    monkeypatch.setattr(llm_service.settings, "GEMINI_API_KEY", None)

    with pytest.raises(RuntimeError):
        llm_service.call_llm("system prompt", "user prompt")


def test_call_llm_returns_text_from_response(monkeypatch):
    monkeypatch.setattr(llm_service.settings, "GEMINI_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(
        llm_service.genai,
        "Client",
        lambda api_key, **kwargs: FakeGenaiClient(api_key, reply_text='{"hello": "world"}'),
    )

    result = llm_service.call_llm("system prompt", "user prompt")

    assert result == '{"hello": "world"}'
