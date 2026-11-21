import re
from collections.abc import Iterator
from pathlib import Path

import pytest
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
    """Nazwy z listy `environment:` serwisu `api` (bez parsera YAML, który nie jest zależnością)."""
    lines = (ROOT / "docker-compose.yml").read_text(encoding="utf-8").splitlines()
    start = lines.index("  api:")
    names: set[str] = set()
    in_env = False
    for line in lines[start + 1 :]:
        if re.match(r"^  \S", line):  # następny serwis
            break
        if re.match(r"^    \S", line):
            in_env = line.strip() == "environment:"
            continue
        # Forma `NAZWA: ${NAZWA:-}`: wartość z powłoki albo .env, a gdy brak, pusta (domyślna).
        # Wyjątki z wartością domyślną compose: COMPOSE_DEFAULTS.
        match = re.match(r"^      ([A-Z][A-Z0-9_]*): \$\{([A-Z][A-Z0-9_]*):-([^}]*)\}\s*$", line)
        if match and match.group(3) != COMPOSE_DEFAULTS.get(match.group(1), ""):
            continue
        if in_env and match and match.group(1) == match.group(2):
            names.add(match.group(1))
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
