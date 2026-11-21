import logging
import subprocess
from collections.abc import Iterator
from io import BytesIO
from lzma import LZMAError
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile
from zlib import error as ZlibError

from pypdf import PdfReader

from app.config import get_settings
from app.errors import AppError, ExtractionError
from app.extract.common import NOT_TEXT, UNREADABLE
from app.extract.sheets import ods_text, xlsx_text
from app.models import ExtractedDocument, SourceFormat

_WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_MAX_DOCUMENT_XML_BYTES = 16 * 1024 * 1024
_IMAGE_FORMATS = {SourceFormat.JPG, SourceFormat.PNG}
_OCR_TIMEOUT_SECONDS = 30
_SERVER_ERROR = "Coś poszło nie tak. Spróbuj ponownie."

_logger = logging.getLogger(__name__)


def extract(data: bytes, ext: str) -> ExtractedDocument:
    ocr_used = ext in _IMAGE_FORMATS
    warnings = []
    if ocr_used:
        text = _image_text(data)
    elif ext == SourceFormat.DOCX:
        text = _docx_text(data)
    elif ext == SourceFormat.XLSX:
        text = xlsx_text(data)
    elif ext == SourceFormat.ODS:
        text = ods_text(data)
    elif ext == SourceFormat.PDF:
        pages = _pdf_pages(data)
        text = "\f".join(pages)
        without_text = [str(number) for number, page in enumerate(pages, start=1) if not page]
        if without_text:
            warnings.append(f"Strony PDF bez warstwy tekstowej: {', '.join(without_text)}.")
    else:
        raise ExtractionError(detail=UNREADABLE)
    if not text.strip():
        raise ExtractionError(detail=UNREADABLE)
    return ExtractedDocument(source_format=SourceFormat(ext), text=text, ocr_used=ocr_used, warnings=warnings)


def _pdf_pages(data: bytes) -> list[str]:
    """Tekst każdej strony w kolejności dokumentu. Strona bez warstwy tekstowej to pusty napis."""
    try:
        return [NOT_TEXT.sub(" ", page.extract_text()).strip() for page in PdfReader(BytesIO(data)).pages]
    # Na uszkodzonym pliku pypdf zgłasza też wyjątki spoza PyPdfError (NotImplementedError,
    # TypeError, AttributeError, AssertionError). Każdy znaczy to samo: treści nie da się odczytać.
    except Exception as exc:
        raise ExtractionError(detail=UNREADABLE) from exc


def _image_text(data: bytes) -> str:
    language = get_settings().ocr_lang
    try:
        result = subprocess.run(
            ["tesseract", "stdin", "stdout", "-l", language],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=_OCR_TIMEOUT_SECONDS,
        )
        return result.stdout.decode("utf-8").strip()
    except FileNotFoundError as exc:
        _logger.error("Brak programu Tesseract w środowisku API.")
        raise AppError(detail=_SERVER_ERROR) from exc
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, UnicodeDecodeError) as exc:
        raise ExtractionError(detail=UNREADABLE) from exc


def _docx_text(data: bytes) -> str:
    try:
        with ZipFile(BytesIO(data)) as archive, archive.open("word/document.xml") as entry:
            # Limit dotyczy rozpakowanego XML, niezależnie od limitu całego pliku.
            xml = entry.read(_MAX_DOCUMENT_XML_BYTES + 1)
        if len(xml) > _MAX_DOCUMENT_XML_BYTES:
            raise ExtractionError(detail=UNREADABLE)
        root = ElementTree.fromstring(xml)
    except (
        BadZipFile,
        EOFError,
        KeyError,
        LZMAError,
        OSError,
        RuntimeError,
        ValueError,
        ZlibError,
        ElementTree.ParseError,
    ) as exc:
        raise ExtractionError(detail=UNREADABLE) from exc

    body = root.find(f"{_WORD}body")
    if root.tag != f"{_WORD}document" or body is None:
        raise ExtractionError(detail=UNREADABLE)
    text = "\n".join(_block_lines(body))
    return "\f".join(page.strip() for page in text.split("\f"))


def _block_lines(container: ElementTree.Element) -> Iterator[str]:
    for block in _content_children(container):
        if block.tag == f"{_WORD}p":
            line = _paragraph_text(block)
            if line:
                yield line
        elif block.tag == f"{_WORD}tbl":
            rows = (row for row in _content_children(block) if row.tag == f"{_WORD}tr")
            for row in rows:
                cells = [
                    " ".join(_block_lines(cell))
                    for cell in _content_children(row)
                    if cell.tag == f"{_WORD}tc"
                ]
                if any(cells):
                    yield " | ".join(cells)


def _content_children(container: ElementTree.Element) -> Iterator[ElementTree.Element]:
    for child in container:
        if child.tag == f"{_WORD}sdt":
            content = child.find(f"{_WORD}sdtContent")
            if content is not None:
                yield from _content_children(content)
        else:
            yield child


def _paragraph_text(paragraph: ElementTree.Element) -> str:
    parts = []
    for node in paragraph.iter():
        if node.tag == f"{_WORD}t":
            parts.append(node.text or "")
        elif node.tag == f"{_WORD}tab":
            parts.append("\t")
        elif node.tag == f"{_WORD}br":
            parts.append("\f" if node.get(f"{_WORD}type") == "page" else "\n")
        elif node.tag == f"{_WORD}cr":
            parts.append("\n")
    return "".join(parts).strip(" \t\n")
