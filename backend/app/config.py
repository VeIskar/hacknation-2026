"""Konfiguracja ze zmiennych środowiskowych (DELEGACJA.md, rozdz. 5).

Endpointy biorą ją przez Depends(get_settings), więc testy podmieniają ją przez
app.dependency_overrides zamiast ustawiać zmienne środowiskowe.
"""

import os
from dataclasses import dataclass
from functools import cache

MB = 1024 * 1024
_TRUE = {"1", "true", "yes", "on"}


def _env(name: str, default: str) -> str:
    return os.environ.get(name, "").strip() or default


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    return value in _TRUE if value else default


@dataclass(frozen=True)
class Settings:
    max_file_size_mb: int = 10
    jwt_enabled: bool = False
    jwt_secret: str | None = None
    jwt_algorithm: str = "HS256"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "qwen3.5:4b"
    llm_api_key: str = "ollama"
    llm_timeout_s: float = 120.0
    llm_fixture: str | None = None
    ocr_lang: str = "pol"
    add_validators: bool = True

    @property
    def max_file_bytes(self) -> int:
        return self.max_file_size_mb * MB

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            max_file_size_mb=int(_env("MAX_FILE_SIZE_MB", "10")),
            jwt_enabled=_env_bool("JWT_ENABLED", False),
            jwt_secret=os.environ.get("JWT_SECRET") or None,
            jwt_algorithm=_env("JWT_ALGORITHM", "HS256"),
            llm_base_url=_env("LLM_BASE_URL", "http://localhost:11434/v1"),
            llm_model=_env("LLM_MODEL", "qwen3.5:4b"),
            llm_api_key=_env("LLM_API_KEY", "ollama"),
            llm_timeout_s=float(_env("LLM_TIMEOUT_S", "120")),
            llm_fixture=os.environ.get("LLM_FIXTURE") or None,
            ocr_lang=_env("OCR_LANG", "pol"),
            add_validators=_env_bool("ADD_VALIDATORS", True),
        )


@cache
def get_settings() -> Settings:
    return Settings.from_env()
