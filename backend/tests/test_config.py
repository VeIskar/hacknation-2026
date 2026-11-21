import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from compose import environment, interpolation
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app

ROOT = Path(__file__).resolve().parents[2]
# W kontenerze `api` model jest w serwisie `ollama`, nie na localhost (M1.5).
COMPOSE_DEFAULTS = {"LLM_BASE_URL": "http://ollama:11434/v1"}


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

    Pusta domyślna daje domyślną wartość z config.py. Wyjątki z inną domyślną: COMPOSE_DEFAULTS.
    """
    names = set()
    for key, value in environment("api").items():
        parsed = interpolation(value)
        if parsed == (key, COMPOSE_DEFAULTS.get(key, "")):
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


def test_env_example_does_not_override_compose_defaults() -> None:
    """`cp env.example .env` nie może nadpisać domyślnych wartości compose (M1.5, recenzja #1).

    Pusta wartość w .env daje w compose wartość domyślną (`${NAZWA:-…}`), a lokalnie domyślną z config.py.
    """
    text = (ROOT / "env.example").read_text(encoding="utf-8")
    for name in COMPOSE_DEFAULTS:
        values = re.findall(rf"^{name}=(.*)$", text, flags=re.MULTILINE)
        assert values == [""], f"{name} w env.example ma być pusty, jest {values}"


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
