"""K3: analiza bez modelu. Atrapa transportu httpx albo LLM_FIXTURE (AGENTS.md: testy nie wołają LLM).

Wejście to przykładowy ExtractedDocument, więc testy nie zależą od odczytu plików (K2).
"""

import html
import json
import logging
import re
from pathlib import Path
from typing import Annotated, Any

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import analysis
from app.analysis import (
    ANSWER_TOKENS,
    CONTEXT_TOKENS,
    CORRECTION_INTRO,
    CORRECTION_OUTRO,
    EMPTY_DOCUMENT_DETAIL,
    SHORT_CORRECTION_INTRO,
    SYSTEM_PROMPT,
    TRUNCATED_NOTE,
    analyze,
    correction_message,
    estimate_prompt_tokens,
    prepare_text,
    system_message_text,
    user_message,
)
from app.config import Settings, get_settings
from app.errors import ExtractionError, LLMUnavailable
from app.llm import UNAVAILABLE_DETAIL
from app.models import ApplicantData, ExtractedDocument, FormAnalysis

FIELDS = Path(__file__).parent / "fixtures" / "fields.json"
VALID = FIELDS.read_text(encoding="utf-8")
SETTINGS = Settings(llm_base_url="http://model.test/v1", llm_timeout_s=5)
RADIO = "Wybierz, co mamy zrobić z nadpłatą"
# Zmyślony wniosek w stylu folderu 5. Strona 2 zaczyna się po znaku \f.
DOC_TEXT = (
    "WNIOSEK O STWIERDZENIE NADPŁATY PODATKU\r\n"
    "Urząd Gminy Ulan-Majorat\r\n\r\n"
    "Wnoszę o stwierdzenie nadpłaty z tytułu ....................... w kwocie ______________ zł\n"
    "Uzasadnienie:\t……………………………………\n"
    "\f"
    "Kwotę nadpłaty proszę:\n"
    "1) zaliczyć na poczet ...................\n"
    "2) zwrócić przelewem na rachunek nr .................\n"
)
DOC = ExtractedDocument(source_format="pdf", text=DOC_TEXT)
PNG = b"\x89PNG\r\n\x1a\n"


def _answer_with_self_reference(padding: int = 0) -> str:
    """Błąd z pomiaru K1: RADIO z show_if wskazującym samo siebie."""
    data = json.loads(VALID)
    fields = data["subject_pages"][0]["sections"][1]["fields"]
    radio = next(field for field in fields if field["label"] == RADIO)
    radio["show_if"] = {"field": RADIO, "equals": radio["options"][0]}
    radio["description"] = "x" * padding
    return json.dumps(data, ensure_ascii=False)


def _measured_prompt_tokens(body: dict[str, Any]) -> int:
    """Tyle tokenów liczy prawdziwy serwer: 3,5 znaku na token (pomiar K3) i ok. 1950 na stronę skanu (K1)."""
    chars = images = 0
    for message in body["messages"]:
        content = message["content"]
        for part in [{"type": "text", "text": content}] if isinstance(content, str) else content:
            chars, images = (chars + len(part["text"]), images) if part["type"] == "text" else (chars, images + 1)
    return round(chars / 3.5) + images * 1950


class FakeModel:
    """Serwer /v1 w pamięci: kolejne odpowiedzi z listy, zapisane ciała zapytań.

    context_tokens udaje serwer z mniejszym kontekstem, który przycina prompt bez błędu.
    usage=False udaje serwer, który nie podaje liczby tokenów.
    """

    def __init__(
        self, *replies: str | tuple[str, str] | Exception, context_tokens: int | None = None, usage: bool = True
    ) -> None:
        self.replies = list(replies)
        self.requests: list[dict[str, Any]] = []
        self.context_tokens = context_tokens
        self.usage = usage
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        content, finish_reason = reply if isinstance(reply, tuple) else (reply, "stop")
        prompt_tokens = _measured_prompt_tokens(body)
        if self.context_tokens is not None:
            prompt_tokens = min(prompt_tokens, self.context_tokens)
        choice = {"message": {"role": "assistant", "content": content}, "finish_reason": finish_reason}
        usage = {"prompt_tokens": prompt_tokens, "completion_tokens": 1200}
        return httpx.Response(200, json={"choices": [choice], **({"usage": usage} if self.usage else {})})


def _run(model: FakeModel, doc: ExtractedDocument = DOC) -> FormAnalysis:
    return analyze(doc, settings=SETTINGS, transport=model.transport)


def test_valid_answer_is_returned_as_form_analysis_after_one_request() -> None:
    model = FakeModel(VALID)
    assert _run(model) == FormAnalysis.model_validate_json(VALID)
    assert len(model.requests) == 1


def test_request_carries_rules_schema_and_prepared_text() -> None:
    model = FakeModel(VALID)
    _run(model)

    (body,) = model.requests
    system, user = body["messages"]
    assert system["role"] == "system" and system["content"].startswith(SYSTEM_PROMPT)
    assert body["response_format"]["json_schema"]["schema"] == FormAnalysis.model_json_schema()
    assert body["max_tokens"] == ANSWER_TOKENS
    assert user["role"] == "user"
    assert user["content"].startswith("Tekst formularza z pliku PDF:")
    assert "--- Strona 2 ---\nKwotę nadpłaty proszę:" in user["content"]
    assert "z tytułu … w kwocie … zł" in user["content"]
    assert "...." not in user["content"] and "____" not in user["content"]


def test_ocr_text_is_marked_as_possibly_misspelled() -> None:
    model = FakeModel(VALID)
    _run(model, ExtractedDocument(source_format="jpg", text="WNIOSEK", ocr_used=True))
    assert model.requests[0]["messages"][1]["content"].startswith(
        "Tekst formularza z pliku JPG, odczytany przez OCR, więc może mieć błędy literowe:"
    )


def _prompt_schema() -> dict:
    return json.loads(system_message_text().split("\n\nSchemat JSON:\n", 1)[1])


def _values(node: Any, key: str) -> list[Any]:
    if isinstance(node, dict):
        return [v for k, v in node.items() if k == key] + [x for v in node.values() for x in _values(v, key)]
    if isinstance(node, list):
        return [x for v in node for x in _values(v, key)]
    return []


def test_prompt_schema_keeps_every_description_and_the_applicant_contract() -> None:
    schema = _prompt_schema()
    full = FormAnalysis.model_json_schema()
    def descriptions(node: Any) -> list[str]:
        return [value for value in _values(node, "description") if isinstance(value, str)]

    assert descriptions(schema) == descriptions(full) != []
    assert set(schema["$defs"]["ApplicantData"]["properties"]) == set(ApplicantData.model_fields)
    assert schema["$defs"]["ApplicantData"]["required"] == full["$defs"]["ApplicantData"]["required"]
    # Pole o nazwie "title" zostaje, znika tylko adnotacja Pydantic z nazwą klucza.
    assert "title" in schema["properties"] and "title" in schema["required"]
    assert [value for value in _values(schema, "title") if isinstance(value, str)] == []


def test_invalid_answer_is_retried_with_the_validator_message() -> None:
    wrong = _answer_with_self_reference()
    model = FakeModel(wrong, VALID)
    assert _run(model) == FormAnalysis.model_validate_json(VALID)

    first, second = model.requests
    assert second["messages"][:2] == first["messages"]
    assistant, correction = second["messages"][2:]
    assert assistant == {"role": "assistant", "content": wrong}
    assert correction["role"] == "user"
    assert correction["content"] == "\n".join(
        [CORRECTION_INTRO, f"- subject_pages[0]: show_if pola '{RADIO}' wskazuje to samo pole", CORRECTION_OUTRO]
    )


def test_truncated_answer_is_retried_with_a_note_about_length() -> None:
    model = FakeModel((VALID[:300], "length"), VALID)
    assert _run(model) == FormAnalysis.model_validate_json(VALID)
    correction = model.requests[1]["messages"][-1]["content"]
    assert correction.startswith(f"{TRUNCATED_NOTE}\n{CORRECTION_INTRO}\n- cały JSON: Invalid JSON")


def test_two_invalid_answers_end_with_controlled_503_without_a_third_try() -> None:
    model = FakeModel(_answer_with_self_reference(), _answer_with_self_reference(), VALID)
    with pytest.raises(LLMUnavailable) as caught:
        _run(model)
    assert (caught.value.status_code, caught.value.detail) == (503, UNAVAILABLE_DETAIL)
    assert len(model.requests) == 2


def test_model_failure_is_503_and_is_not_retried() -> None:
    model = FakeModel(httpx.ReadTimeout("timeout"), VALID)
    with pytest.raises(LLMUnavailable) as caught:
        _run(model)
    assert caught.value.detail == UNAVAILABLE_DETAIL
    assert len(model.requests) == 1


def test_correction_lists_at_most_ten_errors_and_counts_the_rest() -> None:
    data = json.loads(VALID)
    data["subject_pages"][0]["sections"][0]["fields"] = [{"label": f"Pole {n}"} for n in range(12)]
    with pytest.raises(ValidationError) as caught:
        FormAnalysis.model_validate(data)
    lines = correction_message(caught.value, "stop").split("\n")
    assert lines[1] == "- subject_pages[0].sections[0].fields[0].type: Field required"
    assert len(lines) == 1 + 10 + 2
    assert lines[-2] == "- … i 2 innych błędów"


def _form_text(chars: int) -> str:
    line = "Wpisz numer działalności, której dotyczy wniosek …\n"
    return line * (chars // len(line))


@pytest.mark.parametrize(
    ("chars", "sent"),
    [(13_000, True), (31_000, False)],
    ids=["folder-9-size-fits", "folder-8-size-rejected"],
)
def test_context_budget_decides_before_any_request(
    chars: int, sent: bool, caplog: pytest.LogCaptureFixture
) -> None:
    """Rozmiary po uporządkowaniu tekstu DOCX z folderów 9 (13,2 tys.) i 8 (31,2 tys. znaków)."""
    model = FakeModel(VALID)
    doc = ExtractedDocument(source_format="docx", text=_form_text(chars))
    if sent:
        _run(model, doc)
        assert len(model.requests) == 1
        return
    with pytest.raises(LLMUnavailable) as caught, caplog.at_level(logging.WARNING, logger="app.analysis"):
        _run(model, doc)
    assert caught.value.detail == UNAVAILABLE_DETAIL
    assert model.requests == []
    assert "analizy fragmentami" in caplog.text


def test_prompt_cut_by_a_server_with_smaller_context_is_503(caplog: pytest.LogCaptureFixture) -> None:
    """Recenzja K3: tekst rozmiaru folderu 9 na serwerze z domyślnym kontekstem Ollamy (4096)."""
    model = FakeModel(VALID, VALID, context_tokens=4096)
    doc = ExtractedDocument(source_format="docx", text=_form_text(13_000))
    with pytest.raises(LLMUnavailable) as caught, caplog.at_level(logging.WARNING, logger="app.analysis"):
        _run(model, doc)
    assert caught.value.detail == UNAVAILABLE_DETAIL
    assert len(model.requests) == 1
    assert "serwer policzył 4096 tokenów promptu" in caplog.text


def test_answer_without_token_usage_is_accepted() -> None:
    model = FakeModel(VALID, usage=False, context_tokens=0)
    assert _run(model) == FormAnalysis.model_validate_json(VALID)


def test_retry_drops_a_long_invalid_answer_but_keeps_the_whole_document() -> None:
    """Recenzja Codexa: tekst rozmiaru folderu 9 i długa zła odpowiedź. Pełne ponowienie by się nie zmieściło."""
    doc = ExtractedDocument(source_format="docx", text=_form_text(13_000))
    model = FakeModel(_answer_with_self_reference(padding=12_000), VALID)
    assert _run(model, doc) == FormAnalysis.model_validate_json(VALID)

    first, second = model.requests
    assert second["messages"][:2] == first["messages"]
    (correction,) = second["messages"][2:]
    assert correction["role"] == "user"
    assert correction["content"] == "\n".join(
        [SHORT_CORRECTION_INTRO, f"- subject_pages[0]: show_if pola '{RADIO}' wskazuje to samo pole", CORRECTION_OUTRO]
    )


def _document_filling_the_context(spare_tokens: int) -> ExtractedDocument:
    """Dokument, po którym w budżecie zostaje najwyżej spare_tokens na dopisanie błędów."""
    line = "Wpisz numer działalności, której dotyczy wniosek …\n"
    lines = 0
    while True:
        doc = ExtractedDocument(source_format="docx", text=line * (lines + 1))
        messages = [{"role": "system", "content": system_message_text()}, user_message(doc)]
        if estimate_prompt_tokens(messages) + ANSWER_TOKENS > CONTEXT_TOKENS - spare_tokens:
            return ExtractedDocument(source_format="docx", text=line * lines)
        lines += 1


def test_retry_is_not_sent_when_even_the_errors_alone_do_not_fit(caplog: pytest.LogCaptureFixture) -> None:
    model = FakeModel(_answer_with_self_reference(), VALID)
    with pytest.raises(LLMUnavailable) as caught, caplog.at_level(logging.WARNING, logger="app.analysis"):
        _run(model, _document_filling_the_context(spare_tokens=20))
    assert caught.value.detail == UNAVAILABLE_DETAIL
    assert len(model.requests) == 1
    assert "próba 2: zapytanie z odpowiedzią" in caplog.text


def test_deeply_nested_answer_is_a_validation_error_not_a_crash() -> None:
    """Głęboko zagnieżdżona odpowiedź to błąd walidacji całego JSON-a i ponowienie, nie 500.

    Treść błędu zależy od Pythona: do 3.13 json.loads rzuca RecursionError i opisuje go parser Pydantic
    („recursion limit exceeded”), od 3.14 json.loads ją przyjmuje, a model odrzuca listę (`model_type`).
    """
    # 20 000 poziomów to 40 000 znaków: tyle model może wypisać w limicie ANSWER_TOKENS.
    model = FakeModel("[" * 20_000 + "]" * 20_000, VALID)
    assert _run(model) == FormAnalysis.model_validate_json(VALID)
    assert len(model.requests) == 2
    assert "\n- cały JSON: " in model.requests[1]["messages"][-1]["content"]


def test_recursion_error_from_json_loads_falls_back_to_pydantic_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gałąź RecursionError w _validate (Python do 3.13) sprawdzona na każdej wersji Pythona."""

    def too_deep(_: str) -> Any:
        raise RecursionError("maximum recursion depth exceeded")

    monkeypatch.setattr(analysis.json, "loads", too_deep)
    with pytest.raises(ValidationError, match="recursion limit exceeded"):
        analysis._validate("[" * 20_000 + "]" * 20_000)


def test_lone_surrogate_from_the_model_is_repaired_like_in_the_contract() -> None:
    """P1.2a: samotny surogat staje się U+FFFD. Parser Pydantic odrzuciłby go przed tą naprawą."""
    raw = VALID.replace('"label": "Kwota"', '"label": "Kwota \\ud83d"', 1)
    assert "\\ud83d" in raw
    model = FakeModel(raw)
    analysis = _run(model)
    assert analysis.subject_pages[0].sections[0].fields[1].label == "Kwota \ufffd"
    assert len(model.requests) == 1


def test_page_images_go_to_the_model_only_without_text() -> None:
    scan = FakeModel(VALID)
    _run(scan, ExtractedDocument(source_format="png", text=" \n\f\t", images=[PNG]))
    parts = scan.requests[0]["messages"][1]["content"]
    assert [part["type"] for part in parts] == ["text", "image_url"]
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")

    with_text = FakeModel(VALID)
    _run(with_text, ExtractedDocument(source_format="png", text="WNIOSEK", images=[PNG], ocr_used=True))
    assert isinstance(with_text.requests[0]["messages"][1]["content"], str)


@pytest.mark.parametrize(("pages", "sent"), [(2, True), (4, False)], ids=["2-pages-fit", "4-pages-rejected"])
def test_page_images_count_against_the_context_budget(pages: int, sent: bool) -> None:
    """K1: strona skanu to ok. 1950 tokenów. Cztery strony z promptem i odpowiedzią nie mieszczą się w 16384."""
    model = FakeModel(VALID)
    doc = ExtractedDocument(source_format="png", text="", images=[PNG] * pages)
    if sent:
        _run(model, doc)
        assert len(model.requests) == 1
        return
    with pytest.raises(LLMUnavailable):
        _run(model, doc)
    assert model.requests == []


def test_document_without_text_or_images_is_not_sent_to_the_model() -> None:
    model = FakeModel(VALID)
    with pytest.raises(ExtractionError) as caught:
        _run(model, ExtractedDocument(source_format="pdf", text=" \r\n\f  "))
    assert (caught.value.status_code, caught.value.detail) == (400, EMPTY_DOCUMENT_DETAIL)
    assert model.requests == []


def test_prepare_text_shortens_fillers_and_spaces() -> None:
    assert prepare_text("Kwota:\t............  zł\r\n\r\n\nData: ____   ……") == "Kwota: … zł\nData: … ……"
    # Trzy kropki i kropki w skrótach to treść, nie miejsce do wpisania.
    assert prepare_text("art. 75 § 1 itd...") == "art. 75 § 1 itd..."


def test_prepare_text_marks_pages_with_their_original_numbers() -> None:
    assert prepare_text("A\n\f \f B ") == "--- Strona 1 ---\nA\n--- Strona 3 ---\nB"
    assert prepare_text("\fTylko druga") == "Tylko druga"


def test_prepare_text_keeps_every_letter_and_digit_in_order() -> None:
    def words(text: str) -> list[str]:
        return re.findall(r"[^\W_]+", text)

    messy = DOC_TEXT + "Lp. | Nazwa | Ilość\n1 |  | ....\n2 | ____ | …………\n\f\f  Oświadczam, że dane są prawdziwe."
    prepared = prepare_text(messy)
    assert "--- Strona 4 ---" in prepared
    assert words(re.sub(r"(?m)^--- Strona \d+ ---$", "", prepared)) == words(messy)


def test_fixture_mode_skips_the_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_network(*_: object) -> httpx.Response:
        raise AssertionError("LLM_FIXTURE nie może łączyć się z modelem")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_network)
    analysis = analyze(DOC, settings=Settings(llm_base_url="http://model.test/v1", llm_fixture=str(FIELDS)))
    assert analysis == FormAnalysis.model_validate_json(VALID)


def test_dependency_override_of_settings_reaches_the_model_layer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Trasa bierze Settings z Depends(get_settings), jak w main.py. Env wskazuje inny serwer i brak atrapy."""

    def no_network(*_: object) -> httpx.Response:
        raise AssertionError("ustawienia z env zamiast z dependency_overrides")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_network)
    monkeypatch.setenv("LLM_BASE_URL", "http://env.test/v1")
    monkeypatch.delenv("LLM_FIXTURE", raising=False)
    get_settings.cache_clear()
    api = FastAPI()

    @api.post("/analiza")
    def route(settings: Annotated[Settings, Depends(get_settings)]) -> dict:
        return analyze(DOC, settings=settings).model_dump(mode="json")

    api.dependency_overrides[get_settings] = lambda: Settings(llm_fixture=str(FIELDS))
    try:
        response = TestClient(api).post("/analiza")
    finally:
        get_settings.cache_clear()
    assert response.status_code == 200
    assert response.json() == FormAnalysis.model_validate_json(VALID).model_dump(mode="json")


def test_log_has_numbers_but_no_document_or_answer_text(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="app.analysis"):
        _run(FakeModel(_answer_with_self_reference(), VALID))
    assert "próba 1/2" in caplog.text and "próba 2/2: poprawna analiza" in caplog.text
    for secret in ["Ulan-Majorat", "Kwotę nadpłaty", RADIO]:
        assert secret not in caplog.text


def _plain(text: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text)).split()).casefold()


def _coi_texts(form: dict) -> set[str]:
    """Teksty widoczne w JSON-ie COI. Ta sama miara co w test_models.py (D5)."""
    texts = {form["title"]}
    for tab in form["tabs"]:
        texts.add(tab["title"])
        for question in tab["questions"]:
            for item in [question, *question["field"].get("repeatingSectionGrid", [])]:
                texts.update(item["field"].get(key, "") for key in ("title", "description", "tooltipMessage"))
                texts.update(option["name"] for option in item["field"].get("options", []))
                default = item["field"].get("defaultValue")
                if isinstance(default, str):
                    texts.add(default)
    return {plain for plain in map(_plain, texts) if len(plain) >= 4}


def test_control_set_does_not_leak_into_the_prompt(coi_control_reference: dict, coi_working_reference: dict) -> None:
    control_only = _coi_texts(coi_control_reference) - _coi_texts(coi_working_reference)
    # Jak w test_models.py: REGON to nazwa walidatora z Reguł i wartość kontraktu, nie tekst z folderu 1.
    control_only.discard("regon")
    assert control_only, "zbiór kontrolny nie ma własnych tekstów, test nic by nie sprawdzał"
    prompt = _plain(f"{system_message_text()} {CORRECTION_INTRO} {TRUNCATED_NOTE} {CORRECTION_OUTRO}")
    assert sorted(text for text in control_only if text in prompt) == []
