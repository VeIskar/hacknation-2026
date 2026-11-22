"""Tekst komórek arkuszy XLSX i ODS, czytany z XML w pamięci bez dodatkowych bibliotek.

Arkusz to strona (separator \\f), a wiersz to niepuste komórki „a | b”, jak wiersz tabeli DOCX.
Wchodzą wszystkie komórki z tekstem, także ukryte i przykryte scaleniem; komentarze nie wchodzą.
Liczby i daty z XLSX zostają w postaci zapisanej w pliku, bez formatu wyświetlania.
"""

import re
from collections.abc import Iterator
from posixpath import join, normpath
from urllib.parse import unquote
from xml.etree import ElementTree

from app.extract.common import XML_ERRORS, ZipParts, clean_text, completed, unreadable

# Wspólny limit rozpakowanych XML jednego pliku. Największy arkusz w materiałach COI ma 0,7 MB XML,
# a odczyt kosztuje ok. 0,3 s CPU na każdy 1 MB.
MAX_XML_BYTES = 8 * 1024 * 1024
# Limit tekstu, sprawdzany przed rozwinięciem powtórzeń ODS (pusty wiersz bywa powtórzony ponad
# milion razy). Kontekst modelu mieści ok. 40 tys. znaków, więc dłuższy tekst i tak nie przejdzie analizy.
MAX_TEXT_CHARS = 1_000_000
# Skoroszyt i jego relacje to tylko spis arkuszy: w materiałach COI do 2 KB.
_MAX_INDEX_XML_BYTES = 1024 * 1024
# Otwarte elementy i cała bieżąca komórka zostają w pamięci. Formularze COI mają do 12 poziomów
# i kilka elementów na komórkę; limity zatrzymują pliki, które tylko udają arkusz.
_MAX_XML_DEPTH = 100
_MAX_CELL_ELEMENTS = 10_000
_CELL_SEPARATOR = " | "
_BOOLEAN = {"1": "PRAWDA", "true": "PRAWDA", "0": "FAŁSZ", "false": "FAŁSZ"}

_XLSX_NAMESPACES = frozenset(
    {
        "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "http://purl.oclc.org/ooxml/spreadsheetml/main",  # Strict Open XML
    }
)
_RELATIONSHIP_IDS = (
    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id",
    "{http://purl.oclc.org/ooxml/officeDocument/relationships}id",
)
_RELATIONSHIP = "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"
_WORKBOOK = "xl/workbook.xml"
_WORKBOOK_RELATIONSHIPS = "xl/_rels/workbook.xml.rels"
# Excel zapisuje znaki niedozwolone w XML jako _xHHHH_ (ECMA-376, ST_Xstring).
_ESCAPED_CHARACTER = re.compile(r"_x([0-9A-Fa-f]{4})_")

_OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
_TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
_TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
_ODS_TABLE = f"{_TABLE}table"
_ODS_ROW = f"{_TABLE}table-row"
_ODS_CELLS = frozenset({f"{_TABLE}table-cell", f"{_TABLE}covered-table-cell"})
_ODS_PARAGRAPHS = frozenset({f"{_TEXT}p", f"{_TEXT}h"})
_ODS_ANNOTATION = f"{_OFFICE}annotation"
_ODS_STORED_VALUE = {
    "float": "value",
    "percentage": "value",
    "currency": "value",
    "string": "string-value",
    "date": "date-value",
    "time": "time-value",
    "boolean": "boolean-value",
}
# Ciąg spacji służy tylko układowi, a analiza i tak scala odstępy (K3).
_MAX_SPACES = 100


class _TextBudget:
    def __init__(self) -> None:
        self._remaining = MAX_TEXT_CHARS

    def take(self, chars: int) -> None:
        if chars > self._remaining:
            raise unreadable()
        self._remaining -= chars


class _Row:
    """Niepuste komórki bieżącego wiersza; koszt w budżecie liczony przed rozwinięciem powtórzeń."""

    def __init__(self, budget: _TextBudget) -> None:
        self._budget = budget
        self._cells: list[tuple[str, int]] = []
        self._width = 0

    def add(self, text: str, count: int = 1) -> None:
        if not text:
            return
        width = (len(text) + len(_CELL_SEPARATOR)) * count
        self._budget.take(width)
        self._width += width
        self._cells.append((text, count))

    def lines(self, rows: int = 1) -> list[str]:
        """Wiersz powtórzony `rows` razy; potem wiersz jest pusty i gotowy na następne komórki."""
        if not self._cells:
            return []
        self._budget.take(self._width * (rows - 1))
        line = _CELL_SEPARATOR.join(text for text, count in self._cells for _ in range(count))
        self._cells, self._width = [], 0
        return [line] * rows


def _completed(
    xml: bytes, items: frozenset[str], markers: frozenset[str] = frozenset()
) -> Iterator[ElementTree.Element]:
    return completed(xml, items, markers, max_depth=_MAX_XML_DEPTH, max_item_elements=_MAX_CELL_ELEMENTS)


def _parse(xml: bytes) -> ElementTree.Element:
    try:
        return ElementTree.fromstring(xml)
    except XML_ERRORS as exc:
        raise unreadable() from exc


class _Package:
    """Części pakietu OPC. Nazwy części to URI bez rozróżniania wielkości liter (ECMA-376 cz. 2)."""

    def __init__(self, parts: ZipParts) -> None:
        self._parts = parts
        self._names = {name.casefold(): name for name in parts.names()}

    def read(self, part: str, *, max_bytes: int | None = None) -> bytes:
        name = self._names.get(normpath(unquote(part)).casefold())
        if name is None:
            raise unreadable()
        return self._parts.read(name, max_bytes=max_bytes)


def xlsx_text(data: bytes) -> str:
    budget = _TextBudget()
    with ZipParts(data, MAX_XML_BYTES) as parts:
        package = _Package(parts)
        workbook = _parse(package.read(_WORKBOOK, max_bytes=_MAX_INDEX_XML_BYTES))
        ns = _spreadsheet_namespace(workbook)
        relationships = _parse(package.read(_WORKBOOK_RELATIONSHIPS, max_bytes=_MAX_INDEX_XML_BYTES))
        targets = _relationship_targets(relationships)
        shared = [
            _xlsx_string(item, ns)
            for kind, path in targets.values()
            if kind == "sharedStrings"
            for item in _completed(package.read(path), frozenset({f"{ns}si"}))
        ]
        pages = []
        for sheet in workbook.iterfind(f"{ns}sheets/{ns}sheet"):
            kind, path = targets.get(_relationship_id(sheet), (None, ""))
            if kind is None:
                raise unreadable()
            # Arkusz wykresu albo okna dialogowego ma relację innego typu i nie ma komórek.
            if kind == "worksheet":
                pages.append(_xlsx_sheet_text(package.read(path), ns, shared, budget))
    return "\f".join(page for page in pages if page)


def _spreadsheet_namespace(workbook: ElementTree.Element) -> str:
    namespace, _, local_name = workbook.tag.removeprefix("{").partition("}")
    if local_name != "workbook" or namespace not in _XLSX_NAMESPACES:
        raise unreadable()
    return f"{{{namespace}}}"


def _relationship_targets(relationships: ElementTree.Element) -> dict[str | None, tuple[str, str]]:
    """Id relacji -> (typ, ścieżka części). Cel bez ukośnika na początku jest względny wobec xl/."""
    targets = {}
    for relationship in relationships.iter(_RELATIONSHIP):
        target = relationship.get("Target", "")
        path = target.removeprefix("/") if target.startswith("/") else join("xl", target)
        kind = relationship.get("Type", "").rpartition("/")[2]
        targets[relationship.get("Id")] = (kind, path)
    return targets


def _relationship_id(sheet: ElementTree.Element) -> str | None:
    return next((sheet.get(name) for name in _RELATIONSHIP_IDS if name in sheet.attrib), None)


def _xlsx_sheet_text(xml: bytes, ns: str, shared: list[str], budget: _TextBudget) -> str:
    lines = []
    row = _Row(budget)
    for element in _completed(xml, frozenset({f"{ns}c"}), markers=frozenset({f"{ns}row"})):
        if element.tag == f"{ns}c":
            row.add(_xlsx_cell_text(element, ns, shared))
        else:
            lines.extend(row.lines())
    return "\n".join(lines)


def _xlsx_cell_text(cell: ElementTree.Element, ns: str, shared: list[str]) -> str:
    kind = cell.get("t", "n")
    if kind == "inlineStr":
        inline = cell.find(f"{ns}is")
        return "" if inline is None else _xlsx_string(inline, ns)
    value = cell.findtext(f"{ns}v")
    if value is None:
        return ""
    if kind == "s":
        try:
            index = int(value)
        except ValueError as exc:
            raise unreadable() from exc
        if not 0 <= index < len(shared):
            raise unreadable()
        return shared[index]
    if kind == "b":
        return _BOOLEAN.get(value.strip(), clean_text(value))
    return _clean_xlsx(value)


def _xlsx_string(node: ElementTree.Element, ns: str) -> str:
    """Tekst `si` albo `is`: zwykły `t` lub kolejne fragmenty `r/t`; fonetyka `rPh` pominięta."""
    parts = [node.findtext(f"{ns}t", "")]
    parts.extend(run.findtext(f"{ns}t", "") for run in node.iterfind(f"{ns}r"))
    return _clean_xlsx("".join(parts))


def _clean_xlsx(text: str) -> str:
    return clean_text(_ESCAPED_CHARACTER.sub(lambda match: chr(int(match[1], 16)), text))


def ods_text(data: bytes) -> str:
    budget = _TextBudget()
    with ZipParts(data, MAX_XML_BYTES) as parts:
        xml = parts.read("content.xml")
    pages: list[str] = []
    lines: list[str] = []
    row = _Row(budget)
    for element in _completed(xml, _ODS_CELLS, markers=frozenset({_ODS_ROW, _ODS_TABLE})):
        if element.tag in _ODS_CELLS:
            row.add(_ods_cell_text(element), _repeat(element, f"{_TABLE}number-columns-repeated"))
        elif element.tag == _ODS_ROW:
            lines.extend(row.lines(_repeat(element, f"{_TABLE}number-rows-repeated")))
        else:
            pages.append("\n".join(lines))
            lines = []
    return "\f".join(page for page in pages if page)


def _repeat(element: ElementTree.Element, attribute: str) -> int:
    """Liczba powtórzeń z atrybutu ODF; brak albo wartość niedodatnia lub nieliczbowa to 1."""
    try:
        count = int(element.get(attribute, "1"))
    except ValueError:
        return 1
    return max(count, 1)


def _ods_cell_text(cell: ElementTree.Element) -> str:
    # Rekurencja niżej jest płytka: _completed odrzuca XML głębszy niż _MAX_XML_DEPTH.
    paragraphs = [_odf_inline(paragraph) for paragraph in _odf_paragraphs(cell)]
    if paragraphs:
        return clean_text("\n".join(paragraphs))
    # Bez akapitu zostaje wartość zapisana w atrybucie, zależnie od typu komórki.
    value_type = cell.get(f"{_OFFICE}value-type", "")
    attribute = _ODS_STORED_VALUE.get(value_type)
    value = cell.get(f"{_OFFICE}{attribute}", "") if attribute else ""
    if value_type == "boolean":
        return _BOOLEAN.get(value, clean_text(value))
    return clean_text(value)


def _odf_paragraphs(element: ElementTree.Element) -> Iterator[ElementTree.Element]:
    for child in element:
        if child.tag in _ODS_PARAGRAPHS:
            yield child
        elif child.tag != _ODS_ANNOTATION:
            yield from _odf_paragraphs(child)


def _odf_inline(element: ElementTree.Element) -> str:
    parts = [element.text or ""]
    for child in element:
        if child.tag == f"{_TEXT}s":
            parts.append(" " * min(_repeat(child, f"{_TEXT}c"), _MAX_SPACES))
        elif child.tag == f"{_TEXT}tab":
            parts.append("\t")
        elif child.tag == f"{_TEXT}line-break":
            parts.append("\n")
        elif child.tag in _ODS_PARAGRAPHS:
            parts.append("\n" + _odf_inline(child))
        elif child.tag != _ODS_ANNOTATION:
            parts.append(_odf_inline(child))
        parts.append(child.tail or "")
    return "".join(parts)
