"""Budowanie plików testowych dla czytników K2: obrazy, binarny DOC (OLE2) i PDF ze skanami.

Pliki powstają w pamięci, z samych struktur formatu, bez materiałów COI i bez bibliotek zapisu.
"""

import struct
import zlib
from collections.abc import Sequence
from dataclasses import dataclass

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_SECTOR = 512
_FREE, _END, _FAT = 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD
# Strumień krótszy niż 4096 bajtów trafiałby do ministrumienia; dopełniamy, żeby go nie budować.
_MIN_STREAM = 4096
_TEXT_AT = 1024
_FIB_PAIRS = 93
CLX, PLC_SPA_MOM, PLC_TXBX_TXT = 33, 40, 56


def png(width: int, height: int, *, gray: int = 255) -> bytes:
    """Poprawny PNG w skali szarości o jednolitym kolorze."""
    raster = (b"\x00" + bytes([gray]) * width) * height
    return png_file(width, height, 8, 0, zlib.compress(raster, 1))


def png_file(width: int, height: int, bits: int, color: int, compressed: bytes) -> bytes:
    chunks = [(b"IHDR", struct.pack(">IIBBBBB", width, height, bits, color, 0, 0, 0)), (b"IDAT", compressed), (b"IEND", b"")]
    return PNG_SIGNATURE + b"".join(
        struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body)) for kind, body in chunks
    )


def png_pixels(data: bytes) -> tuple[tuple[int, int, int, int], bytes, bytes]:
    """(szerokość, wysokość, bity, typ koloru), surowe wiersze z bajtem filtra i paleta z pliku PNG."""
    assert data.startswith(PNG_SIGNATURE)
    position, header, raster, palette = len(PNG_SIGNATURE), None, b"", b""
    while position < len(data):
        (length,) = struct.unpack_from(">I", data, position)
        kind, body = data[position + 4 : position + 8], data[position + 8 : position + 8 + length]
        assert struct.unpack_from(">I", data, position + 8 + length)[0] == zlib.crc32(kind + body)
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)[:4]
        elif kind == b"IDAT":
            raster += body
        elif kind == b"PLTE":
            palette = body
        position += 12 + length
    assert header is not None
    return header, zlib.decompress(raster), palette


def jpeg(width: int, height: int, *, frame: int = 0xC0, prefix: bytes = b"") -> bytes:
    """Nagłówek JPEG z wymiarami w znaczniku ramki. Wystarcza do odczytu wymiarów, nie do dekodowania."""
    application = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    table = b"\xff\xc4" + struct.pack(">H", 4) + b"\x00\x00"
    start_of_frame = bytes([0xFF, frame]) + struct.pack(">HBHHB", 11, 8, height, width, 1) + b"\x01\x11\x00"
    return b"\xff\xd8" + application + table + prefix + start_of_frame + b"\xff\xd9"


def compound_file(streams: dict[str, bytes]) -> bytes:
    """Kontener OLE2 (wersja 3, sektory 512 bajtów) ze strumieniami w katalogu głównym."""
    contents = {name: content.ljust(max(_MIN_STREAM, -(-len(content) // _SECTOR) * _SECTOR), b"\x00") for name, content in streams.items()}
    data_sectors = sum(len(content) // _SECTOR for content in contents.values())
    directory_sectors = -(-(len(contents) + 1) // 4)
    fat_sectors = 1
    while fat_sectors * (_SECTOR // 4) < fat_sectors + directory_sectors + data_sectors:
        fat_sectors += 1
    fat = [_FAT] * fat_sectors
    directory_start = len(fat)
    fat += [*range(directory_start + 1, directory_start + directory_sectors), _END]
    entries = [_directory_entry("Root Entry", 5, child=1 if contents else _FREE, start=_END, size=0)]
    for index, (name, content) in enumerate(contents.items(), start=1):
        start, count = len(fat), len(content) // _SECTOR
        fat += [*range(start + 1, start + count), _END]
        sibling = index + 1 if index < len(contents) else _FREE
        entries.append(_directory_entry(name, 2, right=sibling, start=start, size=len(content)))
    entries += [b"\x00" * 128] * (directory_sectors * 4 - len(entries))
    fat += [_FREE] * (fat_sectors * (_SECTOR // 4) - len(fat))
    header = struct.pack(
        "<8s16xHHHHH6xIIIIIIIII",
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",
        0x003E,
        3,
        0xFFFE,
        9,
        6,
        0,
        fat_sectors,
        directory_start,
        0,
        _MIN_STREAM,
        _END,
        0,
        _END,
        0,
    )
    header += struct.pack("<109I", *range(fat_sectors), *[_FREE] * (109 - fat_sectors))
    return header + struct.pack(f"<{len(fat)}I", *fat) + b"".join(entries) + b"".join(contents.values())


def _directory_entry(name: str, kind: int, *, right: int = _FREE, child: int = _FREE, start: int, size: int) -> bytes:
    encoded = (name + "\x00").encode("utf-16-le")
    return struct.pack("<64sHBBIII16xI8x8xIQ", encoded, len(encoded), kind, 1, _FREE, right, child, 0, start, size)


@dataclass(frozen=True)
class TextBox:
    """Pole tekstowe DOC: tekst, pozycja znaku kotwicy w historii głównej (None bez kotwicy) i położenie."""

    text: str
    anchor: int | None = None
    top: int = 0
    left: int = 0


def word_document(
    main: str,
    *,
    footnotes: str = "",
    headers: str = "",
    endnotes: str = "",
    boxes: Sequence[TextBox] = (),
    compressed: bool = False,
    ident: int = 0xA5EC,
    version: int = 0x00C1,
    flags: int = 0x0200,
    lengths: Sequence[int] | None = None,
    parts: dict[int, tuple[int, int]] | None = None,
    table: bytes | None = None,
    streams: dict[str, bytes] | None = None,
) -> bytes:
    """Binarny dokument Word 97–2003 z podanymi historiami tekstu.

    `lengths`, `parts`, `table` i `streams` podmieniają wyliczone struktury: służą do budowania
    plików uszkodzonych.
    """
    box_story = "".join(f"{box.text}\r" for box in boxes) + ("\r" if boxes else "")
    stories = [main, footnotes, headers, "", "", endnotes, box_story, ""]
    text = "".join(stories)
    encoded = text.encode("cp1252") if compressed else text.encode("utf-16-le")
    location = (_TEXT_AT * 2) | 0x40000000 if compressed else _TEXT_AT

    pieces = struct.pack("<II", 0, len(text)) + struct.pack("<HIH", 0, location, 0)
    table_parts = {CLX: b"\x02" + struct.pack("<I", len(pieces)) + pieces}
    if boxes:
        bounds, position = [0], 0
        for box in boxes:
            position += len(box.text) + 1
            bounds.append(position)
        bounds.append(position + 1)
        owners = [*range(1, len(boxes) + 1), 0]
        table_parts[PLC_TXBX_TXT] = struct.pack(f"<{len(bounds)}I", *bounds) + b"".join(
            struct.pack("<14xI4x", owner) for owner in owners
        )
        anchored = sorted((box.anchor, index) for index, box in enumerate(boxes, start=1) if box.anchor is not None)
        positions = [anchor for anchor, _ in anchored] + [len(main)]
        table_parts[PLC_SPA_MOM] = struct.pack(f"<{len(positions)}I", *positions) + b"".join(
            struct.pack("<IiiiiHI", index, boxes[index - 1].left, boxes[index - 1].top, 0, 0, 0, 1) for _, index in anchored
        )
    built_table, pairs = b"", [0] * (2 * _FIB_PAIRS)
    for index, content in table_parts.items():
        pairs[2 * index], pairs[2 * index + 1] = len(built_table), len(content)
        built_table += content
    for index, (start, size) in (parts or {}).items():
        pairs[2 * index], pairs[2 * index + 1] = start, size

    story_lengths = list(lengths) if lengths is not None else [len(story) for story in stories]
    fib = struct.pack("<HH6xH20x", ident, version, flags)
    fib += struct.pack("<H28x", 14)
    fib += struct.pack("<H3i8i11i", 22, 0, 0, 0, *story_lengths, *[0] * 11)
    fib += struct.pack(f"<H{len(pairs)}I", _FIB_PAIRS, *pairs)
    word = fib.ljust(_TEXT_AT, b"\x00") + encoded
    table_name = "1Table" if flags & 0x0200 else "0Table"
    result = {"WordDocument": word, table_name: built_table if table is None else table}
    result.update(streams or {})
    return compound_file({name: content for name, content in result.items() if content is not None})


@dataclass(frozen=True)
class PdfImage:
    """Obraz na stronie PDF. `place` to macierz `cm`: domyślnie cała strona A4."""

    data: bytes
    width: int
    height: int
    filter: str | None = "/DCTDecode"
    colorspace: str | None = "/DeviceGray"
    bits: int = 8
    place: tuple[float, ...] = (595, 0, 0, 842, 0, 0)
    extra: str = ""
    drawn: bool = True


def scanned_pdf(
    *pages: tuple[str, Sequence[PdfImage]],
    through_form: bool = False,
    form_uses: int = 1,
    form_redraws: int = 0,
    before: bytes = b"",
) -> bytes:
    """PDF, w którym strona to (tekst ASCII warstwy tekstowej, obrazy). `through_form` rysuje obrazy przez Form XObject.

    Strona rysuje ten formularz `form_uses` razy, a `form_redraws` dopisuje do niego tyle wywołań samego
    siebie (cykl). `before` to operatory rysowania przed obrazami.
    """
    objects: list[bytes] = [b"", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    page_ids = []
    for text, pictures in pages:
        names = []
        for picture in pictures:
            entries = f"/Type /XObject /Subtype /Image /Width {picture.width} /Height {picture.height} /BitsPerComponent {picture.bits}"
            if picture.colorspace:
                entries += f" /ColorSpace {picture.colorspace}"
            if picture.filter:
                entries += f" /Filter {picture.filter}"
            objects.append(_stream(f"{entries} {picture.extra}", picture.data))
            names.append(len(objects))
        draws = before + b"".join(
            f"q {' '.join(f'{value:g}' for value in picture.place)} cm /Im{number} Do Q ".encode()
            for picture, number in zip(pictures, names, strict=True)
            if picture.drawn
        )
        images = [f"/Im{number} {number} 0 R" for number in names]
        resources = "/XObject << " + " ".join(images) + " >>"
        if through_form:
            form = len(objects) + 1
            own = "/XObject << " + " ".join([*images, f"/Fm1 {form} 0 R"]) + " >>"
            draws += b"/Fm1 Do " * form_redraws
            objects.append(_stream(f"/Type /XObject /Subtype /Form /BBox [0 0 595 842] /Resources << {own} >>", draws))
            resources, draws = f"/XObject << /Fm1 {form} 0 R >>", b"/Fm1 Do " * form_uses
        if text:
            draws += b"BT /F1 12 Tf 72 770 Td (" + text.encode("ascii") + b") Tj ET"
        objects.append(_stream("", draws))
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                f"/Resources << /Font << /F1 3 0 R >> {resources} >> /Contents {len(objects)} 0 R >>"
            ).encode()
        )
        page_ids.append(len(objects))
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode()

    body, offsets = b"%PDF-1.4\n", []
    for number, content in enumerate(objects, start=1):
        offsets.append(len(body))
        body += b"%d 0 obj\n%b\nendobj\n" % (number, content)
    table = b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    table += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    return body + table + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, len(body))


def _stream(entries: str, data: bytes) -> bytes:
    return b"<< %b /Length %d >>\nstream\n%b\nendstream" % (entries.encode(), len(data), data)
