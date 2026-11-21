"""Jedyne miejsce, które woła model (AGENTS.md): klient OpenAI-compatible `/chat/completions`.

Adres, model, klucz i parametry zapytania bierze z config.Settings podanych przez wołającego,
więc app.dependency_overrides[get_settings] w testach dociera aż tutaj.
Przy LLM_FIXTURE zwraca treść tego pliku bez łączenia się z modelem (SPEC „Real and mocked”).
Ollama na tym endpoincie ignoruje pole `think` z natywnego API. Tryb myślenia wyłącza
`reasoning_effort: "none"` (docs.ollama.com/api/openai-compatibility). Rozmiaru kontekstu nie da się
tu ustawić: ustala go serwer (`OLLAMA_CONTEXT_LENGTH`, domyślnie 4096 tokenów).
"""

import base64
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.errors import LLMUnavailable

log = logging.getLogger(__name__)

UNAVAILABLE_DETAIL = "Model AI nie odpowiada. Spróbuj ponownie za chwilę."

Message = dict[str, Any]


@dataclass(frozen=True)
class ChatResult:
    content: str
    # Treść toku rozumowania, jeśli serwer ją zwrócił.
    reasoning: str
    prompt_tokens: int | None
    completion_tokens: int | None
    # "length" znaczy, że odpowiedź ucięto na max_tokens, więc JSON jest niepełny.
    finish_reason: str | None
    elapsed_s: float


def image_part(data: bytes, mime: str = "image/png") -> Message:
    encoded = base64.b64encode(data).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}}


def provider(settings: Settings) -> str:
    return getattr(settings, "llm_provider", "ollama")


def answer_token_limit(settings: Settings) -> int:
    if settings.llm_max_tokens is not None:
        return settings.llm_max_tokens
    return 8192 if provider(settings) == "edenai" else 4096


def build_request(
    messages: list[Message], schema: dict[str, Any], *, settings: Settings, schema_name: str, max_tokens: int
) -> dict[str, Any]:
    body = {
        **(settings.llm_extra_body or {}),
        "model": settings.llm_model,
        "messages": messages,
        "stream": False,
        "temperature": settings.llm_temperature,
        "max_tokens": max_tokens,
        "reasoning_effort": settings.llm_reasoning_effort,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "schema": schema, "strict": settings.llm_strict_schema},
        },
    }
    for key in ("temperature", "reasoning_effort"):
        if body[key] is None:
            del body[key]
    return body


def _typed(value: Any, kind: type) -> Any:
    """Metadane są tylko diagnostyką: zły typ to brak wartości, a nie powód do odrzucenia odpowiedzi."""
    return value if isinstance(value, kind) and not isinstance(value, bool) else None


def _fixture_result(path: str) -> ChatResult:
    started = time.perf_counter()
    try:
        content = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        # Atrapa zastępuje model, więc jej brak to brak modelu (503). Przyczyna zostaje w logu.
        log.error("LLM_FIXTURE: nie można odczytać pliku %s: %s", path, exc)
        raise LLMUnavailable(detail=UNAVAILABLE_DETAIL) from exc
    return ChatResult(
        content=content,
        reasoning="",
        prompt_tokens=None,
        completion_tokens=None,
        finish_reason="stop",
        elapsed_s=time.perf_counter() - started,
    )


def chat_json(
    messages: list[Message],
    schema: dict[str, Any],
    *,
    settings: Settings,
    schema_name: str = "FormAnalysis",
    max_tokens: int | None = None,
    transport: httpx.BaseTransport | None = None,
) -> ChatResult:
    """Jedno zapytanie z odpowiedzią wymuszoną schematem. Treści nie waliduje: to robi wywołujący."""
    if settings.llm_fixture:
        return _fixture_result(settings.llm_fixture)
    if max_tokens is None:
        max_tokens = answer_token_limit(settings)
    body = build_request(messages, schema, settings=settings, schema_name=schema_name, max_tokens=max_tokens)
    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    timeout = httpx.Timeout(settings.llm_timeout_s, connect=settings.llm_connect_timeout_s)
    started = time.perf_counter()
    try:
        # Łączymy się bezpośrednio z ustawionym dostawcą, żeby proxy z env nie dostało formularza ani klucza.
        with httpx.Client(timeout=timeout, transport=transport, trust_env=False) as client:
            response = client.post(url, json=body, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        excerpt = exc.response.text
        if settings.llm_api_key:
            excerpt = excerpt.replace(settings.llm_api_key, "***")
        log.warning("Model AI: HTTP %d, treść odpowiedzi: %s", exc.response.status_code, excerpt[:300])
        raise LLMUnavailable(detail=UNAVAILABLE_DETAIL) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise LLMUnavailable(detail=UNAVAILABLE_DETAIL) from exc
    elapsed = time.perf_counter() - started

    try:
        choice = payload["choices"][0]
        message = choice["message"]
        content = message["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMUnavailable(detail=UNAVAILABLE_DETAIL) from exc
    if not isinstance(content, str) or not content.strip():
        raise LLMUnavailable(detail=UNAVAILABLE_DETAIL)

    usage = _typed(payload.get("usage"), dict) or {}
    return ChatResult(
        content=content,
        reasoning=_typed(message.get("reasoning"), str) or _typed(message.get("reasoning_content"), str) or "",
        prompt_tokens=_typed(usage.get("prompt_tokens"), int),
        completion_tokens=_typed(usage.get("completion_tokens"), int),
        finish_reason=choice.get("finish_reason"),
        elapsed_s=elapsed,
    )
