"""Konfiguracja ze zmiennych środowiskowych (DELEGACJA.md, rozdz. 5).

Endpointy biorą ją przez Depends(get_settings), więc testy podmieniają ją przez
app.dependency_overrides zamiast ustawiać zmienne środowiskowe.
"""

import json
import math
import os
from dataclasses import dataclass
from functools import cache
from typing import Any
from urllib.parse import urlsplit

MB = 1024 * 1024
# Min. kontekst zostawia miejsce na dokument przy domyślnej odpowiedzi Ollamy (4096 tokenów).
MIN_CONTEXT_TOKENS = 8192
_TRUE = {"1", "true", "yes", "on"}
_REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh"}

# D9 (M1.7): Ollama lokalnie albo Eden AI organizatorów. Inny dostawca zatrzymuje start.
PROVIDERS = ("ollama", "edenai")
OLLAMA_URL = "http://localhost:11434/v1"
EDENAI_URL = "https://api.edenai.run/v3"
EDENAI_HOSTS = frozenset({"api.edenai.run", "api.eu.edenai.run"})
# D9 pkt 7 i 8: przez Eden AI tylko otwarty Qwen3.5-9B (Apache-2.0, wagi publiczne).
# Lista tras z publicznego katalogu Eden AI; nowy model wymaga wpisu w DECISIONS.md.
EDENAI_OPEN_MODELS = frozenset({
    "ovhcloud/Qwen3.5-9B",
    "ionos/Qwen/Qwen3.5-9B",
    "flexai/Qwen3.5-9B",
    "flexai/Qwen3.5-9B@eu",
    "greenference/qwen3.5-9b",
    "tensorx/qwen/qwen3.5-9b",
    "deepinfra/Qwen/Qwen3.5-9B",
    "together_ai/Qwen/Qwen3.5-9B",
})


def _env(name: str, default: str) -> str:
    return os.environ.get(name, "").strip() or default


def _env_positive_int(name: str, default: int) -> int:
    raw = _env(name, str(default))
    if not raw.isdigit() or int(raw) <= 0:
        raise ValueError(f"{name} ma być dodatnią liczbą całkowitą, jest {raw!r}")
    return int(raw)


def _env_positive_float(name: str, default: float) -> float:
    raw = _env(name, str(default))
    try:
        value = float(raw)
    except ValueError:
        value = math.nan
    if not (math.isfinite(value) and value > 0):
        raise ValueError(f"{name} ma być dodatnią liczbą, jest {raw!r}")
    return value


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    return value in _TRUE if value else default


def _is_eden_url(url: str) -> bool:
    """Tylko https na hoście Eden AI, bez użytkownika w adresie i bez obcego portu."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    return (
        parts.scheme == "https"
        and (parts.hostname or "") in EDENAI_HOSTS
        and "@" not in parts.netloc
        and port in (None, 443)
    )


def _env_temperature() -> float | None:
    raw = _env("LLM_TEMPERATURE", "0").lower()
    if raw == "off":
        return None
    if raw == "0":
        return 0
    try:
        return float(raw)
    except ValueError:
        raise ValueError("LLM_TEMPERATURE ma być liczbą od 0 do 2 albo 'off'") from None


def _env_extra_body() -> dict[str, Any] | None:
    raw = _env("LLM_EXTRA_BODY", "")
    if not raw:
        return None
    error = "LLM_EXTRA_BODY ma być obiektem JSON"
    try:
        body = json.loads(raw)
        if isinstance(body, dict):
            json.dumps(body, allow_nan=False)
            return body
    except (ValueError, RecursionError):
        raise ValueError(error) from None
    raise ValueError(error)


@dataclass(frozen=True)
class Settings:
    max_file_size_mb: int = 10
    jwt_enabled: bool = False
    jwt_secret: str | None = None
    jwt_algorithm: str = "HS256"
    llm_base_url: str = OLLAMA_URL
    llm_model: str = "qwen3.5:4b"
    llm_api_key: str = "ollama"
    llm_timeout_s: float = 120.0
    # Kontekst serwera modelu w tokenach. Ten sam dla Ollamy (compose) i budżetu analizy (K3).
    llm_context_tokens: int = 32768
    llm_fixture: str | None = None
    ocr_lang: str = "pol"
    add_validators: bool = True
    llm_max_tokens: int | None = None
    llm_temperature: float | None = 0
    llm_reasoning_effort: str | None = "none"
    llm_strict_schema: bool = True
    llm_extra_body: dict[str, Any] | None = None
    llm_connect_timeout_s: float = 10.0
    llm_analysis_budget_s: float = 170.0
    llm_max_attempts: int = 2
    llm_provider: str = "ollama"

    def __post_init__(self) -> None:
        self._check_provider()
        # Bez tego 0 albo -1 dawałoby 413 dla każdego poprawnego pliku.
        if isinstance(self.max_file_size_mb, bool) or self.max_file_size_mb <= 0:
            raise ValueError(f"MAX_FILE_SIZE_MB ma być dodatnią liczbą całkowitą, jest {self.max_file_size_mb!r}")
        if not (math.isfinite(self.llm_timeout_s) and self.llm_timeout_s > 0):
            raise ValueError(f"LLM_TIMEOUT_S ma być dodatnią liczbą, jest {self.llm_timeout_s!r}")
        if isinstance(self.llm_context_tokens, bool) or self.llm_context_tokens < MIN_CONTEXT_TOKENS:
            raise ValueError(
                f"LLM_CONTEXT_TOKENS ma być liczbą całkowitą co najmniej {MIN_CONTEXT_TOKENS}, "
                f"jest {self.llm_context_tokens!r}"
            )
        if self.llm_max_tokens is not None and (type(self.llm_max_tokens) is not int or self.llm_max_tokens <= 0):
            raise ValueError("LLM_MAX_TOKENS ma być dodatnią liczbą całkowitą")
        if self.llm_temperature is not None and not 0 <= self.llm_temperature <= 2:
            raise ValueError("LLM_TEMPERATURE ma być liczbą od 0 do 2 albo 'off'")
        if self.llm_reasoning_effort is not None and self.llm_reasoning_effort not in _REASONING_EFFORTS:
            raise ValueError("LLM_REASONING_EFFORT ma być jedną z wartości: none, minimal, low, medium, high, xhigh, off")
        if not (math.isfinite(self.llm_connect_timeout_s) and self.llm_connect_timeout_s > 0):
            raise ValueError("LLM_CONNECT_TIMEOUT_S ma być dodatnią liczbą")
        if not (math.isfinite(self.llm_analysis_budget_s) and self.llm_analysis_budget_s > 0):
            raise ValueError("LLM_ANALYSIS_BUDGET_S ma być dodatnią liczbą")
        if type(self.llm_max_attempts) is not int or not 1 <= self.llm_max_attempts <= 3:
            raise ValueError("LLM_MAX_ATTEMPTS ma być liczbą całkowitą od 1 do 3")

    def _check_provider(self) -> None:
        """D9: przy `edenai` tylko host Eden AI, klucz i model otwarty.

        Komunikaty nie powtarzają wartości: klucz wklejony w złą zmienną trafiłby do logu (D9 pkt 3).
        """
        if self.llm_provider not in PROVIDERS:
            raise ValueError("LLM_PROVIDER ma być 'ollama' albo 'edenai'")
        if self.llm_provider != "edenai":
            # Bez tego `ollama` z adresem Eden AI omijałby listę modeli otwartych (D9 pkt 7).
            if _is_eden_url(self.llm_base_url):
                raise ValueError("LLM_BASE_URL wskazuje Eden AI: ustaw LLM_PROVIDER=edenai")
            return
        if not _is_eden_url(self.llm_base_url):
            hosts = ", ".join(f"https://{host}" for host in sorted(EDENAI_HOSTS))
            raise ValueError(f"LLM_BASE_URL przy LLM_PROVIDER=edenai ma wskazywać Eden AI ({hosts})")
        if self.llm_api_key.strip().lower() in {"", "ollama"}:
            raise ValueError("LLM_API_KEY jest wymagany przy LLM_PROVIDER=edenai (klucz Eden AI)")
        if self.llm_model not in EDENAI_OPEN_MODELS:
            raise ValueError("LLM_MODEL przy LLM_PROVIDER=edenai ma być modelem otwartym z listy D9 (DECISIONS.md, M1.7)")

    @property
    def max_file_bytes(self) -> int:
        return self.max_file_size_mb * MB

    @classmethod
    def from_env(cls) -> "Settings":
        strict_schema = _env("LLM_STRICT_SCHEMA", "true").lower()
        if strict_schema not in {"true", "false"}:
            raise ValueError("LLM_STRICT_SCHEMA ma być 'true' albo 'false'")
        reasoning_effort = _env("LLM_REASONING_EFFORT", "none").lower()
        provider = _env("LLM_PROVIDER", "ollama").lower()
        # Compose podaje adres Ollamy osobno (LLM_OLLAMA_URL), żeby nie trafił do Eden AI.
        default_url = EDENAI_URL if provider == "edenai" else _env("LLM_OLLAMA_URL", OLLAMA_URL)
        return cls(
            llm_provider=provider,
            max_file_size_mb=_env_positive_int("MAX_FILE_SIZE_MB", 10),
            jwt_enabled=_env_bool("JWT_ENABLED", False),
            jwt_secret=os.environ.get("JWT_SECRET") or None,
            jwt_algorithm=_env("JWT_ALGORITHM", "HS256"),
            llm_base_url=_env("LLM_BASE_URL", default_url),
            llm_model=_env("LLM_MODEL", "qwen3.5:4b"),
            llm_api_key=_env("LLM_API_KEY", "ollama" if provider == "ollama" else ""),
            llm_timeout_s=_env_positive_float("LLM_TIMEOUT_S", 120.0),
            llm_context_tokens=_env_positive_int("LLM_CONTEXT_TOKENS", 32768),
            llm_fixture=os.environ.get("LLM_FIXTURE") or None,
            ocr_lang=_env("OCR_LANG", "pol"),
            add_validators=_env_bool("ADD_VALIDATORS", True),
            llm_max_tokens=_env_positive_int("LLM_MAX_TOKENS", 0) if _env("LLM_MAX_TOKENS", "") else None,
            llm_temperature=_env_temperature(),
            llm_reasoning_effort=None if reasoning_effort == "off" else reasoning_effort,
            llm_strict_schema=strict_schema == "true",
            llm_extra_body=_env_extra_body(),
            llm_connect_timeout_s=_env_positive_float("LLM_CONNECT_TIMEOUT_S", 10.0),
            llm_analysis_budget_s=_env_positive_float("LLM_ANALYSIS_BUDGET_S", 170.0),
            llm_max_attempts=_env_positive_int("LLM_MAX_ATTEMPTS", 2),
        )


@cache
def get_settings() -> Settings:
    return Settings.from_env()
