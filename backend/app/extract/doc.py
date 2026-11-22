"""Tekst binarnego dokumentu Word 97–2003 (.doc).

Kontener OLE2 czyta `olefile`, struktury Word ten moduł (specyfikacja MS-DOC). Zakres jest celowo
wąski: tablica kawałków tekstu (Clx), długości historii z FIB i kotwice pól tekstowych. Formatowania
znaków i akapitów nie czytamy, więc koniec wiersza tabeli rozpoznajemy po podwójnym znaku komórki.
"""

import re
import struct
from bisect import bisect_left
from dataclasses import dataclass
from io import BytesIO

import olefile

from app.extract.common import (
    MAX_TEXT_CHARS,
    Box,
    clean_text,
    lines_by_position,
    unreadable,
)

_WORD_IDENT = 0xA5EC
# Word 97. Starsze wersje (Word 6 i 95) mają inny układ FIB i tekst 8-bitowy w stronie kodowej.
_MIN_NFIB = 0x00C1
_ENCRYPTED = 0x0100
_TABLE1 = 0x0200
# Pozycje par (fc, lcb) w FibRgFcLcb97.
_CLX, _PLC_SPA_MOM, _PLC_TXBX_TXT = 33, 40, 56
_FSPA_BYTES, _FTXBXS_BYTES, _FTXBXS_LID = 26, 22, 14
_PCD_BYTES = 8
_FC_COMPRESSED = 0x40000000
# Historie tekstu w kolejności zapisu: główna, przypisy dolne, nagłówki i stopki, makra,
# komentarze, przypisy końcowe, pola tekstowe, pola tekstowe nagłówków.
_MAIN, _FOOTNOTES, _HEADERS, _ENDNOTES, _TEXTBOXES, _HEADER_TEXTBOXES = 0, 1, 2, 5, 6, 7
_STORIES = 8
# Położenie pól jest w twipach (1/20 punktu). Wiersz 9 pt ma ok. 185 twipów, więc pola przesunięte
# o mniej niż 90 leżą w tym samym wierszu (folder 8: różnice do 56 twipów w jednym wierszu).
_ROW_TOLERANCE_TWIPS = 90
_FIELD_BEGIN, _FIELD_SEPARATOR, _FIELD_END = "\x13", "\x14", "\x15"
_NOTE_MARK = "\x02"
_ANCHOR = "\x08"
_PARAGRAPH_END = re.compile(r"[\r\x0c]")
_ROW_END = re.compile("\x07{2,}")
_TRAILING_SPACE = re.compile(r"[ \t]+$", re.MULTILINE)
_BLANK_LINES = re.compile(r"\n{3,}")
# Znak akapitu i podziału wiersza, podział strony, łączniki oraz znaczniki obiektów bez tekstu.
_CHARACTERS = {
    0x0D: "\n",
    0x0B: "\n",
    0x0C: "\f",
    0x1E: "-",
    0x1F: None,
    0x01: None,
    0x03: None,
    0x04: None,
    0x05: None,
    0x06: None,
    0x08: None,
}
_ERRORS = (struct.error, IndexError, ValueError, OSError)


@dataclass(frozen=True)
class _Fib:
    table_name: str
    story_lengths: tuple[int, ...]
    parts: tuple[int, ...]

    def part(self, index: int) -> tuple[int, int]:
        """Położenie i długość struktury w strumieniu tabeli; brak w krótszym FIB to (0, 0)."""
        if 2 * index + 1 >= len(self.parts):
            return 0, 0
        return self.parts[2 * index], self.parts[2 * index + 1]


def doc_text(data: bytes) -> str:
    try:
        return _text(data)
    # olefile zgłasza uszkodzony kontener jako OSError, a krótkie struktury kończą się błędem struct.
    except _ERRORS as exc:
        raise unreadable() from exc


def _text(data: bytes) -> str:
    # Obiekt plikowy, nie bajty: krótkie bajty olefile uznałby za nazwę pliku na dysku.
    container = olefile.OleFileIO(BytesIO(data))
    try:
        word = _stream(container, "WordDocument")
        fib = _fib(word)
        table = _stream(container, fib.table_name)
    finally:
        container.close()

    characters = _characters(word, _pieces(table, *fib.part(_CLX)))
    stories = _stories(characters, fib.story_lengths)
    anchored, loose = _textboxes(table, fib, stories[_TEXTBOXES])
    main, unplaced = _with_textboxes(stories[_MAIN], anchored)
    extras = [
        *unplaced,
        *loose,
        _numbered(stories[_FOOTNOTES]),
        _numbered(stories[_ENDNOTES]),
        _unique_lines(stories[_HEADERS]),
        stories[_HEADER_TEXTBOXES],
    ]
    pages = [clean_text(page) for page in _plain(_numbered(main)).split("\f")]
    appended = "\n".join(filter(None, (clean_text(_plain(extra)) for extra in extras)))
    if appended:
        pages[-1] = f"{pages[-1]}\n{appended}".strip()
    return "\f".join(_BLANK_LINES.sub("\n\n", _TRAILING_SPACE.sub("", page)) for page in pages)


def _stream(container: olefile.OleFileIO, name: str) -> bytes:
    if not container.exists(name) or container.get_type(name) != olefile.STGTY_STREAM:
        raise unreadable()
    return container.openstream(name).read()


def _slice(data: bytes, start: int, length: int) -> bytes:
    """Fragment, który musi leżeć w całości w danych; wycinek Pythona po cichu by go skrócił."""
    if start < 0 or length < 0 or start + length > len(data):
        raise unreadable()
    return data[start : start + length]


def _fib(word: bytes) -> _Fib:
    ident, version = struct.unpack_from("<HH", word, 0)
    (flags,) = struct.unpack_from("<H", word, 10)
    if ident != _WORD_IDENT or version < _MIN_NFIB or flags & _ENCRYPTED:
        raise unreadable()
    (short_count,) = struct.unpack_from("<H", word, 32)
    longs_at = 34 + 2 * short_count
    (long_count,) = struct.unpack_from("<H", word, longs_at)
    # Długości historii to pola 3–10 tablicy FibRgLw97.
    story_lengths = struct.unpack_from(f"<{_STORIES}i", word, longs_at + 2 + 3 * 4)
    parts_at = longs_at + 2 + 4 * long_count
    (part_count,) = struct.unpack_from("<H", word, parts_at)
    parts = struct.unpack_from(f"<{2 * part_count}I", word, parts_at + 2)
    if long_count < 3 + _STORIES or min(story_lengths) < 0:
        raise unreadable()
    return _Fib("1Table" if flags & _TABLE1 else "0Table", story_lengths, parts)


def _pieces(table: bytes, start: int, length: int) -> list[tuple[int, int, int]]:
    """Kawałki tekstu z Clx: (liczba znaków, położenie w strumieniu WordDocument, bajty na znak)."""
    clx = _slice(table, start, length)
    position = 0
    while clx[position] == 0x01:  # Prc: właściwości formatowania, pomijane
        position += 3 + struct.unpack_from("<H", clx, position + 1)[0]
    if clx[position] != 0x02:
        raise unreadable()
    (size,) = struct.unpack_from("<I", clx, position + 1)
    plc = _slice(clx, position + 5, size)
    count, rest = divmod(size - 4, 4 + _PCD_BYTES)
    if count < 1 or rest:
        raise unreadable()
    bounds = struct.unpack_from(f"<{count + 1}I", plc, 0)
    pieces = []
    for index in range(count):
        chars = bounds[index + 1] - bounds[index]
        (raw,) = struct.unpack_from("<I", plc, 4 * (count + 1) + _PCD_BYTES * index + 2)
        if chars < 0:
            raise unreadable()
        if raw & _FC_COMPRESSED:
            pieces.append((chars, (raw & ~_FC_COMPRESSED) // 2, 1))
        else:
            pieces.append((chars, raw & ~_FC_COMPRESSED, 2))
    return pieces


def _characters(word: bytes, pieces: list[tuple[int, int, int]]) -> str:
    """Cały tekst dokumentu; indeks znaku to jego pozycja (CP) w strukturach Word."""
    if sum(chars for chars, _, _ in pieces) > 2 * MAX_TEXT_CHARS:
        raise unreadable()
    parts = []
    for chars, offset, width in pieces:
        raw = _slice(word, offset, chars * width)
        if width == 1:
            parts.append(raw.decode("cp1252", "replace"))
            continue
        text = raw.decode("utf-16-le", "surrogatepass")
        if len(text) != chars:
            # Para surogatów to dwie pozycje w Word, a dekoder skleja ją w jeden znak.
            text = "".join(map(chr, struct.unpack(f"<{chars}H", raw)))
        parts.append(text)
    return "".join(parts)


def _stories(characters: str, lengths: tuple[int, ...]) -> list[str]:
    if sum(lengths) > len(characters):
        raise unreadable()
    stories, start = [], 0
    for length in lengths:
        stories.append(characters[start : start + length])
        start += length
    return stories


def _textboxes(table: bytes, fib: _Fib, story: str) -> tuple[dict[int, list[Box]], list[str]]:
    """Pola tekstowe przy kotwicach z historii głównej oraz teksty pól, których kotwicy nie ma."""
    texts_at, texts_bytes = fib.part(_PLC_TXBX_TXT)
    shapes_at, shapes_bytes = fib.part(_PLC_SPA_MOM)
    if not story or texts_bytes < 4:
        return {}, [story] if story.strip() else []
    texts = _slice(table, texts_at, texts_bytes)
    box_count = (texts_bytes - 4) // (4 + _FTXBXS_BYTES)
    bounds = struct.unpack_from(f"<{box_count + 1}I", texts, 0)

    shapes = _slice(table, shapes_at, shapes_bytes) if shapes_bytes >= 4 else b""
    shape_count = max(len(shapes) - 4, 0) // (4 + _FSPA_BYTES)
    anchors = struct.unpack_from(f"<{shape_count + 1}I", shapes, 0) if shape_count else ()
    placed = {}
    for index in range(shape_count):
        shape_id, left, top = struct.unpack_from("<Iii", shapes, 4 * (shape_count + 1) + _FSPA_BYTES * index)
        placed[shape_id] = (anchors[index], top, left)

    anchored: dict[int, list[Box]] = {}
    loose = []
    for index in range(box_count):
        text = story[bounds[index] : bounds[index + 1]]
        lines = tuple(line.strip() for line in text.split("\r") if line.strip())
        if not lines:
            continue
        (shape_id,) = struct.unpack_from("<I", texts, 4 * (box_count + 1) + _FTXBXS_BYTES * index + _FTXBXS_LID)
        if shape_id in placed:
            anchor, top, left = placed[shape_id]
            anchored.setdefault(anchor, []).append(Box(top, left, lines))
        else:
            loose.append(text)
    return anchored, loose


def _with_textboxes(main: str, anchored: dict[int, list[Box]]) -> tuple[str, list[str]]:
    """Historia główna z tekstem pól dopisanym na końcu akapitu, w którym leży ich kotwica.

    Pola jednego akapitu mają wspólny punkt odniesienia, więc układamy je po położeniu.
    Drugi wynik to teksty pól, których kotwica nie wskazuje znaku obiektu w historii głównej.
    """
    positions = sorted(position for position in anchored if position < len(main) and main[position] == _ANCHOR)
    unplaced = ["\r".join(line for box in anchored[position] for line in box.lines) for position in sorted(anchored.keys() - set(positions))]
    if not positions:
        return main, unplaced
    parts = []
    start = 0
    while start < len(main):
        match = _PARAGRAPH_END.search(main, start)
        end = match.start() if match else len(main)
        boxes = [
            box
            for position in positions[bisect_left(positions, start) : bisect_left(positions, end)]
            for box in anchored[position]
        ]
        parts.append(main[start:end])
        if boxes:
            parts.append("\r" + "\r".join(lines_by_position(boxes, _ROW_TOLERANCE_TWIPS)))
        parts.append(match.group() if match else "")
        start = end + 1
    return "".join(parts), unplaced


def _numbered(story: str) -> str:
    """Znaczniki przypisów automatycznych jako kolejne liczby, jak na wydruku."""
    parts = story.split(_NOTE_MARK)
    return "".join(part if index == 0 else f"{index}{part}" for index, part in enumerate(parts))


def _unique_lines(story: str) -> str:
    """Nagłówki i stopki sekcji powtarzają ten sam tekst dla stron parzystych i nieparzystych."""
    return "\r".join(dict.fromkeys(line for line in story.split("\r") if line.strip()))


def _plain(story: str) -> str:
    text = _field_results(story)
    text = _ROW_END.sub("\n", text).replace("\x07", " | ").translate(_CHARACTERS)
    # Znaki spoza BMP czytaliśmy jako dwie połówki, żeby indeks zgadzał się z pozycją w Word.
    return text.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace")


def _field_results(text: str) -> str:
    """Tekst bez kodów pól: z „początek, kod, separator, wynik, koniec” zostaje wynik."""
    if _FIELD_BEGIN not in text:
        return text
    kept = []
    in_code: list[bool] = []
    codes = 0
    for char in text:
        if char == _FIELD_BEGIN:
            in_code.append(True)
            codes += 1
        elif char == _FIELD_SEPARATOR:
            if in_code and in_code[-1]:
                in_code[-1] = False
                codes -= 1
        elif char == _FIELD_END:
            if in_code:
                codes -= in_code.pop()
        elif not codes:
            kept.append(char)
    return "".join(kept)
