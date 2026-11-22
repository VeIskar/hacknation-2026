"""Tekst dokumentu DOCX: akapity, tabele, pola tekstowe i tekst z osadzonych obrazów (OCR).

XML czytamy strumieniowo: w pamięci jest jeden blok treści (akapit albo tabela) naraz.
Pole tekstowe Word zapisuje dwa razy, w `mc:Choice` i w `mc:Fallback`; czytamy jedną gałąź.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from posixpath import join, normpath
from xml.etree import ElementTree

from app.errors import ExtractionError
from app.extract import images, ocr
from app.extract.common import (
    XML_ERRORS,
    Box,
    Reading,
    ZipParts,
    clean_text,
    completed,
    lines_by_position,
    unreadable,
)

MAX_DOCUMENT_XML_BYTES = 16 * 1024 * 1024
# Wspólny limit rozpakowanych bajtów: XML dokumentu, relacje i obrazy. Plik ma najwyżej 10 MB,
# a obrazy PNG i JPG prawie się nie kompresują, więc więcej oznacza bombę ZIP.
MAX_UNPACKED_BYTES = 64 * 1024 * 1024
MAX_PICTURES = 20
MAX_PICTURE_BYTES = 20 * 1024 * 1024
# Jak w PDF: czas OCR rośnie z liczbą pikseli, a cały odczyt ma limit czasu.
MAX_DOCUMENT_PIXELS = 400_000_000
_MAX_RELATIONSHIPS_BYTES = 1024 * 1024
# Formularze COI mają do 20 poziomów XML. Dokument z folderu 8 trzyma do 50 tys. elementów
# w jednym akapicie (strona złożona z pól tekstowych).
_MAX_XML_DEPTH = 100
_MAX_BLOCK_ELEMENTS = 500_000
# Tekst obrazu krótszy niż to jest szumem z logo albo ozdobnika.
_MIN_PICTURE_CHARS = 8
_DOCUMENT = "word/document.xml"
_RELATIONSHIPS = "word/_rels/document.xml.rels"
# Części z tekstem poza treścią główną, w kolejności dopisywania: przypisy, nagłówki, stopki.
_NOTES = re.compile(r"word/(footnotes|endnotes)\.xml")
_MARGINS = re.compile(r"word/(header|footer)\d*\.xml")
_MAX_MARGIN_PARTS = 30
_WORD_NAMESPACES = (
    "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "http://purl.oclc.org/ooxml/wordprocessingml/main",  # Strict Open XML
)
_ALTERNATE = "{http://schemas.openxmlformats.org/markup-compatibility/2006}AlternateContent"
_RELATIONSHIP = "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"
_BLOCKS = frozenset(f"{{{namespace}}}{name}" for namespace in _WORD_NAMESPACES for name in ("p", "tbl", "sdt"))
# `mc:AlternateContent` stoi też między akapitami: wtedy czytamy go w całości, żeby wziąć jedną gałąź.
_ITEMS = _BLOCKS | {_ALTERNATE}
_ROOT_NAMES = ("body", "document", "footnotes", "endnotes", "hdr", "ftr")
_ROOTS = frozenset(f"{{{namespace}}}{name}" for namespace in _WORD_NAMESPACES for name in _ROOT_NAMES)
_NOTE_MARKS = frozenset({"footnoteReference", "endnoteReference", "footnoteRef", "endnoteRef"})
# Położenie kotwicy jest w EMU; 635 EMU to twip, a tolerancja wiersza jak w czytniku DOC (90 twipów).
_ROW_TOLERANCE_EMU = 90 * 635
_PICTURE = re.compile("\x00(\\d+)\x00")
_NOT_WORD = re.compile(r"[\W_]+")
_OVER_LIMIT = f"Pominięto obrazy ponad limit {MAX_PICTURES} sztuk."
_OVER_PIXELS = "Pominięto obrazy, bo razem są za duże do odczytu."
_NOT_READ = "Części obrazów w dokumencie nie udało się odczytać."


@dataclass(frozen=True)
class _Shape:
    """Pole tekstowe albo obraz zakotwiczone w akapicie; `position` to (góra, lewa) albo None."""

    position: tuple[int, int] | None
    lines: tuple[str, ...]


def read(data: bytes, language: str) -> Reading:
    walker = _Walker()
    with ZipParts(data, MAX_UNPACKED_BYTES) as parts:
        lines = list(walker.lines(parts.read(_DOCUMENT, max_bytes=MAX_DOCUMENT_XML_BYTES)))
        if walker.roots != ["body", "document"]:
            raise unreadable()
        lines += _outside_body(parts)
        pictures, warnings = _pictures(parts, walker.pictures)
    recognized = _recognized(pictures, "\n".join(lines), language)
    ocr_used = bool(recognized)
    # Ten sam obraz bywa wstawiony wiele razy (logo w nagłówku każdej strony): tekst dajemy raz.
    # Wiersz, w którym stał tylko obraz bez nowego tekstu, znika.
    lines = [_PICTURE.sub(lambda match: recognized.pop(int(match[1]), ""), line) for line in lines]
    text = "\n".join(filter(None, lines))
    # \f to tylko nasz podział strony: XML 1.0 nie dopuszcza tego znaku w treści.
    pages = "\f".join(clean_text(page) for page in text.split("\f"))
    return Reading(pages, ocr_used=ocr_used, warnings=warnings)


def _outside_body(parts: ZipParts) -> list[str]:
    """Tekst przypisów oraz nagłówków i stopek; te ostatnie powtarzają się między sekcjami, więc raz."""
    names = sorted(parts.names())
    lines = []
    for name in filter(_NOTES.fullmatch, reversed(names)):  # footnotes przed endnotes
        lines += _Walker(pictures=False).lines(parts.read(name, max_bytes=MAX_DOCUMENT_XML_BYTES))
    margins = []
    for name in sorted(filter(_MARGINS.fullmatch, names), reverse=True)[:_MAX_MARGIN_PARTS]:  # header przed footer
        margins += _Walker(pictures=False).lines(parts.read(name, max_bytes=MAX_DOCUMENT_XML_BYTES))
    return lines + list(dict.fromkeys(margins))


class _Walker:
    """Zamienia bloki części dokumentu na wiersze tekstu i zbiera odwołania do obrazów."""

    def __init__(self, *, pictures: bool = True) -> None:
        # Identyfikatory relacji obrazów w kolejności pierwszego wystąpienia. Relacje nagłówków
        # i stopek są w osobnych plikach, więc ich obrazów nie zbieramy.
        self.pictures: list[str] = []
        self._collect_pictures = pictures
        self.roots: list[str] = []
        self._notes = 0

    def lines(self, xml: bytes) -> Iterator[str]:
        blocks = completed(xml, _ITEMS, _ROOTS, max_depth=_MAX_XML_DEPTH, max_item_elements=_MAX_BLOCK_ELEMENTS)
        for element in blocks:
            if element.tag in _ROOTS:
                self.roots.append(_word(element))
            else:
                yield from self._block(element)

    def _blocks(self, container: ElementTree.Element) -> Iterator[str]:
        for child in container:
            yield from self._block(child)

    def _block(self, block: ElementTree.Element) -> Iterator[str]:
        if block.tag == _ALTERNATE:
            yield from self._alternate_blocks(block)
            return
        name = _word(block)
        if name == "p":
            yield from self._paragraph(block)
        elif name == "tbl":
            for row in self._content(block, "tr"):
                cells = [" ".join(self._blocks(cell)) for cell in self._content(row, "tc")]
                if any(cells):
                    yield " | ".join(cells)
        elif name == "sdt":
            for content in block:
                if _word(content) == "sdtContent":
                    yield from self._blocks(content)

    def _alternate_blocks(self, node: ElementTree.Element) -> list[str]:
        """Bloki pierwszej gałęzi z treścią: `mc:Choice` w kolejności zapisu, potem `mc:Fallback`.

        Gałąź bez wierszy nie zostawia śladu: obraz i przypis zawsze dają wiersz.
        """
        for branch in sorted(node, key=lambda child: _local(child) != "Choice"):
            lines = list(self._blocks(branch))
            if lines:
                return lines
        return []

    def _content(self, container: ElementTree.Element, name: str) -> Iterator[ElementTree.Element]:
        """Dzieci `name`, także ukryte w kontrolkach treści `w:sdt`."""
        for child in container:
            kind = _word(child)
            if kind == name:
                yield child
            elif kind == "sdt":
                for content in child:
                    if _word(content) == "sdtContent":
                        yield from self._content(content, name)

    def _paragraph(self, paragraph: ElementTree.Element) -> list[str]:
        text: list[str] = []
        shapes: list[_Shape] = []
        self._inline(paragraph, text, shapes, None)
        line = "".join(text).strip(" \t\n")
        lines = [line] if line else []
        if len(shapes) > 1 and all(shape.position is not None for shape in shapes):
            boxes = [Box(*shape.position, shape.lines) for shape in shapes if shape.position]
            return lines + lines_by_position(boxes, _ROW_TOLERANCE_EMU)
        return lines + [line for shape in shapes for line in shape.lines]

    def _inline(
        self,
        node: ElementTree.Element,
        text: list[str],
        shapes: list[_Shape],
        position: tuple[int, int] | None,
    ) -> None:
        for child in node:
            name = _word(child)
            if name == "t":
                text.append(child.text or "")
            elif name == "tab":
                text.append("\t")
            elif name == "br":
                text.append("\f" if _attribute(child, "type") == "page" else "\n")
            elif name == "cr":
                text.append("\n")
            elif name == "noBreakHyphen":
                text.append("-")
            elif name in _NOTE_MARKS and not _attribute(child, "customMarkFollows"):
                # Numer przypisu Word wylicza przy wyświetlaniu; na papierze stoi kolejna liczba.
                self._notes += 1
                text.append(str(self._notes))
            elif name == "txbxContent":
                lines = tuple(self._blocks(child))
                if lines:
                    shapes.append(_Shape(position, lines))
            elif child.tag == _ALTERNATE:
                self._alternate(child, text, shapes, position)
            elif _local(child) in ("blip", "imagedata"):
                if self._collect_pictures:
                    shapes.append(_Shape(position, (self._picture(child),)))
            elif _local(child) == "anchor":
                self._inline(child, text, shapes, _position(child))
            else:
                self._inline(child, text, shapes, position)

    def _alternate(
        self,
        node: ElementTree.Element,
        text: list[str],
        shapes: list[_Shape],
        position: tuple[int, int] | None,
    ) -> None:
        """Pierwsza gałąź z treścią: `mc:Choice` w kolejności zapisu, potem `mc:Fallback`."""
        before = (len(text), len(shapes))
        for branch in sorted(node, key=lambda child: _local(child) != "Choice"):
            self._inline(branch, text, shapes, position)
            if (len(text), len(shapes)) != before:
                return

    def _picture(self, node: ElementTree.Element) -> str:
        """Znacznik miejsca obrazu w tekście. XML nie może zawierać znaku NUL, więc nie pomyli się z treścią."""
        relationship = _attribute(node, "embed") or _attribute(node, "id") or ""
        if relationship not in self.pictures:
            self.pictures.append(relationship)
        return f"\x00{self.pictures.index(relationship)}\x00"


def _local(element: ElementTree.Element) -> str:
    return element.tag.rpartition("}")[2]


def _word(element: ElementTree.Element) -> str:
    """Nazwa elementu WordprocessingML bez przestrzeni nazw; pusty tekst dla innych elementów."""
    namespace, _, name = element.tag[1:].partition("}")
    return name if namespace in _WORD_NAMESPACES else ""


def _attribute(element: ElementTree.Element, name: str) -> str | None:
    """Atrybut po nazwie bez przestrzeni nazw: dokument Strict ma inne przestrzenie niż zwykły."""
    return next((value for key, value in element.attrib.items() if key.rpartition("}")[2] == name), None)


def _position(anchor: ElementTree.Element) -> tuple[int, int] | None:
    offsets = {}
    for child in anchor:
        if _local(child) in ("positionV", "positionH"):
            offsets[_local(child)] = next((part.text for part in child if _local(part) == "posOffset"), None)
    try:
        return int(offsets["positionV"]), int(offsets["positionH"])
    except (KeyError, TypeError, ValueError):
        return None


def _pictures(parts: ZipParts, relationships: list[str]) -> tuple[dict[int, bytes], list[str]]:
    """Bajty obrazów wartych odczytu, pod numerem znacznika w tekście, oraz ostrzeżenia."""
    if not relationships or _RELATIONSHIPS not in parts.names():
        return {}, []
    targets = _targets(parts.read(_RELATIONSHIPS, max_bytes=_MAX_RELATIONSHIPS_BYTES))
    names = set(parts.names())
    pictures: dict[int, bytes] = {}
    warnings: list[str] = []
    seen = set()
    pixels = MAX_DOCUMENT_PIXELS
    for index, relationship in enumerate(relationships):
        name = targets.get(relationship)
        if name is None or name not in names or name in seen:
            continue
        seen.add(name)
        try:
            content = parts.read(name, max_bytes=MAX_PICTURE_BYTES)
        except ExtractionError:
            _warn(warnings, _NOT_READ)
            continue
        dimensions = images.size(content)
        if dimensions is None or not ocr.worth_reading(*dimensions):
            continue
        if len(pictures) == MAX_PICTURES:
            _warn(warnings, _OVER_LIMIT)
            break
        width, height = dimensions
        if width * height > pixels:
            _warn(warnings, _OVER_PIXELS)
            continue
        pixels -= width * height
        pictures[index] = content
    return pictures, warnings


def _warn(warnings: list[str], message: str) -> None:
    if message not in warnings:
        warnings.append(message)


def _targets(xml: bytes) -> dict[str, str]:
    """Identyfikator relacji -> nazwa części w archiwum; odwołania zewnętrzne pomijamy."""
    try:
        root = ElementTree.fromstring(xml)
    except XML_ERRORS as exc:
        raise unreadable() from exc
    targets = {}
    for relationship in root.iter(_RELATIONSHIP):
        # Cel zewnętrzny (adres URL) nie jest nazwą części archiwum, więc odpada przy odczycie.
        target = relationship.get("Target", "")
        path = target.removeprefix("/") if target.startswith("/") else normpath(join("word", target))
        targets[relationship.get("Id", "")] = path
    return targets


def _recognized(pictures: dict[int, bytes], text: str, language: str) -> dict[int, str]:
    """Tekst obrazów bez wierszy, które dokument już zawiera, pod numerem znacznika."""
    if not pictures:
        return {}
    known = _key(_PICTURE.sub("", text))
    recognized = {}
    for index, picture_text in zip(pictures, ocr.texts(list(pictures.values()), language), strict=True):
        fresh = []
        for line in picture_text.replace("\f", "\n").splitlines():
            key = _key(line)
            if len(key) > 1 and key not in known:
                fresh.append(line.strip())
                known += f"\n{key}"
        if sum(len(_key(line)) for line in fresh) >= _MIN_PICTURE_CHARS:
            recognized[index] = "\n".join(fresh)
    return recognized


def _key(text: str) -> str:
    """Tekst do porównań: same litery i cyfry, bez wielkości liter."""
    return _NOT_WORD.sub("", text).casefold()
