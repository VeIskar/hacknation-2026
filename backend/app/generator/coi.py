"""Klocki formatu COI (SZABLONY_SEKCJI.md, rozdz. 0): nazwy, HTML, jsonata, pola, sekcje i strony.

Moduł nie zna treści wniosku. Treść składają template.py (część stała) i form.py (przedmiot).
"""

import html
import re
import unicodedata
from collections.abc import Iterable, Iterator

# Klucze, które obiekt `field` ma zawsze, w kolejności ze wzorców COI.
FIELD_KEYS = (
    "id",
    "type",
    "techName",
    "title",
    "description",
    "options",
    "validation",
    "readOnly",
    "repeatingSectionGrid",
    "states",
    "questionOrder",
    "tooltipMessage",
)
COLS = 3
MAX_TECH_NAME = 60

# NFKD rozkłada ą, ę, ó, ś, ź, ż, ć, ń na literę i znak diakrytyczny. Tych liter nie rozkłada.
_NOT_DECOMPOSED = str.maketrans(
    {
        "ł": "l", "Ł": "L", "ß": "ss", "ẞ": "SS", "ø": "o", "Ø": "O",
        "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "đ": "d", "Đ": "D",
    }
)


def slug(text: str) -> str:
    """'Wybierz, jako kto wnioskujesz' -> 'wybierz_jako_kto_wnioskujesz'. Pusty, gdy brak liter i cyfr."""
    decomposed = unicodedata.normalize("NFKD", text.translate(_NOT_DECOMPOSED))
    ascii_text = decomposed.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_")


def shorten(name: str) -> str:
    """techName najwyżej MAX_TECH_NAME znaków, ucięte na granicy słowa (_), jeśli się da."""
    if len(name) <= MAX_TECH_NAME:
        return name
    head = name[:MAX_TECH_NAME]
    if name[MAX_TECH_NAME] != "_" and "_" in head:
        head = head[: head.rindex("_")]
    return head.rstrip("_")


class Names:
    """Zbiór unikalnych techName: pierwsza nazwa zostaje, kolejne kolizje dostają _2, _3.

    Nazwa jest przycinana do MAX_TECH_NAME przed dodaniem sufiksu, więc sufiks nigdy nie ginie.
    """

    def __init__(self) -> None:
        self._taken: set[str] = set()

    def reserve(self, name: str) -> None:
        """Nazwa ze szablonu. Kolizja oznacza błąd w szablonie, nie w danych od modelu."""
        if name in self._taken:
            raise ValueError(f"techName '{name}' występuje w szablonie dwa razy")
        self._taken.add(name)

    def claim(self, text: str, fallback: str) -> str:
        base = shorten(slug(text)) or fallback
        name, number = base, 2
        while name in self._taken:
            name, number = f"{base}_{number}", number + 1
        self._taken.add(name)
        return name


# --- HTML -----------------------------------------------------------------------------------------


def html_document(body: str = "") -> str:
    return f"<html><head></head><body>{body}</body></html>"


def paragraphs(text: str) -> str:
    """Tekst od modelu jako akapity HTML. Escapuje <, > i &, więc model nie wstrzyknie znaczników."""
    lines = (line.strip() for line in text.splitlines())
    return "".join(f"<p>{html.escape(line, quote=False)}</p>" for line in lines if line)


def field_description(text: str) -> str:
    """Opis pola: "" gdy pusty, inaczej dokument HTML (SZABLONY, rozdz. 0)."""
    body = paragraphs(text)
    return html_document(body) if body else ""


def link(href: str, text: str) -> str:
    """Link do strony zewnętrznej; dostępna nazwa mówi, że otworzy się nowa karta."""
    return (
        f'<a href="{html.escape(href)}" rel="noopener noreferrer" target="_blank" '
        f'aria-label="{html.escape(text)} (link otwiera się w nowej karcie)">{html.escape(text)}</a>'
    )


# --- jsonata --------------------------------------------------------------------------------------

_JSONATA_ESCAPES = {"\\": "\\\\", "\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def jsonata_string(text: str, quote: str = '"') -> str:
    """Literał tekstowy jsonaty w cudzysłowie albo apostrofie.

    JSONata zna tylko sekwencje \\" \\\\ \\/ \\b \\f \\n \\r \\t \\uXXXX. Nie ma \\', więc apostrof
    w literale '...' zapisujemy jako \\u0027.
    """
    escaped_quote = '\\"' if quote == '"' else "\\u0027"
    chars = []
    for char in text:
        if char == quote:
            chars.append(escaped_quote)
        elif char in _JSONATA_ESCAPES:
            chars.append(_JSONATA_ESCAPES[char])
        elif ord(char) < 0x20:
            chars.append(f"\\u{ord(char):04x}")
        else:
            chars.append(char)
    return quote + "".join(chars) + quote


def _answer(option: str, page: str, section: str, field_name: str) -> str:
    # Format 1:1 z COI: opcja w cudzysłowie, tytuł strony i techName w apostrofach.
    page, section, field_name = (jsonata_string(text, "'") for text in (page, section, field_name))
    return (
        f"{jsonata_string(option)} in tabs[{page} in title].questions[{section} in field.techName]"
        f".field.repeatingSectionGrid[{field_name} in field.techName].field.__userAnswer"
    )


def answer_is(option: str, page: str, section: str, field_name: str) -> str:
    """("<opcja>" in tabs['<strona>' in title]…['<pole>' in field.techName].field.__userAnswer)"""
    return f"({_answer(option, page, section, field_name)})"


def answer_is_not(option: str, page: str, section: str, field_name: str) -> str:
    return f"$not({_answer(option, page, section, field_name)})"


def show(query: str) -> list[dict]:
    return [{"type": "SHOW", "query": query}]


# --- pola, sekcje, strony -------------------------------------------------------------------------


def choice_options(names: Iterable[str]) -> list[dict]:
    """Opcje RADIO, CHECKBOX, SELECT: id = nazwa (jak we wzorcach), techName unikalne w polu."""
    local = Names()
    return [{"id": name, "name": name, "techName": local.claim(name, "opcja")} for name in names]


def field(
    kind: str,
    tech_name: str,
    title: str = "",
    *,
    description: str = "",
    options: Iterable[str] = (),
    validation: Iterable[str] = (),
    read_only: bool = False,
    states: Iterable[dict] = (),
    **extra: object,
) -> dict:
    """Obiekt `field` ze wszystkimi kluczami. `extra`: defaultValue, dictionaryName i podobne.

    id i questionOrder ustawiają później build_form i układ sekcji.
    """
    data = {
        "id": "",
        "type": kind,
        "techName": tech_name,
        "title": title,
        "description": description,
        "options": choice_options(options),
        "validation": list(validation),
        "readOnly": read_only,
        "repeatingSectionGrid": [],
        "states": list(states),
        "questionOrder": 0,
        "tooltipMessage": "",
    }
    data.update(extra)
    return data


def section(tech_name: str, title: str, fields: list[dict], *, body: str = "", states: Iterable[dict] = ()) -> dict:
    """Sekcja z polami w siatce: pole ma y = indeks, rows 1 i questionOrder = y."""
    data = field("SECTION", tech_name, title, description=html_document(body), states=states)
    for index, item in enumerate(fields):
        item["questionOrder"] = index
        data["repeatingSectionGrid"].append({"x": 0, "y": index, "rows": 1, "cols": COLS, "field": item})
    return data


def tab(title: str, sections: list[dict], kind: str = "MAIN") -> dict:
    """Strona: sekcja ma rows = liczba pól + 1, y = suma rows poprzednich, questionOrder = y."""
    questions, y = [], 0
    for item in sections:
        rows = len(item["repeatingSectionGrid"]) + 1
        item["questionOrder"] = y
        questions.append({"x": 0, "y": y, "rows": rows, "cols": COLS, "field": item})
        y += rows
    return {"id": "", "title": title, "type": kind, "questions": questions}


def iter_fields(page: dict) -> Iterator[dict]:
    """Sekcje strony i ich pola, w kolejności wyświetlania."""
    for question in page["questions"]:
        yield question["field"]
        for item in question["field"]["repeatingSectionGrid"]:
            yield item["field"]
