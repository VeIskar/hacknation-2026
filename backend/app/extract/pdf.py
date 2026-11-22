"""Tekst PDF: warstwa tekstowa przez pypdf, a dla stron bez użytecznego tekstu OCR obrazów strony.

Strony nie renderujemy: dopuszczalnego licencyjnie renderera nie ma w projekcie (PyMuPDF, Poppler
i Ghostscript są zabronione). Skan to obraz osadzony w stronie, więc wyjmujemy go z pliku i podajemy
Tesseractowi. Nie obsłużymy tak strony z tekstem zamienionym na krzywe ani obrazów JBIG2 i JPEG 2000.
"""

import re
import struct
import zlib
from io import BytesIO
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PyPdfError
from pypdf.generic import ContentStream

from app.errors import ExtractionError
from app.extract import ocr
from app.extract.common import MAX_TEXT_CHARS, NOT_TEXT, Reading, unreadable

# Najdłuższy formularz COI (folder 9) ma 16 stron. Więcej stron niż limit nie zmieści się
# w kontekście modelu, a każda kosztuje czas odczytu.
MAX_PAGES = 100
# Strona z mniejszą liczbą liter i cyfr ma sam numer albo stempel: jej treść jest w skanie.
MIN_PAGE_CHARS = 20
MAX_PICTURES = 40
MAX_PAGE_PICTURES = 10
MAX_DOCUMENT_PIXELS = 400_000_000
# Operacje rysowania przeglądane w poszukiwaniu skanów, razem dla wszystkich stron. Strona skanu ma
# ich kilka; zapętlony albo rozgałęziony formularz wyczerpuje limit w ułamku sekundy.
MAX_DRAWING_OPERATIONS = 200_000
_MAX_FORM_DEPTH = 4
_IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
_JPEG_FILTERS = frozenset({"/DCTDecode", "/DCT"})
_FAX_FILTERS = frozenset({"/CCITTFaxDecode", "/CCF"})
# Tych kodowań nie zdekodujemy: JBIG2 wymaga programu jbig2dec (AGPL), a JPEG 2000 nie ma
# dekodera w obrazie API, który dałoby się sprawdzić.
_UNSUPPORTED_FILTERS = frozenset({"/JBIG2Decode", "/JPXDecode"})
_GRAY_SPACES = frozenset({"/DeviceGray", "/CalGray", "/G"})
_RGB_SPACES = frozenset({"/DeviceRGB", "/CalRGB", "/RGB"})
_PNG_GRAY, _PNG_RGB, _PNG_PALETTE = 0, 2, 3
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# Tyle obrazów zbieramy z jednej strony, zanim wybierzemy najwyżej położone.
_MAX_DRAWN = 200
_INVERTED = bytes(255 - value for value in range(256))
_WORD_CHARACTER = re.compile(r"[^\W_]")
_UNSUPPORTED = object()
# Błędy, którymi pypdf i nasz odczyt obrazu reagują na uszkodzony obiekt PDF.
_PDF_ERRORS = (
    PyPdfError,
    ArithmeticError,
    AssertionError,
    AttributeError,
    LookupError,
    NotImplementedError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
    struct.error,
    zlib.error,
)


def read(data: bytes, language: str) -> Reading:
    pages, pictures, undecoded = _layers(data)
    recognized = iter(ocr.texts([picture for page in pictures.values() for picture in page], language))
    ocr_used = False
    for index, page_pictures in pictures.items():
        scanned = "\n".join(filter(None, (next(recognized) for _ in page_pictures)))
        if scanned:
            ocr_used = True
            stamp = pages[index]
            # Numer strony albo stempel z warstwy tekstowej zostaje, jeśli skan go nie zawiera.
            pages[index] = scanned if _key(stamp) in _key(scanned) else f"{stamp}\n{scanned}"
    warnings = []
    without_text = [str(number) for number, page in enumerate(pages, start=1) if not page]
    if without_text:
        warnings.append(f"Strony PDF bez warstwy tekstowej: {', '.join(without_text)}.")
    if undecoded:
        warnings.append(f"Strony PDF ze skanem w nieobsługiwanym kodowaniu: {', '.join(map(str, undecoded))}.")
    return Reading("\f".join(pages), ocr_used=ocr_used, warnings=warnings)


def _layers(data: bytes) -> tuple[list[str], dict[int, list[bytes]], list[int]]:
    """Tekst stron, obrazy stron bez użytecznego tekstu i numery stron z obrazem nie do zdekodowania."""
    pages: list[str] = []
    pictures: dict[int, list[bytes]] = {}
    undecoded: list[int] = []
    try:
        reader = PdfReader(BytesIO(data))
        budget = _Budget(reader)
        if len(reader.pages) > MAX_PAGES:
            raise unreadable()
        characters = 0
        for index, page in enumerate(reader.pages):
            text = NOT_TEXT.sub(" ", page.extract_text()).strip()
            characters += len(text)
            if characters > MAX_TEXT_CHARS:
                raise unreadable()
            pages.append(text)
            if len(_WORD_CHARACTER.findall(text)) < MIN_PAGE_CHARS:
                found, unsupported = _page_pictures(page, budget)
                if found:
                    pictures[index] = found
                if unsupported:
                    undecoded.append(index + 1)
    except ExtractionError:
        raise
    # Na uszkodzonym pliku pypdf zgłasza też wyjątki spoza PyPdfError (NotImplementedError,
    # TypeError, AttributeError, AssertionError). Każdy znaczy to samo: treści nie da się odczytać.
    except Exception as exc:
        raise unreadable() from exc
    return pages, pictures, undecoded


class _Budget:
    """Wspólne limity jednego dokumentu: obrazy i piksele do OCR oraz operacje rysowania do przejrzenia."""

    def __init__(self, reader: PdfReader) -> None:
        self.pictures = MAX_PICTURES
        self.pixels = MAX_DOCUMENT_PIXELS
        self.operations = MAX_DRAWING_OPERATIONS
        self._reader = reader
        # id formularza -> (formularz, jego strumień); formularz trzymamy, żeby jego id nie wróciło.
        self._forms: dict[int, tuple[Any, ContentStream]] = {}

    def take(self, pixels: int) -> bool:
        if not self.pictures or pixels > self.pixels:
            return False
        self.pictures -= 1
        self.pixels -= pixels
        return True

    def form(self, target: Any) -> ContentStream:
        """Strumień formularza, parsowany raz na dokument, choćby strony rysowały go wiele razy."""
        if id(target) not in self._forms:
            self._forms[id(target)] = (target, ContentStream(target, self._reader))
        return self._forms[id(target)][1]


def _page_pictures(page: Any, budget: _Budget) -> tuple[list[bytes], bool]:
    """Obrazy narysowane na stronie, od góry do dołu, jako pliki dla Tesseracta; i czy coś pominięto."""
    try:
        drawn: list[tuple[float, float, Any]] = []
        _collect(page.get_contents(), page.get("/Resources"), budget, _IDENTITY, (), drawn)
    # Tekst strony już mamy. Zepsuty strumień rysowania odbiera tylko jej obrazy.
    except _PDF_ERRORS:
        return [], False
    files: list[bytes] = []
    unsupported = False
    for _, _, picture in sorted(drawn, key=lambda item: (-item[0], item[1]))[:MAX_PAGE_PICTURES]:
        try:
            converted = _picture_file(picture, budget)
        except _PDF_ERRORS:
            converted = _UNSUPPORTED
        if converted is _UNSUPPORTED:
            unsupported = True
        elif isinstance(converted, bytes):
            files.append(converted)
    return files, unsupported


def _collect(
    content: Any,
    resources: Any,
    budget: _Budget,
    matrix: tuple[float, ...],
    path: tuple[int, ...],
    drawn: list[tuple[float, float, Any]],
) -> None:
    """Dopisuje do `drawn` obrazy rysowane operatorem Do: (górna krawędź, lewa krawędź, obiekt).

    `path` to id formularzy rysowanych w tej chwili: formularz, który rysuje siebie albo przodka,
    pomijamy. Każda przejrzana operacja zużywa budżet dokumentu.
    """
    if content is None or resources is None:
        return
    objects = resources.get_object().get("/XObject")
    if objects is None:
        return
    objects = objects.get_object()
    stack: list[tuple[float, ...]] = []
    for operands, operator in content.operations:
        if len(drawn) >= _MAX_DRAWN or not budget.operations:
            return
        budget.operations -= 1
        if operator == b"q":
            stack.append(matrix)
        elif operator == b"Q":
            matrix = stack.pop() if stack else matrix
        elif operator == b"cm" and len(operands) == 6:
            matrix = _multiply(tuple(float(value) for value in operands), matrix)
        elif operator == b"Do" and operands and operands[0] in objects:
            target = objects[operands[0]].get_object()
            if target.get("/Subtype") == "/Image":
                a, b, c, d, e, f = matrix
                drawn.append((f + max(0.0, b, d, b + d), e + min(0.0, a, c, a + c), target))
            elif target.get("/Subtype") == "/Form" and len(path) < _MAX_FORM_DEPTH and id(target) not in path:
                inner = _multiply(tuple(float(value) for value in target.get("/Matrix", _IDENTITY)), matrix)
                resources_inner = target.get("/Resources", resources)
                _collect(budget.form(target), resources_inner, budget, inner, (*path, id(target)), drawn)


def _multiply(first: tuple[float, ...], second: tuple[float, ...]) -> tuple[float, ...]:
    """Złożenie przekształceń PDF: najpierw `first`, potem `second`."""
    a, b, c, d, e, f = first
    g, h, i, j, k, m = second
    return (a * g + b * i, a * h + b * j, c * g + d * i, c * h + d * j, e * g + f * i + k, e * h + f * j + m)


def _picture_file(picture: Any, budget: _Budget) -> Any:
    """Obraz jako plik JPEG, TIFF albo PNG; None dla obrazu pomijanego; _UNSUPPORTED bez dekodera."""
    width, height = int(picture.get("/Width", 0)), int(picture.get("/Height", 0))
    if not ocr.worth_reading(width, height) or not budget.take(width * height):
        return None
    filters = _names(picture.get("/Filter"))
    if width * height > ocr.MAX_IMAGE_PIXELS or _UNSUPPORTED_FILTERS.intersection(filters):
        return _UNSUPPORTED
    data = picture.get_data()
    # Dla JPEG i faksu pypdf oddaje gotowy plik: JPEG bez zmian, faks z nagłówkiem TIFF.
    if filters and (filters[-1] in _JPEG_FILTERS or filters[-1] in _FAX_FILTERS):
        return data
    return _png(picture, width, height, data)


def _names(value: Any) -> list[str]:
    if value is None:
        return []
    value = value.get_object()
    return [str(item.get_object()) for item in value] if isinstance(value, list) else [str(value)]


def _channels(space: Any) -> int:
    """Liczba składowych przestrzeni barw: 1 dla szarości, 3 dla RGB, 0 dla nieobsługiwanej."""
    space = space.get_object()
    if isinstance(space, list):
        if space and str(space[0]) == "/ICCBased":
            return {1: 1, 3: 3}.get(int(space[1].get_object().get("/N", 0)), 0)
        space = space[0] if space else ""
    return 1 if str(space) in _GRAY_SPACES else 3 if str(space) in _RGB_SPACES else 0


def _palette(space: Any, bits: int) -> bytes | None:
    """Paleta RGB przestrzeni /Indexed; None, gdy przestrzeń bazowa nie jest szarością ani RGB."""
    channels = _channels(space[1])
    lookup = space[3].get_object()
    lookup = lookup.get_data() if hasattr(lookup, "get_data") else bytes(getattr(lookup, "original_bytes", lookup))
    if channels == 1:
        lookup = bytes(value for gray in lookup for value in (gray, gray, gray))
    elif channels != 3:
        return None
    return lookup[: 3 * min(len(lookup) // 3, 1 << bits)]


def _png(picture: Any, width: int, height: int, samples: bytes) -> Any:
    """PNG z surowych próbek obrazu PDF: szarość, RGB albo paleta; inne przestrzenie barw pomijamy."""
    mask = bool(picture.get("/ImageMask"))
    bits = 1 if mask else int(picture.get("/BitsPerComponent", 8))
    space = None if mask else picture.get("/ColorSpace")
    space = space.get_object() if space is not None else None
    palette = None
    if isinstance(space, list) and space and str(space[0]) in ("/Indexed", "/I"):
        palette = _palette(space, bits)
        color, channels = _PNG_PALETTE, 1 if palette and bits <= 8 else 0
    else:
        channels = 1 if space is None else _channels(space)
        color = _PNG_GRAY if channels == 1 else _PNG_RGB
    if not channels or bits not in ((8, 16) if channels == 3 else (1, 2, 4, 8, 16)):
        return _UNSUPPORTED
    row = (width * channels * bits + 7) // 8
    if len(samples) < row * height:
        return _UNSUPPORTED
    decode = picture.get("/Decode")
    if color == _PNG_GRAY and decode is not None and [float(value) for value in decode.get_object()] == [1.0, 0.0]:
        samples = samples.translate(_INVERTED)
    raster = b"".join(b"\x00" + samples[start : start + row] for start in range(0, row * height, row))
    chunks = [(b"IHDR", struct.pack(">IIBBBBB", width, height, bits, color, 0, 0, 0))]
    if palette is not None:
        chunks.append((b"PLTE", palette))
    chunks += [(b"IDAT", zlib.compress(raster, 1)), (b"IEND", b"")]
    return _PNG_SIGNATURE + b"".join(
        struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body)) for kind, body in chunks
    )


def _key(text: str) -> str:
    return "".join(_WORD_CHARACTER.findall(text)).casefold()
