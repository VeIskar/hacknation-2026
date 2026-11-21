import subprocess
import tracemalloc
from collections.abc import Callable
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
SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
STRICT_SHEET_NS = "http://purl.oclc.org/ooxml/spreadsheetml/main"
STRICT_OFFICE_REL_NS = "http://purl.oclc.org/ooxml/officeDocument/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
ODF_NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "draw": "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0",
    "xlink": "http://www.w3.org/1999/xlink",
}
ODS_OPEN = (
    "<office:document-content "
    + " ".join(f'xmlns:{prefix}="{uri}"' for prefix, uri in ODF_NS.items())
    + "><office:body><office:spreadsheet>"
)
ODS_CLOSE = "</office:spreadsheet></office:body></office:document-content>"
UNREADABLE = "Nie udało się odczytać treści pliku."
# Szczyt odczytu w test_sheet_memory_does_not_grow_with_rows_or_cells: zmierzone 2,8 MB, z czego
# 2,6 MB to sam XML, i 1,2 MB. Trzymanie wszystkich wierszy albo całego wiersza dawało 8,8 MB i więcej.
MEMORY_LIMIT_BYTES = 5 * 1024 * 1024
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


def zip_entries(entries: dict[str, str | None]) -> bytes:
    """Archiwum z podanych wpisów; wpis z wartością None jest pomijany."""
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            if content is not None:
                archive.writestr(name, content)
    return buffer.getvalue()


def rewrite_entry(data: bytes, entry: str, change: Callable[[str], str]) -> bytes:
    """Kopia archiwum z jednym wpisem zmienionym przez `change`."""
    with ZipFile(BytesIO(data)) as archive:
        entries: dict[str, str | None] = {name: archive.read(name).decode() for name in archive.namelist()}
    entries[entry] = change(entries[entry] or "")
    return zip_entries(entries)


def xlsx(
    *sheets: str,
    shared: tuple[str, ...] = (),
    ns: str = SHEET_NS,
    rel_ns: str = OFFICE_REL_NS,
    targets: tuple[str, ...] | None = None,
    extra: dict[str, str | None] | None = None,
) -> bytes:
    """XLSX z arkuszem na argument (treść `sheetData`); argument n leży w `xl/worksheets/sheet{n}.xml`.

    `shared` to treść kolejnych `<si>`. `targets` podmienia cele relacji arkuszy w kolejności
    skoroszytu. `extra` dopisuje albo nadpisuje wpisy archiwum (None usuwa wpis).
    """
    numbers = range(1, len(sheets) + 1)
    targets = targets or tuple(f"worksheets/sheet{number}.xml" for number in numbers)
    sheet_list = "".join(f'<sheet name="Arkusz{n}" sheetId="{n}" r:id="rId{n}"/>' for n in numbers)
    relationships = "".join(
        f'<Relationship Id="rId{n}" Type="{rel_ns}/worksheet" Target="{target}"/>'
        for n, target in enumerate(targets, start=1)
    )
    entries: dict[str, str | None] = {"[Content_Types].xml": "<Types/>"}
    if shared:
        relationships += f'<Relationship Id="rIdS" Type="{rel_ns}/sharedStrings" Target="sharedStrings.xml"/>'
        items = "".join(f"<si>{item}</si>" for item in shared)
        entries["xl/sharedStrings.xml"] = f'<sst xmlns="{ns}">{items}</sst>'
    entries["xl/workbook.xml"] = f'<workbook xmlns="{ns}" xmlns:r="{rel_ns}"><sheets>{sheet_list}</sheets></workbook>'
    entries["xl/_rels/workbook.xml.rels"] = f'<Relationships xmlns="{PACKAGE_REL_NS}">{relationships}</Relationships>'
    for number, sheet_data in zip(numbers, sheets, strict=True):
        entries[f"xl/worksheets/sheet{number}.xml"] = f'<worksheet xmlns="{ns}"><sheetData>{sheet_data}</sheetData></worksheet>'
    entries.update(extra or {})
    return zip_entries(entries)


def ods(*tables: str, content: str | None = None) -> bytes:
    """ODS z arkuszem na argument (treść `table:table`). `content` podmienia cały content.xml."""
    if content is None:
        body = "".join(f'<table:table table:name="Arkusz{n}">{table}</table:table>' for n, table in enumerate(tables, 1))
        content = f"{ODS_OPEN}{body}{ODS_CLOSE}"
    return zip_entries({"mimetype": "application/vnd.oasis.opendocument.spreadsheet", "content.xml": content})


def ods_row(*cells: str, repeated: int = 1) -> str:
    """Wiersz ODS; komórka podana jako tekst ma jeden akapit, pusty tekst to pusta komórka."""
    attribute = f' table:number-rows-repeated="{repeated}"' if repeated > 1 else ""
    body = "".join(
        f"<table:table-cell><text:p>{cell}</text:p></table:table-cell>" if cell else "<table:table-cell/>"
        for cell in cells
    )
    return f"<table:table-row{attribute}>{body}</table:table-row>"


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
        (1, ".xlsx", "numer", SourceFormat.XLSX),
        (1, ".ods", "numer", SourceFormat.ODS),
        (5, ".ods", "nadpłat", SourceFormat.ODS),
    ],
    ids=[
        "control-docx",
        "working-docx",
        "working-docx-with-doc-extension",
        "control-pdf",
        "working-pdf",
        "control-xlsx",
        "control-ods",
        "working-ods",
    ],
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


XLSX_CELL = '<row r="1"><c r="A1" t="inlineStr"><is><t>Wniosek</t></is></c></row>'


def xlsx_shared_cell(index: str) -> str:
    return f'<row r="1"><c r="A1" t="s"><v>{index}</v></c></row>'


def xlsx_bad_shared_cell(index: str) -> str:
    """Poprawna komórka obok złej: pominięcie złej dałoby tekst zamiast błędu."""
    return f'<row r="1"><c r="A1" t="inlineStr"><is><t>Wniosek</t></is></c><c r="B1" t="s"><v>{index}</v></c></row>'


def test_extract_xlsx_reads_worksheets_in_workbook_order_as_pages(ocr_runner: Mock) -> None:
    title = (
        '<row r="1"><c r="A1" t="inlineStr"><is><t>Wniosek o zwrot</t></is></c><c r="B1" s="1"/>'
        '<c r="C1" t="s"><v>0</v></c></row>'
        '<row r="2"><c r="A2" s="1"/></row>'
        '<row r="3"><c r="A3" t="inlineStr"><is><r><t xml:space="preserve">Zażółć </t></r>'
        "<r><rPr><b/></rPr><t>gęślą jaźń</t></r></is></c></row>"
    )
    values = (
        '<row r="1"><c r="A1" t="s"><v>1</v></c><c r="B1"><v>17.5</v></c><c r="C1" t="b"><v>1</v></c>'
        '<c r="D1" t="b"><v>0</v></c><c r="E1" t="str"><f>A1</f><v>Wynik formuły</v></c>'
        '<c r="F1" t="e"><v>#N/A</v></c><c r="G1" t="d"><v>2026-11-21</v></c><c r="H1" t="inlineStr"/></row>'
    )
    empty = '<row r="1"><c r="A1" s="1"/></row>'
    # Skoroszyt wymienia arkusze w innej kolejności niż nazwy wpisów w archiwum.
    data = xlsx(
        title,
        empty,
        values,
        shared=("<t>opłaty skarbowej</t>", "<r><t>Załącz</t></r><r><t>niki</t></r>"),
        targets=("worksheets/sheet3.xml", "worksheets/sheet2.xml", "worksheets/sheet1.xml"),
    )

    document = extract(data, validate_upload("wniosek.XLSX", data, max_bytes=len(data)))

    assert document.source_format is SourceFormat.XLSX
    assert document.text == (
        "Załączniki | 17.5 | PRAWDA | FAŁSZ | Wynik formuły | #N/A | 2026-11-21"
        "\fWniosek o zwrot | opłaty skarbowej\nZażółć gęślą jaźń"
    )
    assert document.ocr_used is False
    assert document.warnings == []
    ocr_runner.assert_not_called()


def test_extract_xlsx_decodes_escapes_and_drops_control_characters() -> None:
    # Excel zapisuje znaki niedozwolone w XML jako _xHHHH_, a _x005F_ to samo podkreślenie.
    # Znak \f z komórki nie może udawać końca strony. Fonetyka (rPh) nie jest tekstem komórki.
    data = xlsx(
        '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="inlineStr"><is><t>Kod_x005F_x000D_</t></is></c></row>'
        '<row r="2"><c r="A2" t="inlineStr"><is><t>Strona_x000C_1_x0001_z 2</t></is></c></row>',
        shared=('<t xml:space="preserve">  Nazwa organu,_x000D_\nw którym zapłacono  </t><rPh sb="0" eb="5"><t>FONETYKA</t></rPh>',),
    )

    assert extract(data, "xlsx").text == "Nazwa organu,\nw którym zapłacono | Kod_x000D_\nStrona 1 z 2"


@pytest.mark.parametrize(
    ("ns", "rel_ns", "target"),
    [
        (SHEET_NS, OFFICE_REL_NS, "/xl/worksheets/sheet1.xml"),
        (SHEET_NS, OFFICE_REL_NS, "../xl/worksheets/sheet1.xml"),
        (STRICT_SHEET_NS, STRICT_OFFICE_REL_NS, "worksheets/sheet1.xml"),
        # Nazwy części OPC to URI bez rozróżniania wielkości liter (ECMA-376 cz. 2, 6.2.2).
        (SHEET_NS, OFFICE_REL_NS, "Worksheets/SHEET1.xml"),
        (SHEET_NS, OFFICE_REL_NS, "worksheets/sheet%31.xml"),
    ],
    ids=["absolute-target", "parent-relative-target", "strict-ooxml", "other-letter-case", "percent-encoded"],
)
def test_extract_xlsx_resolves_sheet_parts(ns: str, rel_ns: str, target: str) -> None:
    data = xlsx(xlsx_shared_cell("0"), shared=("<t>Wniosek</t>",), ns=ns, rel_ns=rel_ns, targets=(target,))

    assert extract(data, "xlsx").text == "Wniosek"


def test_extract_xlsx_skips_sheets_without_cells() -> None:
    # Arkusz wykresu ma relację innego typu; jego wpisu celowo brak w archiwum.
    workbook = (
        f'<workbook xmlns="{SHEET_NS}" xmlns:r="{OFFICE_REL_NS}"><sheets>'
        '<sheet name="Wykres" sheetId="2" r:id="rId2"/><sheet name="Arkusz1" sheetId="1" r:id="rId1"/>'
        "</sheets></workbook>"
    )
    relationships = (
        f'<Relationships xmlns="{PACKAGE_REL_NS}">'
        f'<Relationship Id="rId1" Type="{OFFICE_REL_NS}/worksheet" Target="worksheets/sheet1.xml"/>'
        f'<Relationship Id="rId2" Type="{OFFICE_REL_NS}/chartsheet" Target="chartsheets/sheet1.xml"/>'
        "</Relationships>"
    )
    data = xlsx(XLSX_CELL, extra={"xl/workbook.xml": workbook, "xl/_rels/workbook.xml.rels": relationships})

    assert extract(data, "xlsx").text == "Wniosek"


@pytest.mark.parametrize(
    "data",
    [
        b"workbook outside ZIP",
        xlsx(XLSX_CELL, extra={"xl/workbook.xml": None}),
        xlsx(XLSX_CELL, extra={"xl/workbook.xml": "<workbook"}),
        xlsx(XLSX_CELL, extra={"xl/_rels/workbook.xml.rels": None}),
        # Przy złej części obok jest poprawna: pominięcie złej dałoby tekst zamiast błędu.
        xlsx(XLSX_CELL, XLSX_CELL, extra={"xl/worksheets/sheet2.xml": "<worksheet"}),
        xlsx(XLSX_CELL, ns="urn:inny-dokument"),
        xlsx(XLSX_CELL, XLSX_CELL, targets=("worksheets/sheet1.xml", "worksheets/brak.xml")),
        xlsx(
            XLSX_CELL,
            extra={
                "xl/workbook.xml": f'<workbook xmlns="{SHEET_NS}" xmlns:r="{OFFICE_REL_NS}"><sheets>'
                '<sheet name="A" sheetId="1" r:id="rId1"/><sheet name="B" sheetId="2" r:id="rId9"/>'
                "</sheets></workbook>"
            },
        ),
        xlsx(xlsx_bad_shared_cell("1"), shared=("<t>Wniosek</t>",)),
        xlsx(xlsx_bad_shared_cell("-1"), shared=("<t>Wniosek</t>",)),
        xlsx(xlsx_bad_shared_cell("pierwszy"), shared=("<t>Wniosek</t>",)),
        xlsx('<row r="1"><c r="A1" s="1"/><c r="B1" t="inlineStr"><is><t> </t></is></c></row>'),
        # Zagnieżdżenie bez końca trzymałoby w pamięci wszystkie otwarte elementy.
        xlsx(XLSX_CELL + "<x>" * 5000 + "</x>" * 5000),
        # Jedna komórka z dziesiątkami tysięcy elementów to nie formularz, a koszt pamięci.
        xlsx(XLSX_CELL + '<row r="2"><c t="inlineStr"><is>' + "<r><t>a</t></r>" * 20_000 + "</is></c></row>"),
    ],
    ids=[
        "bad-zip",
        "missing-workbook",
        "invalid-workbook-xml",
        "missing-relationships",
        "invalid-sheet-xml",
        "unknown-namespace",
        "missing-sheet-entry",
        "sheet-without-relationship",
        "shared-index-out-of-range",
        "negative-shared-index",
        "non-numeric-shared-index",
        "no-text",
        "deep-nesting",
        "too-many-elements-in-cell",
    ],
)
def test_unreadable_xlsx_uses_contract_error(data: bytes) -> None:
    with pytest.raises(ExtractionError) as exc_info:
        extract(data, "xlsx")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == UNREADABLE


@pytest.mark.parametrize(
    "declaration",
    ['<?xml version="1.0" encoding="shift_jis"?>', '<?xml version="1.0" encoding="brak-takiego"?>'],
    ids=["multi-byte-encoding", "unknown-encoding"],
)
@pytest.mark.parametrize(
    ("data", "ext", "entry"),
    [
        (ods(ods_row("Wniosek")), "ods", "content.xml"),
        (xlsx(XLSX_CELL), "xlsx", "xl/workbook.xml"),
        (xlsx(XLSX_CELL), "xlsx", "xl/worksheets/sheet1.xml"),
        (xlsx(xlsx_shared_cell("0"), shared=("<t>Wniosek</t>",)), "xlsx", "xl/sharedStrings.xml"),
    ],
    ids=["ods-content", "xlsx-workbook", "xlsx-sheet", "xlsx-shared-strings"],
)
def test_unsupported_xml_encoding_is_unreadable(data: bytes, ext: str, entry: str, declaration: str) -> None:
    # Parser XML zgłasza takie kodowanie jako ValueError albo LookupError, nie ParseError.
    broken = rewrite_entry(data, entry, lambda xml: declaration + xml)

    with pytest.raises(ExtractionError, match=UNREADABLE):
        extract(broken, ext)


@pytest.mark.parametrize(
    ("data", "ext"),
    [
        (ods("<table:table-row><table:table-cell/></table:table-row>" * 50_000 + ods_row("Tak")), "ods"),
        (xlsx('<row r="1">' + "<c/>" * 100_000 + '<c t="inlineStr"><is><t>Tak</t></is></c></row>'), "xlsx"),
    ],
    ids=["many-rows", "one-wide-row"],
)
def test_sheet_memory_does_not_grow_with_rows_or_cells(data: bytes, ext: str) -> None:
    # Bez zwalniania przetworzonych elementów szczyt pamięci rośnie z liczbą wierszy i komórek.
    tracemalloc.start()
    try:
        text = extract(data, ext).text
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert text == "Tak"
    assert peak < MEMORY_LIMIT_BYTES


def test_xlsx_unpacked_xml_limit_is_shared_by_all_parts(monkeypatch: pytest.MonkeyPatch) -> None:
    data = xlsx(XLSX_CELL, XLSX_CELL)
    with ZipFile(BytesIO(data)) as archive:
        unpacked = sum(info.file_size for info in archive.infolist() if info.filename.startswith("xl/"))

    monkeypatch.setattr("app.extract.sheets.MAX_XML_BYTES", unpacked)
    assert extract(data, "xlsx").text == "Wniosek\fWniosek"

    # Każda część osobno mieści się w limicie, razem już nie.
    monkeypatch.setattr("app.extract.sheets.MAX_XML_BYTES", unpacked - 1)
    with pytest.raises(ExtractionError, match=UNREADABLE):
        extract(data, "xlsx")


@pytest.mark.parametrize("entry", ["xl/workbook.xml", "xl/_rels/workbook.xml.rels"])
def test_xlsx_index_parts_have_own_limit(monkeypatch: pytest.MonkeyPatch, entry: str) -> None:
    # Spis arkuszy jest mały; cały drzewiasty odczyt dużego spisu kosztowałby dużo pamięci.
    # Badany wpis jest największy, więc limit poniżej jego rozmiaru zatrzymuje tylko jego.
    with ZipFile(BytesIO(xlsx(XLSX_CELL))) as archive:
        entries: dict[str, str | None] = {name: archive.read(name).decode() for name in archive.namelist()}
    entries[entry] = f"{entries[entry]}{' ' * 1000}"
    data = zip_entries(entries)
    size = len(entries[entry].encode())

    monkeypatch.setattr("app.extract.sheets._MAX_INDEX_XML_BYTES", size)
    assert extract(data, "xlsx").text == "Wniosek"

    monkeypatch.setattr("app.extract.sheets._MAX_INDEX_XML_BYTES", size - 1)
    with pytest.raises(ExtractionError, match=UNREADABLE):
        extract(data, "xlsx")


def test_xlsx_text_over_limit_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    data = xlsx(XLSX_CELL, XLSX_CELL)
    monkeypatch.setattr("app.extract.sheets.MAX_TEXT_CHARS", 2 * len("Wniosek") - 1)

    with pytest.raises(ExtractionError, match=UNREADABLE):
        extract(data, "xlsx")


def test_extract_ods_reads_tables_as_pages_with_cell_text(ocr_runner: Mock) -> None:
    form = (
        '<table:table-column table:number-columns-repeated="3"/>'
        "<table:table-header-rows><table:table-row>"
        '<table:table-cell office:value-type="string"><text:p>Wniosek o <text:span>zwrot</text:span></text:p>'
        '<text:p>opłaty<text:s text:c="3"/>skarbowej<text:s/>(PLN)</text:p></table:table-cell>'
        "<table:table-cell/>"
        "<table:covered-table-cell><text:p>pod scaleniem</text:p></table:covered-table-cell>"
        "</table:table-row></table:table-header-rows>"
        '<table:table-row table:number-rows-repeated="5">'
        '<table:table-cell table:number-columns-repeated="16384"/></table:table-row>'
        "<table:table-row-group><table:table-row><table:table-cell>"
        "<office:annotation><text:p>komentarz</text:p></office:annotation>"
        "<text:p>Kwota<text:tab/>zł<text:line-break/>"
        'netto <text:a xlink:href="https://example.org">link</text:a></text:p></table:table-cell>'
        '<table:table-cell office:value-type="float" office:value="17"><text:p>17,00</text:p></table:table-cell>'
        "</table:table-row></table:table-row-group>"
    )
    empty = (
        '<table:table-row table:number-rows-repeated="1048576">'
        '<table:table-cell table:number-columns-repeated="16384"/></table:table-row>'
    )
    data = ods(form, empty, ods_row("Załączniki"))

    document = extract(data, validate_upload("wniosek.ODS", data, max_bytes=len(data)))

    assert document.source_format is SourceFormat.ODS
    assert document.text == (
        "Wniosek o zwrot\nopłaty   skarbowej (PLN) | pod scaleniem\nKwota\tzł\nnetto link | 17,00\fZałączniki"
    )
    assert document.ocr_used is False
    assert document.warnings == []
    ocr_runner.assert_not_called()


def test_extract_ods_expands_repeated_cells_and_rows_with_text() -> None:
    row = (
        '<table:table-row table:number-rows-repeated="2">'
        '<table:table-cell table:number-columns-repeated="3"><text:p>Tak</text:p></table:table-cell>'
        '<table:table-cell table:number-columns-repeated="16381"/></table:table-row>'
        # Zła liczba powtórzeń znaczy jedno wystąpienie.
        '<table:table-row table:number-rows-repeated="-3">'
        '<table:table-cell table:number-columns-repeated="dużo"><text:p>Nie</text:p></table:table-cell>'
        '<table:table-cell table:number-columns-repeated="0"><text:p>Nie</text:p></table:table-cell></table:table-row>'
    )

    assert extract(ods(row), "ods").text == "Tak | Tak | Tak\nTak | Tak | Tak\nNie | Nie"


def test_extract_ods_paragraph_keeps_text_box_and_skips_inline_comment() -> None:
    paragraph = (
        "Kwota<office:annotation><text:p>uwaga</text:p></office:annotation> netto"
        "<draw:frame><draw:text-box><text:p>W ramce</text:p></draw:text-box></draw:frame>"
    )

    assert extract(ods(ods_row(paragraph)), "ods").text == "Kwota netto\nW ramce"


def test_extract_ods_keeps_nested_table_inside_its_cell() -> None:
    nested = f'<table:table table:name="W">{ods_row("Wewnątrz")}</table:table>'
    row = f"<table:table-row><table:table-cell><text:p>Zewnątrz</text:p>{nested}</table:table-cell>"
    row += "<table:table-cell><text:p>Obok</text:p></table:table-cell></table:table-row>"

    assert extract(ods(row), "ods").text == "Zewnątrz\nWewnątrz | Obok"


def test_extract_ods_cell_without_paragraph_uses_stored_value() -> None:
    row = (
        "<table:table-row>"
        '<table:table-cell office:value-type="float" office:value="17.5"/>'
        '<table:table-cell office:value-type="string" office:string-value="Wniosek"/>'
        '<table:table-cell office:value-type="date" office:date-value="2026-11-21"/>'
        '<table:table-cell office:value-type="time" office:time-value="PT10H30M00S"/>'
        '<table:table-cell office:value-type="boolean" office:boolean-value="true"/>'
        "</table:table-row>"
    )

    assert extract(ods(row), "ods").text == "17.5 | Wniosek | 2026-11-21 | PT10H30M00S | PRAWDA"


def test_ods_space_runs_are_capped() -> None:
    text = extract(ods(ods_row('Imię<text:s text:c="100000000"/>Nazwisko')), "ods").text

    assert text.startswith("Imię ")
    assert text.endswith(" Nazwisko")
    assert len(text) < 1000


@pytest.mark.parametrize(
    "data",
    [
        b"spreadsheet outside ZIP",
        zip_entries({"mimetype": "application/vnd.oasis.opendocument.spreadsheet"}),
        # Pełny arkusz z tekstem, potem urwany XML: częściowy odczyt byłby błędem.
        ods(content=f'{ODS_OPEN}<table:table table:name="A">{ods_row("Wniosek")}</table:table><table:table'),
        ods(ods_row("", " ")),
        # Wiersz z tekstem powtórzony milion razy: odrzucony przed rozwinięciem powtórzeń.
        ods(ods_row("Tak", repeated=1_048_576)),
        # Zagnieżdżenie głębsze niż limit rekurencji Pythona: 400, nie 500.
        ods(ods_row("<text:span>" * 5000 + "Tak" + "</text:span>" * 5000)),
        ods(
            "<table:table-row><table:table-cell>"
            + "<text:list>" * 5000
            + "<text:p>Tak</text:p>"
            + "</text:list>" * 5000
            + "</table:table-cell></table:table-row>"
        ),
        ods(content=f"{ODS_OPEN}<table:table>{ods_row('Tak')}</table:table>{'<x>' * 5000}{'</x>' * 5000}{ODS_CLOSE}"),
        ods(ods_row("Tak" + "<text:s/>" * 20_000)),
    ],
    ids=[
        "bad-zip",
        "missing-content-xml",
        "invalid-content-xml",
        "no-text",
        "repeated-text-bomb",
        "deep-nesting-in-paragraph",
        "deep-nesting-around-paragraph",
        "deep-nesting-outside-table",
        "too-many-elements-in-cell",
    ],
)
def test_unreadable_ods_uses_contract_error(data: bytes) -> None:
    with pytest.raises(ExtractionError) as exc_info:
        extract(data, "ods")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == UNREADABLE


def test_ods_unpacked_xml_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    data = ods(ods_row("Wniosek"))
    with ZipFile(BytesIO(data)) as archive:
        size = archive.getinfo("content.xml").file_size

    monkeypatch.setattr("app.extract.sheets.MAX_XML_BYTES", size)
    assert extract(data, "ods").text == "Wniosek"

    monkeypatch.setattr("app.extract.sheets.MAX_XML_BYTES", size - 1)
    with pytest.raises(ExtractionError, match=UNREADABLE):
        extract(data, "ods")
