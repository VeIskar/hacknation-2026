"""Przyjęcie pliku: odczyt z żądania w pamięci i kontrola nazwy, rozmiaru i typu.

Plik nigdy nie trafia na dysk (Treść pkt 5): treść żądania czytamy strumieniowo do limitu,
a parser multipart dostaje bufor większy niż plik, więc nie tworzy pliku tymczasowego.
Komunikaty błędów: SPEC.md, rozdz. „API contract”.
"""

import io
import lzma
import struct
import zipfile
import zlib
from collections.abc import AsyncIterator

from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.requests import Request

from app.config import MB
from app.errors import UploadError

MAX_NAME_LENGTH = 250
FORBIDDEN_NAME_CHARS = frozenset(";:></\\|'*%$")
# Zapas na nagłówki multipart ponad sam plik; dokładny limit sprawdza validate_upload.
MULTIPART_OVERHEAD = 64 * 1024
ODS_MIMETYPE = b"application/vnd.oasis.opendocument.spreadsheet"
ALIASES = {"jpeg": "jpg", "jpe": "jpg"}  # .JPE jest w folderze 7 materiałów COI
SUPPORTED = frozenset({"pdf", "doc", "docx", "ods", "xlsx", "jpg", "png"})

MSG_NAME = "Nazwa pliku jest za długa albo ma niedozwolone znaki."
MSG_TYPE = "Ten typ pliku nie jest obsługiwany. Wybierz PDF, DOC, DOCX, ODS, XLSX, JPG albo PNG."
MSG_NO_FILE = "Wybierz plik formularza."


def too_large(max_bytes: int) -> UploadError:
    return UploadError(detail=f"Plik jest za duży. Limit to {max_bytes / MB:g} MB.", status_code=413)


# zipfile na uszkodzonych metadanych rzuca nie tylko BadZipFile. Plik od użytkownika, którego
# nie da się odczytać, to zawsze 415, nigdy 500, więc łapiemy wszystkie znane błędy odczytu.
# ValueError obejmuje też UnicodeDecodeError (nazwy wpisów), OSError obejmuje EOF i seek.
ZIP_ERRORS = (
    zipfile.BadZipFile,
    zipfile.LargeZipFile,
    ValueError,
    NotImplementedError,
    OSError,
    EOFError,
    RuntimeError,
    OverflowError,
    KeyError,
    IndexError,
    struct.error,
    zlib.error,
    lzma.LZMAError,
)


def _zip_names(data: bytes) -> tuple[zipfile.ZipFile, list[str]] | None:
    if not data.startswith(b"PK\x03\x04"):
        return None
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        return archive, archive.namelist()
    except ZIP_ERRORS:
        return None


def _is_ods(data: bytes) -> bool:
    """Wpis `mimetype` ma treść dokładnie równą typowi ODS (ODF 1.2, rozdz. 3.3), bez dodatków."""
    opened = _zip_names(data)
    if opened is None or "mimetype" not in opened[1]:
        return False
    try:
        with opened[0].open("mimetype") as entry:
            return entry.read(len(ODS_MIMETYPE) + 1) == ODS_MIMETYPE
    except ZIP_ERRORS:
        return False


def _has_zip_dir(data: bytes, prefix: str) -> bool:
    opened = _zip_names(data)
    return opened is not None and any(name.startswith(prefix) for name in opened[1])


def content_matches(ext: str, data: bytes) -> bool:
    """Czy sygnatura pliku pasuje do (znormalizowanego) rozszerzenia."""
    match ext:
        case "pdf":
            # Czytniki PDF akceptują śmieci przed nagłówkiem w pierwszym 1 KB.
            return b"%PDF-" in data[:1024]
        case "png":
            return data.startswith(b"\x89PNG\r\n\x1a\n")
        case "jpg":
            return data.startswith(b"\xff\xd8\xff")
        case "doc":
            return data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
        case "docx":
            return _has_zip_dir(data, "word/")
        case "xlsx":
            return _has_zip_dir(data, "xl/")
        case "ods":
            return _is_ods(data)
    return False


def validate_upload(filename: str, data: bytes, max_bytes: int) -> str:
    """Sprawdza plik i zwraca format do odczytu: rozszerzenie małymi literami (jpeg -> jpg).

    Wyjątek: .doc, który w środku jest DOCX (tak zapisane są pliki COI z folderów 5 i 7),
    przechodzi i zwraca "docx", żeby extract użył właściwego czytnika.
    Kolejność: nazwa (400), rozmiar (413), typ (415), zawartość zgodna z typem (415).
    """
    if (
        not filename
        or len(filename) > MAX_NAME_LENGTH
        or any(ch in FORBIDDEN_NAME_CHARS or ord(ch) < 32 for ch in filename)
    ):
        raise UploadError(detail=MSG_NAME, status_code=400)
    if len(data) > max_bytes:
        raise too_large(max_bytes)
    raw_ext = filename.rsplit(".", 1)[1].lower() if "." in filename else ""
    ext = ALIASES.get(raw_ext, raw_ext)
    if ext not in SUPPORTED:
        raise UploadError(detail=MSG_TYPE, status_code=415)
    if content_matches(ext, data):
        return ext
    if ext == "doc" and content_matches("docx", data):
        return "docx"
    raise UploadError(
        detail=f"Zawartość pliku nie pasuje do rozszerzenia .{raw_ext}.", status_code=415
    )


async def read_single_file(request: Request, max_bytes: int) -> tuple[str, bytes]:
    """Czyta jedno pole `file` z multipart/form-data, całość w pamięci.

    Przerywa odczyt z 413, gdy żądanie jest większe niż limit, zanim przyjdzie do końca.
    """
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type != "multipart/form-data":  # typ MIME bez względu na wielkość liter (RFC 2045)
        raise UploadError(detail=MSG_NO_FILE, status_code=400)
    limit = max_bytes + MULTIPART_OVERHEAD
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        raise too_large(max_bytes)

    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > limit:
            raise too_large(max_bytes)

    async def replay() -> AsyncIterator[bytes]:
        yield bytes(body)

    parser = MultiPartParser(request.headers, replay(), max_files=1, max_fields=0)
    # Bufor większy niż całe żądanie: SpooledTemporaryFile nie zapisze nic na dysk.
    parser.spool_max_size = len(body) + 1
    try:
        form = await parser.parse()
    except MultiPartException as exc:
        raise UploadError(detail=MSG_NO_FILE, status_code=400) from exc
    try:
        upload = form.get("file")
        if not isinstance(upload, UploadFile) or not upload.filename:
            raise UploadError(detail=MSG_NO_FILE, status_code=400)
        return upload.filename, await upload.read()
    finally:
        await form.close()
