"""Klient modelu bez modelu: atrapa transportu httpx zamiast Ollamy (AGENTS.md: testy nie wołają LLM)."""

import base64
import json

import httpx
import pytest

from app.config import Settings, get_settings
from app.errors import LLMUnavailable
from app.llm import UNAVAILABLE_DETAIL, chat_json, image_part
from app.models import FormAnalysis

SETTINGS = Settings(llm_base_url="http://model.test/v1/", llm_model="qwen3.5:4b", llm_api_key="klucz", llm_timeout_s=5)
MESSAGES = [{"role": "user", "content": "Tekst formularza"}]


def _completion(content: object = '{"title": "x"}', **message: object) -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": content, **message}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1200, "completion_tokens": 340},
    }


def _transport(reply: httpx.Response | Exception, seen: list[httpx.Request] | None = None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        if isinstance(reply, Exception):
            raise reply
        return reply

    return httpx.MockTransport(handler)


def test_request_disables_thinking_and_forces_form_analysis_schema() -> None:
    seen: list[httpx.Request] = []
    schema = FormAnalysis.model_json_schema()
    chat_json(MESSAGES, schema, settings=SETTINGS, transport=_transport(httpx.Response(200, json=_completion()), seen))

    (request,) = seen
    assert str(request.url) == "http://model.test/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer klucz"
    assert request.extensions["timeout"]["read"] == 5
    body = json.loads(request.content)
    assert body["model"] == "qwen3.5:4b"
    assert body["messages"] == MESSAGES
    assert body["stream"] is False
    # Ollama na /v1 ignoruje `think`; myślenie wyłącza reasoning_effort "none".
    assert body["reasoning_effort"] == "none"
    assert "think" not in body
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"] == schema
    assert body["response_format"]["json_schema"]["name"] == "FormAnalysis"


def test_returns_content_usage_and_empty_reasoning() -> None:
    result = chat_json(MESSAGES, {}, settings=SETTINGS, transport=_transport(httpx.Response(200, json=_completion())))
    assert result.content == '{"title": "x"}'
    assert (result.prompt_tokens, result.completion_tokens) == (1200, 340)
    assert result.finish_reason == "stop"
    assert result.reasoning == ""
    assert result.elapsed_s >= 0


def test_reports_reasoning_when_server_ignores_the_flag() -> None:
    reply = httpx.Response(200, json=_completion(reasoning="Najpierw przeczytam formularz."))
    result = chat_json(MESSAGES, {}, settings=SETTINGS, transport=_transport(reply))
    assert result.reasoning == "Najpierw przeczytam formularz."


@pytest.mark.parametrize(
    "reply",
    [
        httpx.ReadTimeout("timeout"),
        httpx.ConnectError("connection refused"),
        # Ciało wygląda jak poprawna odpowiedź: liczy się kod HTTP, nie treść.
        httpx.Response(500, json=_completion()),
        httpx.Response(404, json={"error": "model 'qwen3.5:4b' not found"}),
        httpx.Response(200, text="to nie JSON"),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json=_completion(content=None)),
        httpx.Response(200, json=_completion(content="  ")),
    ],
    ids=["timeout", "connect", "http500", "http404", "not-json", "no-choices", "null-content", "blank-content"],
)
def test_any_model_failure_becomes_llm_unavailable(reply: httpx.Response | Exception) -> None:
    with pytest.raises(LLMUnavailable) as caught:
        chat_json(MESSAGES, {}, settings=SETTINGS, transport=_transport(reply))
    assert caught.value.status_code == 503
    assert caught.value.detail == UNAVAILABLE_DETAIL


def test_without_settings_the_client_uses_app_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "http://env.test/v1")
    monkeypatch.setenv("LLM_MODEL", "SpeakLeash/bielik-4.5b-v3.0-instruct:Q8_0")
    monkeypatch.setenv("LLM_API_KEY", "z-env")
    seen: list[httpx.Request] = []
    get_settings.cache_clear()
    try:
        chat_json(MESSAGES, {}, transport=_transport(httpx.Response(200, json=_completion()), seen))
    finally:
        get_settings.cache_clear()

    (request,) = seen
    assert str(request.url) == "http://env.test/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer z-env"
    assert json.loads(request.content)["model"] == "SpeakLeash/bielik-4.5b-v3.0-instruct:Q8_0"


def test_image_part_is_a_base64_data_url() -> None:
    part = image_part(b"\x89PNG", "image/png")
    assert part["type"] == "image_url"
    prefix, encoded = part["image_url"]["url"].split(",", 1)
    assert prefix == "data:image/png;base64"
    assert base64.b64decode(encoded) == b"\x89PNG"
