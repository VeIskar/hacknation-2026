"""Klient modelu bez modelu: atrapa transportu httpx zamiast Ollamy (AGENTS.md: testy nie wołają LLM)."""

import base64
import json
from pathlib import Path

import httpx
import pytest
from env_proxy import record_proxy_use

from app.config import Settings
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


@pytest.mark.parametrize(
    ("usage", "message"),
    [
        ([1200, 340], {}),
        ({"prompt_tokens": "1200", "completion_tokens": [340]}, {}),
        ({}, {"reasoning": 641}),
        ({}, {"reasoning_content": 641}),
    ],
    ids=["usage-list", "tokens-not-int", "reasoning-number", "reasoning-content-number"],
)
def test_malformed_metadata_keeps_the_answer_and_drops_bad_values(usage: object, message: dict) -> None:
    body = _completion(**message)
    body["usage"] = usage
    result = chat_json(MESSAGES, {}, settings=SETTINGS, transport=_transport(httpx.Response(200, json=body)))
    assert result.content == '{"title": "x"}'
    assert result.reasoning == ""
    assert (result.prompt_tokens, result.completion_tokens) == (None, None)


def test_settings_must_come_from_the_caller(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bez cichego get_settings(): inaczej dependency_overrides w testach trasy nie dotarłyby do modelu."""
    monkeypatch.setenv("LLM_BASE_URL", "http://env.test/v1")
    seen: list[httpx.Request] = []
    with pytest.raises(TypeError, match="settings"):
        chat_json(MESSAGES, {}, transport=_transport(httpx.Response(200, json=_completion()), seen))
    assert seen == []


def test_fixture_returns_the_file_without_calling_the_model(tmp_path: Path) -> None:
    fixture = tmp_path / "analiza.json"
    fixture.write_text('{"title": "Wniosek z atrapy"}', encoding="utf-8")
    seen: list[httpx.Request] = []
    settings = Settings(llm_base_url="http://model.test/v1", llm_fixture=str(fixture))
    result = chat_json(MESSAGES, {}, settings=settings, transport=_transport(httpx.Response(500), seen))
    assert result.content == '{"title": "Wniosek z atrapy"}'
    assert (result.finish_reason, result.reasoning, result.prompt_tokens) == ("stop", "", None)
    assert seen == []


@pytest.mark.parametrize("content", [None, b"\xff\xfe nie UTF-8"], ids=["missing", "not-utf8"])
def test_unreadable_fixture_is_llm_unavailable_with_the_path_in_the_log(
    tmp_path: Path, content: bytes | None, caplog: pytest.LogCaptureFixture
) -> None:
    fixture = tmp_path / "analiza.json"
    if content is not None:
        fixture.write_bytes(content)
    seen: list[httpx.Request] = []
    settings = Settings(llm_base_url="http://model.test/v1", llm_fixture=str(fixture))
    with pytest.raises(LLMUnavailable) as caught:
        chat_json(MESSAGES, {}, settings=settings, transport=_transport(httpx.Response(200, json=_completion()), seen))
    assert caught.value.detail == UNAVAILABLE_DETAIL
    assert seen == []
    assert f"LLM_FIXTURE: nie można odczytać pliku {fixture}" in caplog.text


def test_model_call_ignores_proxy_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    used = record_proxy_use(monkeypatch, _completion())
    # Adres jak w docker compose: nie loopback, więc proxy z env objęłoby go bez trust_env=False.
    settings = Settings(llm_base_url="http://ollama:11434/v1", llm_timeout_s=5)
    result = chat_json(MESSAGES, {}, settings=settings)
    assert result.content == '{"title": "x"}'
    assert used == [None]


def test_image_part_is_a_base64_data_url() -> None:
    part = image_part(b"\x89PNG", "image/png")
    assert part["type"] == "image_url"
    prefix, encoded = part["image_url"]["url"].split(",", 1)
    assert prefix == "data:image/png;base64"
    assert base64.b64decode(encoded) == b"\x89PNG"
