import json

import httpx
import pytest
from pydantic import ValidationError
from streamlit.testing.v1 import AppTest
from pathlib import Path

from cleardiligence.models import Assessment, CompanyInput, Source
from cleardiligence.providers import ClaudeExtractor, Extraction, GeminiExtractor, LiveResearch, create_extractor, llm_configuration


def company():
    return CompanyInput(name="Example Vendor", country="United States")


def gemini_response(text='{"items": []}', finish="STOP"):
    return {"candidates": [{"finishReason": finish, "content": {"parts": [{"text": text}]}}]}


def test_gemini_request_is_structured_and_key_is_header_only():
    captured = {}
    def handler(request):
        captured["request"] = request
        return httpx.Response(200, json=gemini_response())
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = GeminiExtractor(api_key="mock-secret", client=client).extract(company(), [], "entity")
    assert result == Extraction(items=[])
    request = captured["request"]
    assert request.url.host == "generativelanguage.googleapis.com"
    assert request.url.path.endswith("/gemini-3.8-flash:generateContent")
    assert "mock-secret" not in str(request.url)
    assert request.headers["x-goog-api-key"] == "mock-secret"
    body = json.loads(request.content)
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["generationConfig"]["responseJsonSchema"]["properties"]["items"]["maxItems"] == 20
    assert "untrusted" in body["systemInstruction"]["parts"][0]["text"]


@pytest.mark.parametrize("payload", [
    gemini_response(finish="MAX_TOKENS"),
    {"promptFeedback": {"blockReason": "SAFETY"}},
    gemini_response("not valid JSON"),
    gemini_response('{"items": [], "invented_extra_field": true}'),
    gemini_response('{"items": [{"field": "invented"}]}'),
])
def test_gemini_rejects_incomplete_blocked_or_invalid_output(payload):
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload))) as client:
        with pytest.raises(ValueError):
            GeminiExtractor(api_key="mock-secret", client=client).extract(company(), [], "entity")


def test_gemini_http_failure_does_not_embed_secret_in_url_error():
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429, json={"error": "quota"}))) as client:
        with pytest.raises(httpx.HTTPStatusError) as error:
            GeminiExtractor(api_key="mock-secret", client=client).extract(company(), [], "entity")
    assert "mock-secret" not in str(error.value)


def test_auto_uses_gemini_without_anthropic(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "mock-secret")
    config = llm_configuration()
    assert config["provider"] == "gemini" and config["configured"]
    assert isinstance(create_extractor(), GeminiExtractor)


def test_explicit_provider_wins_when_both_keys_exist(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "mock-anthropic")
    monkeypatch.setenv("GEMINI_API_KEY", "mock-gemini")
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    assert isinstance(create_extractor(), ClaudeExtractor)
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    assert isinstance(create_extractor(), GeminiExtractor)
    monkeypatch.setenv("LLM_PROVIDER", "unsupported")
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        create_extractor()


def test_gemini_output_passes_through_existing_evidence_gate():
    s = Source(id="s1", title="Company", url="https://example.com", content="Example Vendor is a United States contractor.")
    output = {"items": [{"field": "ownership", "source_id": "s1", "value": "Invented Owner", "quote": s.content, "relation": "same", "relation_reason": "Name and country match", "nature": "Profile"}]}
    class Search:
        def search(self, *args, **kwargs): return [s]
    a = Assessment(company=company(), mode="Live")
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=gemini_response(json.dumps(output))))) as client:
        LiveResearch(Search(), GeminiExtractor(api_key="mock-secret", client=client)).entity(a)
    assert not a.findings[0].evidence_valid
    assert a.findings[0].verification.value == "Unverified"


def test_gemini_model_id_cannot_change_request_destination():
    with pytest.raises(ValueError, match="model ID"):
        GeminiExtractor(api_key="mock-secret", model="https://other.example/steal")


def test_gemini_ui_requires_search_but_not_anthropic(tmp_path, monkeypatch):
    monkeypatch.setenv("CLEARDILIGENCE_DB", str(tmp_path / "gemini-ui.db"))
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "mock-secret")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30).run()
    app.button(key="nav_New assessment").click().run()
    app.radio(key="research_mode").set_value("Live").run()
    assert not app.exception
    assert any("Tavily" in item.value for item in app.warning)
    assert all("Anthropic" not in item.value for item in app.warning)


def test_reload_configuration_reads_saved_provider_settings_only(tmp_path, monkeypatch):
    from cleardiligence.providers import reload_provider_configuration
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_PROVIDER=gemini\nGEMINI_MODEL=gemini-3.8-flash\nGEMINI_API_KEY=mock-new-key\nCLEARDILIGENCE_DB=unintended.db\n")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("GEMINI_MODEL", "old-model")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("CLEARDILIGENCE_DB", "active.db")
    reload_provider_configuration(env_file)
    assert llm_configuration()["provider"] == "gemini"
    assert llm_configuration()["model"] == "gemini-3.8-flash"
    assert llm_configuration()["configured"]
    import os
    assert os.getenv("CLEARDILIGENCE_DB") == "active.db"


def test_sidebar_shows_gemini_without_key_and_reload_applies_model(tmp_path, monkeypatch):
    import cleardiligence.providers as providers
    monkeypatch.setenv("CLEARDILIGENCE_DB", str(tmp_path / "config-ui.db"))
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GEMINI_MODEL", "old-model")
    def reload_settings(path):
        monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")
    monkeypatch.setattr(providers, "reload_provider_configuration", reload_settings)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30).run()
    assert not app.exception
    captions = [node.value for node in app.caption]
    assert any("Google Gemini" in value and "Not configured" in value for value in captions)
    assert any("old-model" in value for value in captions)
    app.button(key="reload_configuration").click().run()
    assert not app.exception
    assert any("Model: gemini-3.8-flash" in node.value for node in app.caption)
