"""Jedyne miejsce, które woła model (AGENTS.md): klient OpenAI-compatible `/v1/chat/completions`.

Adres, model, klucz i limit czasu bierze z config.Settings (LLM_BASE_URL, LLM_MODEL, LLM_API_KEY,
LLM_TIMEOUT_S; DELEGACJA.md, rozdz. 5) podanych przez wołającego. Sam nie czyta env ani get_settings(),
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
    # Pusty, gdy model nie myślał. Niepusty znaczy, że serwer zignorował reasoning_effort.
    reasoning: str
    prompt_tokens: int | None
    completion_tokens: int | None
    # "length" znaczy, że odpowiedź ucięto na max_tokens, więc JSON jest niepełny.
    finish_reason: str | None
    elapsed_s: float


def image_part(data: bytes, mime: str = "image/png") -> Message:
    encoded = base64.b64encode(data).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}}


def build_request(
    messages: list[Message], schema: dict[str, Any], *, model: str, schema_name: str, max_tokens: int
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": messages,
        "stream": False,
        "temperature": 0,
        "max_tokens": max_tokens,
        "reasoning_effort": "none",
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "schema": schema, "strict": True},
        },
    }


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
    max_tokens: int = 4096,
    transport: httpx.BaseTransport | None = None,
) -> ChatResult:
    """Jedno zapytanie z odpowiedzią wymuszoną schematem. Treści nie waliduje: to robi wywołujący."""
    if settings.llm_fixture:
        return _fixture_result(settings.llm_fixture)
    body = build_request(messages, schema, model=settings.llm_model, schema_name=schema_name, max_tokens=max_tokens)
    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    started = time.perf_counter()
    try:
        # Model działa lokalnie (SPEC „Model”): proxy z HTTP_PROXY nie może przejąć zapytania z treścią formularza.
        with httpx.Client(timeout=settings.llm_timeout_s, transport=transport, trust_env=False) as client:
            response = client.post(url, json=body, headers=headers)
            response.raise_for_status()
            payload = response.json()
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
