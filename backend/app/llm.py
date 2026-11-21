"""Jedyne miejsce, które woła model (AGENTS.md): klient OpenAI-compatible `/v1/chat/completions`.

Adres, model, klucz i limit czasu bierze z config.Settings (LLM_BASE_URL, LLM_MODEL, LLM_API_KEY,
LLM_TIMEOUT_S; DELEGACJA.md, rozdz. 5).
Ollama na tym endpoincie ignoruje pole `think` z natywnego API. Tryb myślenia wyłącza
`reasoning_effort: "none"` (docs.ollama.com/api/openai-compatibility). Rozmiaru kontekstu nie da się
tu ustawić: ustala go serwer (`OLLAMA_CONTEXT_LENGTH`, domyślnie 4096 tokenów).
"""

import base64
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.errors import LLMUnavailable

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


def chat_json(
    messages: list[Message],
    schema: dict[str, Any],
    *,
    schema_name: str = "FormAnalysis",
    max_tokens: int = 4096,
    settings: Settings | None = None,
    transport: httpx.BaseTransport | None = None,
) -> ChatResult:
    """Jedno zapytanie z odpowiedzią wymuszoną schematem. Treści nie waliduje: to robi wywołujący."""
    settings = settings or get_settings()
    body = build_request(messages, schema, model=settings.llm_model, schema_name=schema_name, max_tokens=max_tokens)
    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=settings.llm_timeout_s, transport=transport) as client:
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

    usage = payload.get("usage") or {}
    return ChatResult(
        content=content,
        reasoning=message.get("reasoning") or message.get("reasoning_content") or "",
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        finish_reason=choice.get("finish_reason"),
        elapsed_s=elapsed,
    )
