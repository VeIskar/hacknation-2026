"""Małe pliki-próbki z poprawną sygnaturą dla 8 formatów (bez prawdziwych danych)."""

import io
import zipfile


def _zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


PDF = b"%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 32
DOC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 504
DOCX = _zip({"[Content_Types].xml": b"<Types/>", "word/document.xml": b"<w:document/>"})
XLSX = _zip({"[Content_Types].xml": b"<Types/>", "xl/workbook.xml": b"<workbook/>"})
ODS = _zip(
    {
        "mimetype": b"application/vnd.oasis.opendocument.spreadsheet",
        "content.xml": b"<office:document-content/>",
    }
)


def _broken_ods() -> bytes:
    """ODS, którego skompresowany wpis mimetype ma uszkodzone dane (zlib.error przy odczycie)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", b"application/vnd.oasis.opendocument.spreadsheet" * 4)
    raw = bytearray(buffer.getvalue())
    start = 30 + len("mimetype")  # dane zaraz za nagłówkiem lokalnym wpisu
    for i in range(start, start + 10):
        raw[i] ^= 0xFF
    return bytes(raw)


BROKEN_ODS = _broken_ods()
ODT = _zip({"mimetype": b"application/vnd.oasis.opendocument.text", "content.xml": b"<x/>"})
PLAIN_ZIP = _zip({"readme.txt": b"to nie jest dokument"})

# nazwa pliku -> (zawartość, oczekiwane rozszerzenie z validate_upload)
VALID = {
    "wniosek.pdf": (PDF, "pdf"),
    "wniosek.doc": (DOC, "doc"),
    "wniosek.docx": (DOCX, "docx"),
    "wniosek.ods": (ODS, "ods"),
    "wniosek.xlsx": (XLSX, "xlsx"),
    "wniosek.jpg": (JPG, "jpg"),
    "wniosek.jpeg": (JPG, "jpg"),
    "wniosek.png": (PNG, "png"),
}
