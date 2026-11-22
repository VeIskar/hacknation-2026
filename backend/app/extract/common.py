"""Elementy wspólne czytników: wynik odczytu, błąd odczytu, czyszczenie tekstu oraz ZIP i XML z limitami."""

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from functools import partial
from io import BytesIO
from types import TracebackType
from typing import Self
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from app.errors import AppError, ExtractionError
from app.files import ZIP_ERRORS

UNREADABLE = "Nie udało się odczytać treści pliku."
SERVER_ERROR = "Coś poszło nie tak. Spróbuj ponownie."
# Znaki sterujące poza tabulatorem i końcem wiersza oraz niesparowane surogaty UTF-16. Font PDF albo
# komórka arkusza mogą je oddać jako tekst, a \f rozdziela strony i surogat nie daje się zapisać w UTF-8.
NOT_TEXT = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\ud800-\udfff]")
# Limit tekstu jednego dokumentu. Kontekst modelu mieści ok. 40 tys. znaków, więc dłuższy tekst
# i tak nie przejdzie analizy, a jego składanie kosztuje pamięć.
MAX_TEXT_CHARS = 1_000_000
XML_ERRORS = (
    ElementTree.ParseError,
    # Deklaracja kodowania wielobajtowego (ValueError) albo nieznanego (LookupError).
    ValueError,
    LookupError,
)
# Office zapisuje tylko wpisy bez kompresji i deflate. Dla bzip2 i lzma zipfile rozpakowuje cały
# blok wejścia naraz, więc limit odczytu nie ogranicza tam pamięci.
_COMPRESSION = frozenset({ZIP_STORED, ZIP_DEFLATED})


@dataclass
class Reading:
    """Wynik czytnika jednego formatu. Strony tekstu rozdziela \\f."""

    text: str
    ocr_used: bool = False
    warnings: list[str] = field(default_factory=list)


def unreadable() -> ExtractionError:
    return ExtractionError(detail=UNREADABLE)


class SetupError(AppError):
    """Środowisko API nie pozwala odczytać pliku: brak programu, danych języka albo biblioteki (500).

    `reason` trafia do logu API, a użytkownik dostaje ogólny komunikat. Nie cytuje dokumentu.
    """

    def __init__(self, *, reason: str) -> None:
        super().__init__(detail=SERVER_ERROR)
        self.reason = reason

    def __reduce__(self) -> tuple:
        # Konstruktor bazowy przyjmuje detail i kod, ten tylko powód: kopia i pickle odtwarzają go po powodzie.
        return (partial(SetupError, reason=self.reason), ())


def clean_text(text: str) -> str:
    """Końce wierszy jako \\n, inne znaki sterujące jako spacja, bez odstępów na brzegach."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return NOT_TEXT.sub(" ", text).strip()


class ZipParts:
    """Wpisy archiwum ZIP czytane w pamięci, ze wspólnym limitem rozpakowanych bajtów dla całego pliku."""

    def __init__(self, data: bytes, max_bytes: int) -> None:
        try:
            self._archive = ZipFile(BytesIO(data))
        except ZIP_ERRORS as exc:
            raise unreadable() from exc
        self._remaining = max_bytes

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        self._archive.close()

    def names(self) -> list[str]:
        return self._archive.namelist()

    def read(self, name: str, *, max_bytes: int | None = None) -> bytes:
        """Treść wpisu. Brak wpisu, uszkodzenie, inna kompresja albo przekroczenie limitu to ExtractionError."""
        limit = self._remaining if max_bytes is None else min(max_bytes, self._remaining)
        try:
            info = self._archive.getinfo(name)
            if info.compress_type not in _COMPRESSION:
                raise unreadable()
            with self._archive.open(info) as entry:
                content = entry.read(limit + 1)
        except ZIP_ERRORS as exc:
            raise unreadable() from exc
        if len(content) > limit:
            raise unreadable()
        self._remaining -= len(content)
        return content


def completed(
    xml: bytes,
    items: frozenset[str],
    markers: frozenset[str] = frozenset(),
    *,
    max_depth: int,
    max_item_elements: int,
) -> Iterator[ElementTree.Element]:
    """Zamknięte elementy `items` (z całym poddrzewem) i `markers`, które leżą poza `items`.

    Element zamknięty poza `items` znika z drzewa zaraz po przetworzeniu, więc w pamięci są tylko
    otwarte elementy i jeden element `items` naraz. Głębsze zagnieżdżenie niż `max_depth` albo
    więcej niż `max_item_elements` elementów w jednym `items` to ExtractionError.
    """
    open_elements: list[ElementTree.Element] = []
    open_items = 0
    item_elements = 0
    try:
        for event, element in ElementTree.iterparse(BytesIO(xml), events=("start", "end")):
            if event == "start":
                open_elements.append(element)
                if len(open_elements) > max_depth:
                    raise unreadable()
                if open_items:
                    item_elements += 1
                    if item_elements > max_item_elements:
                        raise unreadable()
                elif element.tag in items:
                    item_elements = 0
                open_items += element.tag in items
                continue
            open_elements.pop()
            open_items -= element.tag in items
            if open_items:
                continue
            if element.tag in items or element.tag in markers:
                yield element
            if open_elements:
                # Wcześniejsze rodzeństwo już usunięto, a późniejsze jeszcze nie powstało.
                del open_elements[-1][-1]
    except XML_ERRORS as exc:
        raise unreadable() from exc


@dataclass(frozen=True)
class Box:
    """Pole tekstowe z położeniem lewego górnego rogu w jednostkach pliku źródłowego."""

    top: int
    left: int
    lines: tuple[str, ...]


def lines_by_position(boxes: Sequence[Box], tolerance: int) -> list[str]:
    """Wiersze tekstu z pól ułożonych jak na stronie: z góry na dół, a w wierszu od lewej.

    Dokument przerobiony z PDF trzyma każdy fragment wiersza w osobnym polu, a kolejność pól
    w pliku bywa odwrotna do kolejności czytania. Pola o górnej krawędzi nie dalej niż `tolerance`
    od pierwszego pola wiersza tworzą jeden wiersz.
    """
    rows: list[list[Box]] = []
    for box in sorted(boxes, key=lambda item: (item.top, item.left)):
        if rows and box.top - rows[-1][0].top <= tolerance:
            rows[-1].append(box)
        else:
            rows.append([box])
    lines: list[str] = []
    for row in rows:
        if len(row) == 1:
            lines.extend(row[0].lines)
        else:
            lines.append(" ".join(" ".join(box.lines) for box in sorted(row, key=lambda item: item.left)))
    return lines
