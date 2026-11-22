from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app


def test_info_returns_only_the_default_provider_and_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(app.dependency_overrides, get_settings, lambda: Settings())
    response = TestClient(app).get("/api/info")
    assert response.status_code == 200
    assert response.json() == {"llm": "ollama", "model": "qwen3.5:4b"}


def test_info_is_open_with_jwt_and_does_not_expose_other_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    @dataclass(frozen=True)
    class EdenSettings(Settings):
        llm_provider: str = "edenai"

    settings = EdenSettings(
        llm_model="ovhcloud/Qwen3.5-9B",
        llm_base_url="https://api.eu.edenai.run/v3",
        llm_api_key="synthetic-eden-key",
        llm_extra_body={"test_parameter": "synthetic-extra-body"},
        jwt_enabled=True,
        jwt_secret="a" * 32,
    )
    monkeypatch.setitem(app.dependency_overrides, get_settings, lambda: settings)
    response = TestClient(app).get("/api/info")
    assert response.status_code == 200
    assert response.json() == {"llm": "edenai", "model": "ovhcloud/Qwen3.5-9B"}
    for private in ("llm_api_key", "llm_base_url", settings.llm_api_key, settings.llm_base_url, "synthetic-extra-body"):
        assert private not in response.text
