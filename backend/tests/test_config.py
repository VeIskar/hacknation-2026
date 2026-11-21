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
