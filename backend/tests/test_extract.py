import subprocess
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock
from zipfile import ZipFile

import pytest
from pypdf import PdfWriter
from samples import JPG, PDF, PNG

import app.extract as extract_module
from app.config import Settings
from app.errors import AppError, ExtractionError
from app.extract import extract
from app.files import validate_upload
from app.models import SourceFormat

MATERIALS = Path(__file__).resolve().parents[2] / "materialy"
WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
UNREADABLE = "Nie udało się odczytać treści pliku."
# Helvetica nie ma polskich liter w WinAnsiEncoding, więc dostają własne kody przez /Differences.
PDF_GLYPHS = {
    "ą": "aogonek",
    "ć": "cacute",
    "ę": "eogonek",
    "ł": "lslash",
    "ń": "nacute",
    "ś": "sacute",
    "ź": "zacute",
    "ż": "zdotaccent",
    "Ą": "Aogonek",
    "Ć": "Cacute",
    "Ę": "Eogonek",
    "Ł": "Lslash",
    "Ń": "Nacute",
    "Ś": "Sacute",
    "Ź": "Zacute",
    "Ż": "Zdotaccent",
}
PDF_CODES = {char: 128 + index for index, char in enumerate(PDF_GLYPHS)}


def docx(body: str, *, entry: str = "word/document.xml", trailing: str = "") -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        xml = f'<w:document xmlns:w="{WORD_NS}"><w:body>{body}</w:body></w:document>'
        archive.writestr(entry, xml + trailing)
    return buffer.getvalue()


def pdf(*pages: str, to_unicode: dict[str, int] | None = None) -> bytes:
    """Buduje PDF z jedną stroną na argument. Pusty tekst daje stronę bez warstwy tekstowej.

    `to_unicode` podmienia znaczenie liter: litera z tekstu strony trafia do odczytu jako podany kod.
    """
    differences = " ".join(f"/{glyph}" for glyph in PDF_GLYPHS.values())
    page_ids = [4 + 2 * index for index in range(len(pages))]
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    cmap_reference = f" /ToUnicode {4 + 2 * len(pages)} 0 R" if to_unicode else ""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode(),
        (
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding << /Type /Encoding "
            f"/BaseEncoding /WinAnsiEncoding /Differences [128 {differences}] >>{cmap_reference} >>"
        ).encode(),
    ]
    for page_id, text in zip(page_ids, pages, strict=True):
        lines = b" T* ".join(b"(" + _pdf_string(line) + b") Tj" for line in text.splitlines())
        stream = b"BT /F1 12 Tf 14 TL 72 770 Td " + lines + b" ET" if text else b""
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {page_id + 1} 0 R >>"
            ).encode()
        )
        objects.append(b"<< /Length %d >>\nstream\n%b\nendstream" % (len(stream), stream))
    if to_unicode:
        mapping = " ".join(f"<{ord(char):02X}> <{code:04X}>" for char, code in to_unicode.items())
        cmap = (
            "/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CMapType 2 def "
            "1 begincodespacerange <00> <FF> endcodespacerange "
            f"{len(to_unicode)} beginbfchar {mapping} endbfchar endcmap end end"
        ).encode()
        objects.append(b"<< /Length %d >>\nstream\n%b\nendstream" % (len(cmap), cmap))

    body = b"%PDF-1.4\n"
    offsets = []
    for number, content in enumerate(objects, start=1):
        offsets.append(len(body))
        body += b"%d 0 obj\n%b\nendobj\n" % (number, content)
    xref = b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    xref += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    trailer = b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, len(body))
    return body + xref + trailer


def _pdf_string(line: str) -> bytes:
    codes = bytes(PDF_CODES[char] if char in PDF_CODES else char.encode("cp1252")[0] for char in line)
    return codes.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def encrypted_pdf(data: bytes, *, user_password: str) -> bytes:
    writer = PdfWriter(clone_from=BytesIO(data))
    # RC4 jest w samym pypdf. AES wymagałby dodatkowej biblioteki kryptograficznej.
    writer.encrypt(user_password=user_password, owner_password="wlasciciel", algorithm="RC4-128")
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@pytest.fixture
def ocr_runner(monkeypatch: pytest.MonkeyPatch) -> Mock:
    runner = Mock(side_effect=AssertionError("OCR nie może być wołany dla PDF z warstwą tekstową"))
    monkeypatch.setattr(subprocess, "run", runner)
    return runner


def test_extract_pdf_reads_text_layer_in_page_order_without_ocr(ocr_runner: Mock) -> None:
    data = pdf(
        "Wniosek o wydanie zaświadczenia\nImię i nazwisko (wnioskodawca)",
        "Zażółć gęślą jaźń\nZAŻÓŁĆ GĘŚLĄ JAŹŃ",
        "Załączniki",
    )

    document = extract(data, validate_upload("wniosek.PDF", data, max_bytes=len(data)))

    assert document.source_format is SourceFormat.PDF
    assert document.text == (
        "Wniosek o wydanie zaświadczenia\nImię i nazwisko (wnioskodawca)"
        "\fZażółć gęślą jaźń\nZAŻÓŁĆ GĘŚLĄ JAŹŃ"
        "\fZałączniki"
    )
    assert document.ocr_used is False
    assert document.images == []
    assert document.warnings == []
    ocr_runner.assert_not_called()


def test_extract_pdf_keeps_place_of_pages_without_text(ocr_runner: Mock) -> None:
    document = extract(pdf("Wniosek", "", "Uzasadnienie", ""), "pdf")

    assert document.text == "Wniosek\f\fUzasadnienie\f"
    assert document.warnings == ["Strony PDF bez warstwy tekstowej: 2, 4."]
    assert document.ocr_used is False
    ocr_runner.assert_not_called()


def test_extract_pdf_replaces_characters_that_are_not_text() -> None:
    # Uszkodzony font potrafi oddać NUL, znak końca strony albo połówkę pary zastępczej UTF-16.
    data = pdf("WniosekAoBwydanieCdecyzji", "Podpis", to_unicode={"A": 0x0000, "B": 0x000C, "C": 0xD800})

    document = extract(data, "pdf")

    assert document.text == "Wniosek o wydanie decyzji\fPodpis"
    assert document.text.encode("utf-8").decode("utf-8") == document.text


def test_extract_pdf_reads_file_protected_only_against_editing() -> None:
    data = encrypted_pdf(pdf("Wniosek", "Załączniki"), user_password="")

    assert extract(data, "pdf").text == "Wniosek\fZałączniki"


VALID_PDF = pdf("Wniosek o wydanie decyzji", "Załączniki")


@pytest.mark.parametrize(
    "data",
    [
        PDF,
        b"%PDF-1.7\n" + b"\x00\xff losowe bajty " * 64,
        VALID_PDF[: len(VALID_PDF) // 3],
        VALID_PDF.replace(b"/Type /Pages /Kids", b"/Type /Pages /Kidz"),
        VALID_PDF.replace(b" >>\nstream", b" /Filter /Nieznany >>\nstream", 1),
        pdf(),
        pdf("", ""),
        encrypted_pdf(VALID_PDF, user_password="haslo"),
    ],
    ids=[
        "no-pages-stub",
        "garbage",
        "truncated",
        "broken-page-tree",
        "unsupported-filter",
        "zero-pages",
        "no-text",
        "password",
    ],
)
def test_unreadable_pdf_uses_contract_error(data: bytes, ocr_runner: Mock) -> None:
    with pytest.raises(ExtractionError) as exc_info:
        extract(data, "pdf")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == UNREADABLE
    ocr_runner.assert_not_called()


def test_extract_docx_preserves_text_order_and_page_break() -> None:
    data = docx(
        """
        <w:p><w:r><w:t>Wniosek</w:t><w:tab/><w:t>o wydanie decyzji</w:t></w:r></w:p>
        <w:tbl>
          <w:tr>
            <w:tc><w:p><w:r><w:t>Numer sprawy</w:t></w:r></w:p></w:tc>
            <w:tc><w:p><w:r><w:t>Kwota</w:t></w:r></w:p></w:tc>
          </w:tr>
          <w:tr>
            <w:tc><w:p/><w:p><w:r><w:t>R/1</w:t></w:r></w:p></w:tc>
            <w:tc><w:p><w:r><w:t>100 zł</w:t></w:r></w:p></w:tc>
          </w:tr>
        </w:tbl>
        <w:p><w:r><w:br w:type="page"/><w:t>Uzasadnienie</w:t><w:br/><w:t>Dalsze informacje</w:t></w:r></w:p>
        """
    )

    document = extract(data, "docx")

    assert document.source_format is SourceFormat.DOCX
    assert document.text == "Wniosek\to wydanie decyzji\nNumer sprawy | Kwota\nR/1 | 100 zł\fUzasadnienie\nDalsze informacje"
    assert document.ocr_used is False
    assert document.images == []
    assert document.warnings == []


def test_extract_docx_preserves_text_in_block_content_controls() -> None:
    data = docx(
        """
        <w:p><w:r><w:t>Wniosek</w:t></w:r></w:p>
        <w:sdt><w:sdtPr><w:alias w:val="Opis techniczny"/></w:sdtPr><w:sdtContent>
          <w:p><w:r><w:t>Numer sprawy</w:t></w:r></w:p>
          <w:sdt><w:sdtContent><w:p><w:r><w:t>Kwota</w:t></w:r></w:p></w:sdtContent></w:sdt>
        </w:sdtContent></w:sdt>
        <w:p><w:r><w:t>Załączniki</w:t></w:r></w:p>
        """
    )

    assert extract(data, "docx").text == "Wniosek\nNumer sprawy\nKwota\nZałączniki"


def test_extract_docx_preserves_table_rows_and_cells_in_content_controls() -> None:
    data = docx(
        """
        <w:tbl>
          <w:tr>
            <w:tc><w:p><w:r><w:t>Numer sprawy</w:t></w:r></w:p></w:tc>
            <w:sdt><w:sdtContent>
              <w:tc><w:p><w:r><w:t>Kwota</w:t></w:r></w:p></w:tc>
            </w:sdtContent></w:sdt>
          </w:tr>
          <w:sdt><w:sdtContent><w:tr>
            <w:tc><w:p><w:r><w:t>R/1</w:t></w:r></w:p></w:tc>
            <w:tc><w:p><w:r><w:t>100 zł</w:t></w:r></w:p></w:tc>
          </w:tr></w:sdtContent></w:sdt>
        </w:tbl>
        """
    )

    assert extract(data, "docx").text == "Numer sprawy | Kwota\nR/1 | 100 zł"


@pytest.mark.parametrize(
    ("folder", "suffix", "keyword", "expected_format"),
    [
        (1, ".docx", "numer", SourceFormat.DOCX),
        (5, ".docx", "nadpłat", SourceFormat.DOCX),
        (5, ".doc", "nadpłat", SourceFormat.DOCX),
        (1, ".pdf", "numer", SourceFormat.PDF),
        (5, ".pdf", "nadpłat", SourceFormat.PDF),
    ],
    ids=["control-docx", "working-docx", "working-docx-with-doc-extension", "control-pdf", "working-pdf"],
)
def test_extracts_coi_document(
    folder: int, suffix: str, keyword: str, expected_format: SourceFormat, ocr_runner: Mock
) -> None:
    candidates = sorted(
        path
        for directory in MATERIALS.glob(f"{folder}. *")
        for path in directory.iterdir()
        if path.suffix.lower() == suffix and "wizualizacja" not in path.name.lower()
    )
    if not candidates:
        pytest.skip(f"brak próbki {suffix} z folderu {folder} w {MATERIALS}")
    path = candidates[0]
    data = path.read_bytes()
    source_format = validate_upload(path.name, data, 10 * 1024 * 1024)
    document = extract(data, source_format)

    assert document.source_format is expected_format
    assert "wniosek" in document.text.casefold()
    assert keyword in document.text.casefold()
    assert document.ocr_used is False
    assert document.warnings == []
    ocr_runner.assert_not_called()


@pytest.mark.parametrize(
    "data",
    [
        b"document outside ZIP",
        docx("", entry="word/styles.xml"),
        docx("<w:p>"),
        docx("<w:p><w:r><w:t> </w:t></w:r></w:p>"),
    ],
    ids=["bad-zip", "missing-document-xml", "invalid-document-xml", "no-text"],
)
def test_unreadable_docx_uses_contract_error(data: bytes) -> None:
    with pytest.raises(ExtractionError) as exc_info:
        extract(data, "docx")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Nie udało się odczytać treści pliku."


def test_rejects_docx_when_uncompressed_xml_exceeds_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    data = docx("<w:p><w:r><w:t>Wniosek</w:t></w:r></w:p>", trailing="  ")
    with ZipFile(BytesIO(data)) as archive:
        xml_size = archive.getinfo("word/document.xml").file_size
    monkeypatch.setattr(extract_module, "_MAX_DOCUMENT_XML_BYTES", xml_size - 1)

    with pytest.raises(ExtractionError, match="Nie udało się odczytać treści pliku"):
        extract(data, "docx")


@pytest.mark.parametrize(
    ("filename", "data", "expected_format"),
    [
        ("skan.JPG", JPG, SourceFormat.JPG),
        ("skan.jpeg", JPG, SourceFormat.JPG),
        ("skan.JPE", JPG, SourceFormat.JPG),
        ("skan.png", PNG, SourceFormat.PNG),
    ],
    ids=["jpg", "jpeg", "jpe", "png"],
)
def test_extract_image_runs_local_ocr(
    monkeypatch: pytest.MonkeyPatch, filename: str, data: bytes, expected_format: SourceFormat
) -> None:
    command = ["tesseract", "stdin", "stdout", "-l", "pol+eng"]
    runner = Mock(return_value=subprocess.CompletedProcess(command, 0, " Wniosek\nZałączniki\n\x0c".encode()))
    monkeypatch.setattr(subprocess, "run", runner)
    monkeypatch.setattr(extract_module, "get_settings", lambda: Settings(ocr_lang="pol+eng"))

    document = extract(data, validate_upload(filename, data, max_bytes=1024))

    runner.assert_called_once_with(
        command,
        input=data,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=30,
    )
    assert document.source_format is expected_format
    assert document.text == "Wniosek\nZałączniki"
    assert document.ocr_used is True
    assert document.images == []


@pytest.mark.parametrize(
    "outcome",
    [
        subprocess.CalledProcessError(1, "tesseract"),
        subprocess.TimeoutExpired("tesseract", timeout=30),
        b" \n\x0c",
        b"\xff",
    ],
    ids=["engine-error", "timeout", "empty-text", "bad-encoding"],
)
def test_unreadable_image_uses_contract_error(monkeypatch: pytest.MonkeyPatch, outcome: bytes | Exception) -> None:
    if isinstance(outcome, Exception):
        runner = Mock(side_effect=outcome)
    else:
        runner = Mock(return_value=subprocess.CompletedProcess("tesseract", 0, outcome))
    monkeypatch.setattr(subprocess, "run", runner)

    with pytest.raises(ExtractionError) as exc_info:
        extract(PNG, "png")

    runner.assert_called_once()
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Nie udało się odczytać treści pliku."


def test_missing_tesseract_uses_server_error(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    runner = Mock(side_effect=FileNotFoundError(2, "No such file or directory", "tesseract"))
    monkeypatch.setattr(subprocess, "run", runner)

    with pytest.raises(AppError) as exc_info:
        extract(PNG, "png")

    runner.assert_called_once()
    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Coś poszło nie tak. Spróbuj ponownie."
    assert "Tesseract" in caplog.text
