"""K3: analiza dokumentu przez model, wynik to FormAnalysis (DELEGACJA.md, rozdz. 2.2, zadanie K3).

Przepływ: lekkie uporządkowanie tekstu, kontrola budżetu kontekstu, llm.chat_json ze schematem
FormAnalysis, potem FormAnalysis.model_validate_json. Wynik niezgodny z kontraktem wraca do modelu
z błędami walidatora. Po MAX_ATTEMPTS próbach analiza kończy się LLMUnavailable (503, D4).
Folder 1 (zbiór kontrolny, D5) nie może trafić do promptu: pilnuje tego tests/test_analysis.py.
"""

import json
import logging
import math
import re
from collections.abc import Sequence
from functools import cache
from typing import Any

import httpx
from pydantic import ValidationError

from app.config import Settings
from app.errors import ExtractionError, LLMUnavailable
from app.llm import (
    UNAVAILABLE_DETAIL,
    ChatResult,
    Message,
    answer_token_limit,
    chat_json,
    image_part,
    provider,
)
from app.models import ExtractedDocument, FormAnalysis

log = logging.getLogger(__name__)

# Decyzja 2026-11-21: pierwsza próba i jedno ponowienie, bo na CPU jedna próba trwa 240–344 s (K1).
MAX_ATTEMPTS = 2
# K1: prompt, schemat i tekst nadpłaty to 7338 znaków i 2034 tokeny promptu, czyli 3,6 znaku na token.
# Przyjmujemy mniej znaków na token, żeby oszacowanie było ostrożne: polski tekst bez wielokropków
# dzieli się na tokeny drobniej niż schemat.
CHARS_PER_TOKEN = 2.5
# Górna granica do wykrycia przycięcia przez serwer. Zmierzone: K1 3,6, K3 3,5 znaku na token
# (prompt K3 z nadpłatą: 9690 znaków, 2765 tokenów). Wykrywa utratę ponad ok. 30% promptu.
MAX_CHARS_PER_TOKEN = 5.0
# K1: jedna strona skanu JPG to ok. 1950 tokenów promptu ponad tekst.
IMAGE_TOKENS = 2500
# Znaczniki roli w szablonie czatu.
MESSAGE_TOKENS = 16
MAX_REPORTED_ERRORS = 10

EMPTY_DOCUMENT_DETAIL = "Nie udało się odczytać treści pliku."

SYSTEM_PROMPT = """Analizujesz papierowy formularz urzędowy. Opisz go jako JSON zgodny ze schematem na końcu.

Podstawa w treści:
- Każdy element JSON-a musi wynikać z tekstu formularza: pole, opcja, sekcja, oświadczenie i każda decyzja w applicant.
- Nie dodawaj pól, których formularz nie zawiera. Nie uzupełniaj typowych pól z pamięci.
- Gdy formularz nie mówi o jakiejś danej wnioskodawcy, w applicant wpisz false albo pustą listę.
- Znak … oznacza miejsce do wpisania.

Wnioskodawca (applicants i applicant):
- Imię i nazwisko lub nazwę, PESEL, NIP, REGON, KRS, adresy, telefon, e-mail i pełnomocnika wnioskodawcy opisz tylko w applicants i applicant.
- Nie powtarzaj tych danych w subject_pages.
- Inne dane wnioskodawcy z formularza zapisz w applicant_extra_fields.
- Dane innych osób zapisz w subject_pages.

Przedmiot wniosku (subject_pages):
- Etykiety pisz prostym językiem, w drugiej osobie, bez numerów przepisów.
- Typ pola: kwota lub liczba to NUMBER, data to DATEPICKER, uzasadnienie lub opis to TEXTAREA, reszta to TEXT_FIELD.
- Lista „1) … 2) …” albo kwadraty do zaznaczenia: RADIO dla jednego wyboru, CHECKBOX dla wielu, SELECT dla ponad 5 opcji.
- Dane dopisywane przy opcji to osobne pole z show_if tej opcji.
- show_if.field to dokładna etykieta wcześniejszego pola wyboru, jednoznaczna na wszystkich stronach przedmiotu.
- Podaj jedną opcję w equals, a kolejne w any_of. Wystarczy wybranie jednej z nich.
- show_if_all wymaga wszystkich warunków razem z show_if. Warunki mogą dotyczyć pola lub całej sekcji.
- Załączniki: sekcja z opisem i pole FILE_UPLOADER dla każdego wymienionego załącznika.
- required: false tylko wtedy, gdy formularz mówi, że pole jest nieobowiązkowe albo „jeśli dotyczy”.
- Grupuj pola w sekcje tematyczne. Tytuł sekcji to jej temat.

Pozostałe pola:
- title: tytuł z nagłówka formularza.
- addressee: URZAD dla urzędu; ORGAN dla wójta, burmistrza, prezydenta miasta albo starosty. Nazwa bez adresu.
- signature: true, chyba że formularz mówi, że podpis nie jest potrzebny.
- statements: oświadczenia („Oświadczam, że…”) wymagane zawsze od wnioskodawcy, prostym językiem.
- Oświadczenie warunkowe zostaw w subject_pages przy danych, których dotyczy.

Pomiń: miejscowość i datę, podpis, podstawę prawną, klauzulę RODO, pola „wypełnia urząd” i przypisy.
Zwróć wyłącznie JSON."""

CORRECTION_INTRO = "Ta odpowiedź nie przechodzi walidacji. Popraw wskazane błędy i zwróć cały JSON jeszcze raz."
SHORT_CORRECTION_INTRO = (
    "Twoja poprzednia odpowiedź nie przeszła walidacji i nie mieści się tutaj. "
    "Napisz cały JSON od nowa i unikaj tych błędów:"
)
TRUNCATED_NOTE = "Odpowiedź urwała się na limicie długości. Pisz zwięźlej: krótkie opisy, bez powtórzeń."
CORRECTION_OUTRO = "Nie dodawaj niczego, czego nie ma w formularzu."

# Kropki, podkreślenia i wielokropki do wpisywania. Liczba znaków nie niesie treści, a każdy kosztuje tokeny.
_FILL_RUN = re.compile(r"[._…]{4,}")
# Białe znaki poza końcem linii, także tabulator i twarda spacja.
_SPACES = re.compile(r"[^\S\n]+")


def prepare_text(text: str) -> str:
    """Mniej tokenów bez utraty treści: litery i cyfry zostają wszystkie i w tej samej kolejności.

    Skraca wypełniacze do „…”, scala spacje, usuwa puste linie. Strony (znak \\f) dostają nagłówki,
    gdy niepustych stron jest więcej niż jedna.
    """
    pages: list[tuple[int, str]] = []
    for number, page in enumerate(text.replace("\r\n", "\n").replace("\r", "\n").split("\f"), start=1):
        lines = (_SPACES.sub(" ", _FILL_RUN.sub("…", line)).strip() for line in page.split("\n"))
        body = "\n".join(line for line in lines if line)
        if body:
            pages.append((number, body))
    if len(pages) == 1:
        return pages[0][1]
    return "\n".join(f"--- Strona {number} ---\n{body}" for number, body in pages)


def _without_titles(node: Any) -> Any:
    """Pydantic dodaje "title" z nazwą klucza. Model ma już nazwę klucza, a powtórzenie to ok. 300 tokenów."""
    if isinstance(node, dict):
        return {key: _without_titles(value) for key, value in node.items() if not (key == "title" and isinstance(value, str))}
    if isinstance(node, list):
        return [_without_titles(item) for item in node]
    return node


@cache
def system_message_text() -> str:
    # Opisy pól w schemacie są instrukcją dla modelu (models.py), więc idą też w prompcie:
    # response_format ogranicza tylko składnię odpowiedzi.
    schema = json.dumps(_without_titles(FormAnalysis.model_json_schema()), ensure_ascii=False, separators=(",", ":"))
    return f"{SYSTEM_PROMPT}\n\nSchemat JSON:\n{schema}"


def user_message(doc: ExtractedDocument) -> Message:
    """Tekst, gdy jest. Obrazy stron tylko wtedy, gdy tekstu brak: w K1 skan w modelu był wolniejszy i gorszy."""
    text = prepare_text(doc.text)
    if text:
        source = f"Tekst formularza z pliku {doc.source_format.upper()}"
        if doc.ocr_used:
            source += ", odczytany przez OCR, więc może mieć błędy literowe"
        return {"role": "user", "content": f"{source}:\n\n{text}"}
    if doc.images:
        parts: list[Message] = [{"type": "text", "text": "Formularz jest na obrazach stron poniżej."}]
        parts += [image_part(image) for image in doc.images]
        return {"role": "user", "content": parts}
    # Bez treści model zmyśliłby formularz, zamiast go opisać.
    raise ExtractionError(detail=EMPTY_DOCUMENT_DETAIL)


def _size(messages: Sequence[Message]) -> tuple[int, int]:
    """Liczba znaków tekstu i liczba obrazów w zapytaniu."""
    chars = images = 0
    for message in messages:
        content = message["content"]
        for part in [{"type": "text", "text": content}] if isinstance(content, str) else content:
            if part["type"] == "text":
                chars += len(part["text"])
            else:
                images += 1
    return chars, images


def estimate_prompt_tokens(messages: Sequence[Message]) -> int:
    chars, images = _size(messages)
    return math.ceil(chars / CHARS_PER_TOKEN) + images * IMAGE_TOKENS + len(messages) * MESSAGE_TOKENS


def _ensure_fits(messages: Sequence[Message], attempt: int, context_tokens: int, max_tokens: int) -> None:
    """Za długie zapytanie serwer przyciąłby po cichu, razem z instrukcjami. Wtedy nie wysyłamy go wcale."""
    needed = estimate_prompt_tokens(messages) + max_tokens
    if needed > context_tokens:
        log.warning(
            "Analiza, próba %d: zapytanie z odpowiedzią to ok. %d tokenów, kontekst ma %d. "
            "Dokument wymaga analizy fragmentami albo większego kontekstu.",
            attempt,
            needed,
            context_tokens,
        )
        raise LLMUnavailable(detail=UNAVAILABLE_DETAIL)


def _ensure_not_truncated(messages: Sequence[Message], result: ChatResult, attempt: int, settings: Settings) -> None:
    """Serwer z kontekstem mniejszym niż skonfigurowany w aplikacji może przyciąć prompt bez błędu.

    Analiza części dokumentu przeszłaby walidację jako kompletna, więc za mało tokenów promptu to 503.
    """
    if result.prompt_tokens is None:
        return
    minimum = math.floor(_size(messages)[0] / MAX_CHARS_PER_TOKEN)
    if result.prompt_tokens < minimum:
        hint = " Sprawdź OLLAMA_CONTEXT_LENGTH." if provider(settings) == "ollama" else ""
        log.warning(
            "Analiza, próba %d: serwer policzył %d tokenów promptu, a tekst to co najmniej %d. "
            "Zapytanie zostało przycięte.%s",
            attempt,
            result.prompt_tokens,
            minimum,
            hint,
        )
        raise LLMUnavailable(detail=UNAVAILABLE_DETAIL)


def _location(loc: Sequence[int | str]) -> str:
    path = ""
    for part in loc:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}" if path else part
    return path or "cały JSON"


def correction_message(exc: ValidationError, finish_reason: str | None, intro: str = CORRECTION_INTRO) -> str:
    """Konkretne błędy walidatora dla modelu: miejsce i powód.

    Bez wartości wejściowych z Pydantic: powtórzone poddrzewa odpowiedzi zjadałyby budżet kontekstu.
    """
    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    lines = [TRUNCATED_NOTE] if finish_reason == "length" else []
    lines.append(intro)
    lines += [f"- {_location(error['loc'])}: {error['msg'].removeprefix('Value error, ')}" for error in errors[:MAX_REPORTED_ERRORS]]
    if len(errors) > MAX_REPORTED_ERRORS:
        lines.append(f"- … i {len(errors) - MAX_REPORTED_ERRORS} innych błędów")
    lines.append(CORRECTION_OUTRO)
    return "\n".join(lines)


def _validate(content: str) -> FormAnalysis:
    """Przez json.loads, bo parser Pydantic odrzuca samotny surogat (\\ud83d), zanim models.py zamieni go na U+FFFD."""
    try:
        data = json.loads(content)
    except (ValueError, RecursionError):
        # Błąd składni opisuje Pydantic, tak samo jak pozostałe błędy dla modelu.
        return FormAnalysis.model_validate_json(content)
    return FormAnalysis.model_validate(data)


def _retry_messages(
    base: list[Message], result: ChatResult, exc: ValidationError, attempt: int, context_tokens: int, max_tokens: int
) -> list[Message]:
    """Poprzednia odpowiedź z błędami. Gdy z nią zapytanie się nie mieści, same błędy: dokument zostaje cały."""
    full = [
        *base,
        {"role": "assistant", "content": result.content},
        {"role": "user", "content": correction_message(exc, result.finish_reason)},
    ]
    if estimate_prompt_tokens(full) + max_tokens <= context_tokens:
        return full
    log.info("Analiza, próba %d: ponowienie bez poprzedniej odpowiedzi, bo z nią nie mieści się w kontekście.", attempt + 1)
    return [*base, {"role": "user", "content": correction_message(exc, result.finish_reason, SHORT_CORRECTION_INTRO)}]


def _log_attempt(level: int, attempt: int, result: ChatResult, outcome: str) -> None:
    # Bez treści dokumentu i odpowiedzi: tylko liczby i wynik.
    log.log(
        level,
        "Analiza, próba %d/%d: %s, %.1f s, tokeny %s/%s, finish_reason=%s",
        attempt,
        MAX_ATTEMPTS,
        outcome,
        result.elapsed_s,
        result.prompt_tokens,
        result.completion_tokens,
        result.finish_reason,
    )


def analyze(
    doc: ExtractedDocument, *, settings: Settings, transport: httpx.BaseTransport | None = None
) -> FormAnalysis:
    """Opis formularza zwalidowany kontraktem FormAnalysis.

    settings podaje wołający, np. trasa z Depends(get_settings), więc dependency_overrides w testach
    obejmują też model i LLM_FIXTURE. Funkcja jest synchroniczna i na CPU trwa minuty.
    Błędy: ExtractionError (400), gdy dokument nie ma tekstu ani obrazów. LLMUnavailable (503), gdy
    model nie odpowiada, zapytanie nie mieści się w kontekście, serwer je przyciął albo po
    MAX_ATTEMPTS próbach wynik nie przechodzi FormAnalysis.model_validate.
    """
    base = [{"role": "system", "content": system_message_text()}, user_message(doc)]
    messages = base
    context_tokens = settings.llm_context_tokens
    max_tokens = answer_token_limit(settings)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        _ensure_fits(messages, attempt, context_tokens, max_tokens)
        result = chat_json(
            messages, FormAnalysis.model_json_schema(), settings=settings, max_tokens=max_tokens, transport=transport
        )
        if result.reasoning:
            log.warning("Analiza, próba %d: model zwrócił tok rozumowania (%d znaków).", attempt, len(result.reasoning))
        _ensure_not_truncated(messages, result, attempt, settings)
        try:
            analysis = _validate(result.content)
        except ValidationError as exc:
            kinds = ", ".join(sorted({error["type"] for error in exc.errors()}))
            _log_attempt(logging.WARNING, attempt, result, f"{exc.error_count()} błędów walidacji ({kinds})")
            messages = _retry_messages(base, result, exc, attempt, context_tokens, max_tokens)
            continue
        _log_attempt(logging.INFO, attempt, result, "poprawna analiza")
        return analysis
    raise LLMUnavailable(detail=UNAVAILABLE_DETAIL)
