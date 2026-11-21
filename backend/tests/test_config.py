import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from compose import environment, interpolation
from fastapi.testclient import TestClient

from app.config import EDENAI_OPEN_MODELS, Settings, get_settings
from app.main import app

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def fresh_settings() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_limit_comes_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_FILE_SIZE_MB", "1")
    assert Settings.from_env().max_file_bytes == 1024 * 1024


@pytest.mark.parametrize("value", ["0", "-1", "abc", "1.5", "1e3"])
def test_bad_limit_is_rejected_with_variable_name(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("MAX_FILE_SIZE_MB", value)
    with pytest.raises(ValueError, match="MAX_FILE_SIZE_MB"):
        Settings.from_env()


@pytest.mark.parametrize("value", ["0", "-5", "abc"])
def test_bad_timeout_is_rejected(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("LLM_TIMEOUT_S", value)
    with pytest.raises(ValueError, match="LLM_TIMEOUT_S"):
        Settings.from_env()


def test_api_refuses_to_start_with_bad_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zła konfiguracja zatrzymuje start, zamiast dawać 500 albo 413 przy każdym pliku."""
    monkeypatch.setenv("MAX_FILE_SIZE_MB", "0")
    with pytest.raises(ValueError, match="MAX_FILE_SIZE_MB"), TestClient(app):
        pass


def _env_example_names() -> set[str]:
    text = (ROOT / "env.example").read_text(encoding="utf-8")
    return set(re.findall(r"^([A-Z][A-Z0-9_]*)=", text, flags=re.MULTILINE))


def _compose_api_environment() -> set[str]:
    """Zmienne `api`, które compose bierze z powłoki albo .env: `NAZWA: ${NAZWA:-}`.

    Pusta domyślna daje domyślną wartość z config.py.
    """
    names = set()
    for key, value in environment("api").items():
        if interpolation(value) == (key, ""):
            names.add(key)
    return names


def test_empty_values_from_compose_mean_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Compose przekazuje nieustawioną zmienną jako pusty tekst (`${NAZWA:-}`)."""
    for name in _env_example_names():
        monkeypatch.setenv(name, "")
    assert Settings.from_env() == Settings()


def test_compose_passes_every_setting_to_api() -> None:
    names = _env_example_names()
    assert "MAX_FILE_SIZE_MB" in names
    assert names <= _compose_api_environment()


def test_env_example_leaves_model_url_to_the_provider() -> None:
    """`cp env.example .env` nie może ustawić adresu modelu (M1.5, recenzja #1; M1.7).

    Pusty `LLM_BASE_URL` daje adres dostawcy: Ollama z compose (`LLM_OLLAMA_URL`), localhost albo Eden AI.
    """
    text = (ROOT / "env.example").read_text(encoding="utf-8")
    values = re.findall(r"^LLM_BASE_URL=(.*)$", text, flags=re.MULTILINE)
    assert values == [""], f"LLM_BASE_URL w env.example ma być pusty, jest {values}"


# LLM_CONTEXT_TOKENS: ten sam kontekst dla serwera modelu i budżetu analizy (prośba Mikołaja, K3).
def test_context_tokens_come_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_CONTEXT_TOKENS", "65536")
    assert Settings.from_env().llm_context_tokens == 65536


@pytest.mark.parametrize("value", ["0", "-1", "abc", "1.5", "4096", "8191"])
def test_bad_or_too_small_context_is_rejected(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """Odpowiedź modelu ma do 4096 tokenów: kontekst poniżej 8192 nie zostawia miejsca na dokument."""
    monkeypatch.setenv("LLM_CONTEXT_TOKENS", value)
    with pytest.raises(ValueError, match="LLM_CONTEXT_TOKENS"):
        Settings.from_env()


def test_ollama_gets_the_same_context_as_the_analysis() -> None:
    """Serwer z mniejszym kontekstem przycina prompt po cichu (K1), więc obie strony biorą jedną zmienną."""
    assert interpolation(environment("ollama")["OLLAMA_CONTEXT_LENGTH"]) == (
        "LLM_CONTEXT_TOKENS",
        str(Settings().llm_context_tokens),
    )


@pytest.mark.parametrize(("name", "default"), [("LLM_TEMPERATURE", 0), ("LLM_REASONING_EFFORT", "none")])
@pytest.mark.parametrize("value", [None, "", "off"])
def test_temperature_and_reasoning_use_defaults_unless_switched_off(
    monkeypatch: pytest.MonkeyPatch, name: str, default: int | str, value: str | None,
) -> None:
    if value is None:
        monkeypatch.delenv(name, raising=False)
    else:
        monkeypatch.setenv(name, value)
    assert getattr(Settings.from_env(), name.lower()) == (None if value == "off" else default)


@pytest.mark.parametrize(("name", "value"), [
    ("LLM_TEMPERATURE", "warm"),
    ("LLM_TEMPERATURE", "nan"),
    ("LLM_TEMPERATURE", "2.1"),
    ("LLM_REASONING_EFFORT", "maybe"),
    ("LLM_STRICT_SCHEMA", "maybe"),
    ("LLM_MAX_TOKENS", "0"),
    ("LLM_MAX_TOKENS", "8.5"),
    ("LLM_CONNECT_TIMEOUT_S", "0"),
    ("LLM_CONNECT_TIMEOUT_S", "inf"),
    ("LLM_EXTRA_BODY", "{"),
    ("LLM_EXTRA_BODY", "[]"),
    ("LLM_EXTRA_BODY", '{"bad":NaN}'),
])
def test_api_refuses_to_start_with_invalid_llm_configuration(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str,
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name), TestClient(app):
        pass


def test_eden_request_options_are_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MAX_TOKENS", "8192")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.25")
    monkeypatch.setenv("LLM_REASONING_EFFORT", "low")
    monkeypatch.setenv("LLM_STRICT_SCHEMA", "false")
    monkeypatch.setenv("LLM_CONNECT_TIMEOUT_S", "2.5")
    monkeypatch.setenv("LLM_EXTRA_BODY", '{"chat_template_kwargs":{"enable_thinking":false}}')
    settings = Settings.from_env()
    assert settings.llm_max_tokens == 8192
    assert settings.llm_temperature == 0.25
    assert settings.llm_reasoning_effort == "low"
    assert settings.llm_strict_schema is False
    assert settings.llm_connect_timeout_s == 2.5
    assert settings.llm_extra_body == {"chat_template_kwargs": {"enable_thinking": False}}


def test_k31_options_match_in_sample_compose_and_settings() -> None:
    names = {
        "LLM_MAX_TOKENS", "LLM_TEMPERATURE", "LLM_REASONING_EFFORT",
        "LLM_STRICT_SCHEMA", "LLM_EXTRA_BODY", "LLM_CONNECT_TIMEOUT_S",
    }
    assert names <= _env_example_names() & _compose_api_environment()
    assert all(hasattr(Settings(), name.lower()) for name in names)


def test_d11_settings_are_listed_for_compose_and_have_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    names = {"LLM_ANALYSIS_BUDGET_S", "LLM_MAX_ATTEMPTS"}
    assert names <= _env_example_names() & _compose_api_environment()
    for name in names:
        monkeypatch.delenv(name, raising=False)
    settings = Settings.from_env()
    assert (settings.llm_analysis_budget_s, settings.llm_max_attempts) == (170.0, 2)
    for name in names:
        monkeypatch.setenv(name, "")
    assert Settings.from_env() == settings


@pytest.mark.parametrize("attempts", [1, 3])
def test_d11_settings_read_valid_nondefaults(monkeypatch: pytest.MonkeyPatch, attempts: int) -> None:
    monkeypatch.setenv("LLM_ANALYSIS_BUDGET_S", "125.5")
    monkeypatch.setenv("LLM_MAX_ATTEMPTS", str(attempts))
    settings = Settings.from_env()
    assert (settings.llm_analysis_budget_s, settings.llm_max_attempts) == (125.5, attempts)


@pytest.mark.parametrize(("name", "value"), [
    ("LLM_ANALYSIS_BUDGET_S", "0"),
    ("LLM_ANALYSIS_BUDGET_S", "-1"),
    ("LLM_ANALYSIS_BUDGET_S", "nan"),
    ("LLM_ANALYSIS_BUDGET_S", "inf"),
    ("LLM_ANALYSIS_BUDGET_S", "abc"),
    ("LLM_MAX_ATTEMPTS", "0"),
    ("LLM_MAX_ATTEMPTS", "4"),
    ("LLM_MAX_ATTEMPTS", "1.5"),
])
def test_invalid_d11_settings_prevent_api_startup(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name), TestClient(app):
        pass


# M1.7: dostawca modelu (D9). Klucze w testach są syntetyczne; nic nie idzie do sieci.
EDEN_ENV = {
    "LLM_PROVIDER": "edenai",
    "LLM_BASE_URL": "https://api.eu.edenai.run/v3",
    "LLM_MODEL": "ovhcloud/Qwen3.5-9B",
    "LLM_API_KEY": "synthetic-eden-key-123",
}
OLLAMA_IN_COMPOSE = "http://ollama:11434/v1"


def _set(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> None:
    for name, value in env.items():
        monkeypatch.setenv(name, value)


def test_provider_defaults_to_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert Settings().llm_provider == "ollama"
    assert Settings.from_env().llm_provider == "ollama"
    monkeypatch.setenv("LLM_PROVIDER", "")
    assert Settings.from_env().llm_provider == "ollama"


@pytest.mark.parametrize("value", ["openai", "eden", "ollama2", "local"])
def test_unknown_provider_stops_start(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("LLM_PROVIDER", value)
    with pytest.raises(ValueError, match="LLM_PROVIDER"), TestClient(app):
        pass


def test_provider_name_ignores_case_and_spaces(monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, {**EDEN_ENV, "LLM_PROVIDER": " EdenAI "})
    assert Settings.from_env().llm_provider == "edenai"


def test_eden_settings_are_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, EDEN_ENV)
    settings = Settings.from_env()
    assert (settings.llm_provider, settings.llm_base_url, settings.llm_model) == (
        "edenai", "https://api.eu.edenai.run/v3", "ovhcloud/Qwen3.5-9B",
    )


@pytest.mark.parametrize("key", ["", "ollama", "   ", "Ollama", " OLLAMA "])
def test_eden_without_key_stops_start_without_showing_it(monkeypatch: pytest.MonkeyPatch, key: str) -> None:
    _set(monkeypatch, {**EDEN_ENV, "LLM_API_KEY": key})
    with pytest.raises(ValueError, match="LLM_API_KEY"), TestClient(app):
        pass


@pytest.mark.parametrize("url", [
    "http://ollama:11434/v1",
    "http://localhost:11434/v1",
    "http://api.edenai.run/v3",
    "https://api.edenai.run.evil.test/v3",
    "https://evil.test/api.edenai.run/v3",
    "https://api.edenai.run@evil.test/v3",
    "https://user@api.edenai.run/v3",
    "https://api.edenai.run:8443/v3",
    "https://api.edenai.run:abc/v3",
    "https://api.openai.com/v1",
    "api.edenai.run/v3",
])
def test_eden_with_foreign_host_stops_start(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    _set(monkeypatch, {**EDEN_ENV, "LLM_BASE_URL": url})
    with pytest.raises(ValueError, match="LLM_BASE_URL") as error, TestClient(app):
        pass
    assert EDEN_ENV["LLM_API_KEY"] not in str(error.value)


@pytest.mark.parametrize("url", [
    "https://api.edenai.run/v3", "https://api.eu.edenai.run/v3", "https://API.EdenAI.run:443/v3/",
])
def test_eden_hosts_are_accepted(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    _set(monkeypatch, {**EDEN_ENV, "LLM_BASE_URL": url})
    assert Settings.from_env().llm_base_url == url


@pytest.mark.parametrize("model", [
    "qwen3.5:4b", "openai/gpt-4o", "anthropic/claude-sonnet-4-5", "ovhcloud/qwen3.5-9b", "ovhcloud/Qwen3.5-9B ", "",
])
def test_eden_with_model_outside_open_list_stops_start(model: str) -> None:
    with pytest.raises(ValueError, match="LLM_MODEL"):
        Settings(
            llm_provider="edenai", llm_base_url=EDEN_ENV["LLM_BASE_URL"],
            llm_api_key=EDEN_ENV["LLM_API_KEY"], llm_model=model,
        )


def test_eden_model_from_env_outside_list_stops_start(monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, {**EDEN_ENV, "LLM_MODEL": "openai/gpt-4o"})
    with pytest.raises(ValueError, match="LLM_MODEL"), TestClient(app):
        pass


def test_every_open_model_is_a_qwen35_9b_route() -> None:
    """D9 pkt 7 i 8: tylko otwarty Qwen3.5-9B (Apache-2.0). Inny model wymaga wpisu w DECISIONS.md."""
    assert EDENAI_OPEN_MODELS
    assert all(re.search(r"qwen3\.5-9b", model, flags=re.IGNORECASE) for model in EDENAI_OPEN_MODELS)
    decisions = (ROOT / "DECISIONS.md").read_text(encoding="utf-8")
    assert all(f"`{model}`" in decisions for model in EDENAI_OPEN_MODELS)


def test_eden_without_url_gets_eden_not_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    """Compose daje Ollamę tylko dostawcy `ollama`: pusty adres przy `edenai` to Eden AI."""
    _set(monkeypatch, {**EDEN_ENV, "LLM_BASE_URL": "", "LLM_OLLAMA_URL": OLLAMA_IN_COMPOSE})
    assert Settings.from_env().llm_base_url == "https://api.edenai.run/v3"


def test_ollama_without_url_gets_compose_service_or_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "")
    monkeypatch.setenv("LLM_OLLAMA_URL", OLLAMA_IN_COMPOSE)
    assert Settings.from_env().llm_base_url == OLLAMA_IN_COMPOSE
    monkeypatch.delenv("LLM_OLLAMA_URL")
    assert Settings.from_env().llm_base_url == "http://localhost:11434/v1"


def test_explicit_url_wins_for_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "http://gpu-box:11434/v1")
    monkeypatch.setenv("LLM_OLLAMA_URL", OLLAMA_IN_COMPOSE)
    assert Settings.from_env().llm_base_url == "http://gpu-box:11434/v1"


def test_compose_gives_ollama_url_separately_from_llm_base_url() -> None:
    env = environment("api")
    assert interpolation(env["LLM_PROVIDER"]) == ("LLM_PROVIDER", "")
    assert interpolation(env["LLM_BASE_URL"]) == ("LLM_BASE_URL", "")
    assert env["LLM_OLLAMA_URL"] == OLLAMA_IN_COMPOSE


def test_env_example_has_provider_and_no_eden_key() -> None:
    text = (ROOT / "env.example").read_text(encoding="utf-8")
    assert re.search(r"^LLM_PROVIDER=(ollama)?$", text, flags=re.MULTILINE)
    assert "D9" in text
    assert re.findall(r"^LLM_API_KEY=(.*)$", text, flags=re.MULTILINE) == ["ollama"]


def test_info_reports_eden_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, EDEN_ENV)
    response = TestClient(app).get("/api/info")
    assert response.json() == {"llm": "edenai", "model": "ovhcloud/Qwen3.5-9B"}


@pytest.mark.parametrize("model", ["openai/gpt-4o", "ovhcloud/Qwen3.5-9B", "qwen3.5:4b"])
def test_ollama_provider_cannot_point_at_eden(monkeypatch: pytest.MonkeyPatch, model: str) -> None:
    """Recenzja M1.7 #1: `ollama` z adresem Eden AI omijałby listę modeli otwartych (D9 pkt 7)."""
    _set(monkeypatch, {**EDEN_ENV, "LLM_PROVIDER": "ollama", "LLM_MODEL": model})
    with pytest.raises(ValueError, match="LLM_PROVIDER=edenai"), TestClient(app):
        pass


@pytest.mark.parametrize("name", ["LLM_PROVIDER", "LLM_MODEL"])
def test_key_pasted_into_wrong_variable_is_not_in_the_error(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """Recenzja M1.7 #3, D9 pkt 3: komunikat błędu trafia do logu, więc nie powtarza wartości."""
    _set(monkeypatch, {**EDEN_ENV, name: EDEN_ENV["LLM_API_KEY"]})
    with pytest.raises(ValueError, match=name) as error:
        Settings.from_env()
    assert EDEN_ENV["LLM_API_KEY"].lower() not in str(error.value).lower()
