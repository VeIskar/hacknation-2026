import shutil
import subprocess
import tracemalloc
import zlib
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock
from zipfile import ZIP_BZIP2, ZIP_DEFLATED, ZIP_LZMA, ZipFile

import pytest
from extract_builders import PdfImage, jpeg, png, png_pixels, scanned_pdf
from pypdf import PdfWriter
from samples import PDF

from app.errors import ExtractionError
from app.extract import docx as docx_reader
from app.extract import extract as extract_in_child_process
from app.extract import images, ocr
from app.extract import pdf as pdf_reader
from app.extract.readers import read_document
from app.files import validate_upload
from app.models import ExtractedDocument, SourceFormat

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
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
SHAPE_NS = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
GRAPHIC_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
VML_NS = "urn:schemas-microsoft-com:vml"
STRICT_WORD_NS = "http://purl.oclc.org/ooxml/wordprocessingml/main"
needs_ocr_engine = pytest.mark.skipif(
    shutil.which("tesseract") is None or not images.can_cut(), reason="brak programu Tesseract albo biblioteki Leptonica"
)
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


def extract(data: bytes, ext: str) -> ExtractedDocument:
    """Odczyt w procesie testu, bez piaskownicy: tylko tu działają atrapy OCR i podmienione limity."""
    reading = read_document(data, ext, language="pol")
    return ExtractedDocument(
        source_format=SourceFormat(ext), text=reading.text, ocr_used=reading.ocr_used, warnings=reading.warnings
    )


def document_xml(body: str, *, ns: str = WORD_NS) -> str:
    namespaces = f'xmlns:w="{ns}" xmlns:mc="{MC_NS}" xmlns:wp="{DRAWING_NS}" xmlns:wps="{SHAPE_NS}"'
    namespaces += f' xmlns:a="{GRAPHIC_NS}" xmlns:v="{VML_NS}" xmlns:r="{OFFICE_REL_NS}"'
    return f"<w:document {namespaces}><w:body>{body}</w:body></w:document>"


def docx(body: str, *, entry: str = "word/document.xml", trailing: str = "") -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(entry, document_xml(body) + trailing)
    return buffer.getvalue()


def docx_package(
    body: str,
    *,
    media: dict[str, bytes] | None = None,
    targets: dict[str, str] | None = None,
    parts: dict[str, str] | None = None,
    compression: int = ZIP_DEFLATED,
    ns: str = WORD_NS,
) -> bytes:
    """DOCX z obrazami i dodatkowymi częściami.

    `media` to nazwa pliku -> bajty; relacja rId{n} wskazuje n-ty obraz. `targets` dopisuje albo
    podmienia relacje (identyfikator -> cel), a cel zaczynający się od http jest zewnętrzny.
    """
    relationships = {f"rId{number}": f"media/{name}" for number, name in enumerate(media or {}, start=1)}
    relationships.update(targets or {})
    rows = "".join(
        f'<Relationship Id="{identifier}" Type="{OFFICE_REL_NS}/image" Target="{target}"'
        + (' TargetMode="External"/>' if target.startswith("http") else "/>")
        for identifier, target in relationships.items()
    )
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression) as archive:
        archive.writestr("word/document.xml", document_xml(body, ns=ns))
        archive.writestr("word/_rels/document.xml.rels", f'<Relationships xmlns="{PACKAGE_REL_NS}">{rows}</Relationships>')
        for name, content in (media or {}).items():
            archive.writestr(f"word/media/{name}", content)
        for name, content in (parts or {}).items():
            archive.writestr(name, content)
    return buffer.getvalue()


def paragraph(text: str) -> str:
    return f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"


def picture(relationship: str) -> str:
    """Akapit z obrazem wstawionym w tekście."""
    blip = f'<a:graphic><a:graphicData><a:blip r:embed="{relationship}"/></a:graphicData></a:graphic>'
    return f"<w:p><w:r><w:drawing><wp:inline>{blip}</wp:inline></w:drawing></w:r></w:p>"


def text_box(content: str, *, top: int | None = None, left: int = 0, fallback: str | None = None) -> str:
    """Pole tekstowe tak, jak zapisuje je Word: kształt w mc:Choice i jego kopia VML w mc:Fallback."""
    position = ""
    if top is not None:
        position = f"<wp:positionH><wp:posOffset>{left}</wp:posOffset></wp:positionH>"
        position += f"<wp:positionV><wp:posOffset>{top}</wp:posOffset></wp:positionV>"
    copy = content if fallback is None else fallback
    return (
        '<mc:AlternateContent><mc:Choice Requires="wps"><w:drawing><wp:anchor>'
        f"{position}<a:graphic><a:graphicData><wps:wsp><wps:txbx><w:txbxContent>{content}</w:txbxContent></wps:txbx>"
        "</wps:wsp></a:graphicData></a:graphic></wp:anchor></w:drawing></mc:Choice>"
        f"<mc:Fallback><w:pict><v:shape><v:textbox><w:txbxContent>{copy}</w:txbxContent></v:textbox></v:shape></w:pict>"
        "</mc:Fallback></mc:AlternateContent>"
    )


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
    monkeypatch.setattr(docx_reader, "MAX_DOCUMENT_XML_BYTES", xml_size)
    assert extract(data, "docx").text == "Wniosek"

    monkeypatch.setattr(docx_reader, "MAX_DOCUMENT_XML_BYTES", xml_size - 1)
    with pytest.raises(ExtractionError, match="Nie udało się odczytać treści pliku"):
        extract(data, "docx")


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


# K2-FINAL: pola tekstowe i obrazy w DOCX, limity ZIP i XML, OCR skanów w PDF.


def ocr_by_content(monkeypatch: pytest.MonkeyPatch, results: dict[bytes, str]) -> list[bytes]:
    """Atrapa Tesseracta: tekst zależy od bajtów obrazu. Zwraca listę obrazów, które dostała."""
    seen: list[bytes] = []

    def tesseract(command: list[str], **options: bytes) -> subprocess.CompletedProcess:
        seen.append(options["input"])
        return subprocess.CompletedProcess(command, 0, results[options["input"]].encode())

    monkeypatch.setattr(subprocess, "run", tesseract)
    return seen


def test_docx_text_box_is_read_once_and_as_separate_lines(ocr_runner: Mock) -> None:
    # Word zapisuje pole dwa razy (Choice i Fallback). Wcześniej wychodziło „Urząd MiastaUrząd Miasta”.
    box = text_box(paragraph("Urząd Miasta i Gminy") + paragraph("ul. Dworcowa 29"))
    data = docx(f"{paragraph('Imię i nazwisko')}<w:p><w:r><w:t>Adres</w:t>{box}</w:r></w:p>{paragraph('PESEL')}")

    assert extract(data, "docx").text == "Imię i nazwisko\nAdres\nUrząd Miasta i Gminy\nul. Dworcowa 29\nPESEL"


def test_docx_fallback_is_used_when_choice_has_no_content() -> None:
    box = text_box("<w:p/>", fallback=paragraph("Tylko w kopii"))

    assert extract(docx(f"<w:p><w:r>{box}</w:r></w:p>"), "docx").text == "Tylko w kopii"


def alternate(choice: str, fallback: str) -> str:
    return f'<mc:AlternateContent><mc:Choice Requires="w14">{choice}</mc:Choice><mc:Fallback>{fallback}</mc:Fallback></mc:AlternateContent>'


def test_docx_block_level_alternate_content_gives_one_branch() -> None:
    # Recenzja K2-FINAL, D1: gałęzie poza akapitem dawały tekst dwa razy, a w komórce tabeli wcale.
    body = (
        paragraph("Wniosek")
        + alternate(paragraph("Dane wnioskodawcy"), paragraph("Dane wnioskodawcy"))
        + f"<w:tbl><w:tr><w:tc>{alternate(paragraph('PESEL'), paragraph('PESEL (kopia)'))}</w:tc></w:tr></w:tbl>"
        + alternate("<w:p/>", paragraph("Tylko w kopii"))
    )

    assert extract(docx(body), "docx").text == "Wniosek\nDane wnioskodawcy\nPESEL\nTylko w kopii"


def test_docx_text_drops_control_characters() -> None:
    # Recenzja K2-FINAL, D4: XML 1.0 dopuszcza znaki C1 i powrót karetki zapisany jako &#13;.
    body = paragraph("Wniosek&#13;o zwrot") + paragraph("Kwota\u0085100\u009fzł")

    assert extract(docx(body), "docx").text == "Wniosek\no zwrot\nKwota 100 zł"


def test_docx_text_boxes_of_one_paragraph_follow_page_layout() -> None:
    # Dokument przerobiony z PDF (folder 8): fragmenty wiersza w osobnych polach, w pliku od dołu strony.
    boxes = (
        text_box(paragraph("Podpis"), top=9_000_000, left=500_000)
        + text_box(paragraph("zł"), top=3_040_000, left=4_000_000)
        + text_box(paragraph("Kwota"), top=3_000_000, left=500_000)
        + text_box(paragraph("WNIOSEK") + paragraph("O ZWROT"), top=1_000_000, left=500_000)
        + text_box(paragraph("100"), top=3_010_000, left=2_000_000)
    )

    assert extract(docx(f"<w:p><w:r>{boxes}</w:r></w:p>"), "docx").text == "WNIOSEK\nO ZWROT\nKwota 100 zł\nPodpis"


def test_docx_text_boxes_without_position_keep_file_order() -> None:
    boxes = text_box(paragraph("Drugie w układzie"), top=5_000_000) + text_box(paragraph("Bez położenia"))

    assert extract(docx(f"<w:p><w:r>{boxes}</w:r></w:p>"), "docx").text == "Drugie w układzie\nBez położenia"


def test_docx_reads_notes_headers_and_footers_after_body() -> None:
    def part(root: str, body: str) -> str:
        return f'<w:{root} xmlns:w="{WORD_NS}">{body}</w:{root}>'

    note = '<w:footnote w:id="{0}"><w:p><w:r><w:footnoteRef/></w:r><w:r><w:t>) {1}</w:t></w:r></w:p></w:footnote>'
    data = docx_package(
        '<w:p><w:r><w:t>Adres e-mail</w:t></w:r><w:r><w:footnoteReference w:id="2"/></w:r><w:r><w:t>)</w:t></w:r></w:p>'
        '<w:p><w:r><w:t>Podpis</w:t></w:r><w:r><w:footnoteReference w:id="3"/></w:r><w:r><w:t>)</w:t></w:r></w:p>',
        parts={
            "word/footnotes.xml": part(
                "footnotes",
                '<w:footnote w:type="separator" w:id="0"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
                + note.format(2, "Dane nieobowiązkowe.")
                + note.format(3, "Podpis własnoręczny."),
            ),
            "word/endnotes.xml": part("endnotes", f"<w:endnote>{paragraph('Przypis końcowy')}</w:endnote>"),
            "word/header1.xml": part("hdr", paragraph("Załącznik nr 2")),
            "word/header2.xml": part("hdr", paragraph("Załącznik nr 2")),
            "word/footer1.xml": part("ftr", paragraph("* niepotrzebne skreślić")),
            "word/styles.xml": part("styles", paragraph("Tego nie czytamy")),
        },
    )

    assert extract(data, "docx").text == (
        "Adres e-mail1)\nPodpis2)\n1) Dane nieobowiązkowe.\n2) Podpis własnoręczny.\nPrzypis końcowy\n"
        "Załącznik nr 2\n* niepotrzebne skreślić"
    )


def test_docx_strict_namespace_is_read() -> None:
    data = docx_package(paragraph("Wniosek") + f"<w:tbl><w:tr><w:tc>{paragraph('Kwota')}</w:tc></w:tr></w:tbl>", ns=STRICT_WORD_NS)

    assert extract(data, "docx").text == "Wniosek\nKwota"


def test_docx_picture_text_is_inserted_where_picture_stands(monkeypatch: pytest.MonkeyPatch) -> None:
    scan, logo, icon = png(600, 400), png(300, 300, gray=10), png(20, 20)
    seen = ocr_by_content(monkeypatch, {scan: "Wniosek\n7\nNumer rachunku: 12 3456\n— |\nPodpis wnioskodawcy\n", logo: "ab .\n"})
    body = paragraph("Wniosek") + picture("rId1") + paragraph("Podpis wnioskodawcy") + picture("rId2") + picture("rId3")
    data = docx_package(body, media={"skan.png": scan, "logo.png": logo, "ikona.png": icon, "luzem.png": png(500, 500)})

    document = extract(data, "docx")

    # Wiersze, które są już w tekście dokumentu, pojedynczy znak i szum z logo odpadają. Ikona nie idzie do OCR,
    # tak samo obraz, do którego dokument się nie odwołuje.
    assert document.text == "Wniosek\nNumer rachunku: 12 3456\nPodpis wnioskodawcy"
    assert sorted(seen) == sorted([scan, logo])
    assert document.ocr_used is True
    assert document.warnings == []


def test_docx_without_new_text_from_pictures_does_not_report_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    logo = png(300, 300)
    ocr_by_content(monkeypatch, {logo: "WNIOSEK\n"})

    document = extract(docx_package(paragraph("Wniosek") + picture("rId1"), media={"logo.png": logo}), "docx")

    assert document.text == "Wniosek"
    assert document.ocr_used is False


def test_docx_repeated_picture_is_read_once_and_its_text_stands_once(monkeypatch: pytest.MonkeyPatch) -> None:
    stamp = png(400, 200)
    seen = ocr_by_content(monkeypatch, {stamp: "Urząd Gminy Stawiguda\n"})
    vml = '<w:p><w:r><w:pict><v:shape><v:imagedata r:id="rId2"/></v:shape></w:pict></w:r></w:p>'
    body = picture("rId1") + paragraph("Strona 1") + picture("rId1") + vml + paragraph("Strona 2")
    data = docx_package(body, media={"pieczec.png": stamp}, targets={"rId2": "media/pieczec.png"})

    assert extract(data, "docx").text == "Urząd Gminy Stawiguda\nStrona 1\nStrona 2"
    assert seen == [stamp]


def test_docx_pictures_over_limit_are_skipped_with_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    pictures = {f"skan{number}.png": png(200, 100 + number) for number in range(1, 5)}
    seen = ocr_by_content(monkeypatch, {content: f"Załącznik numer {name}\n" for name, content in pictures.items()})
    monkeypatch.setattr(docx_reader, "MAX_PICTURES", 3)
    body = "".join(picture(f"rId{number}") for number in range(1, 5)) + paragraph("Koniec")

    document = extract(docx_package(body, media=pictures), "docx")

    assert document.text == "Załącznik numer skan1.png\nZałącznik numer skan2.png\nZałącznik numer skan3.png\nKoniec"
    assert len(seen) == 3
    assert document.warnings == [docx_reader._OVER_LIMIT]


def test_docx_pictures_have_a_pixel_budget_per_document(monkeypatch: pytest.MonkeyPatch) -> None:
    # Jak w PDF: 20 obrazów po 100 mln pikseli to minuty OCR, a odczyt ma limit czasu.
    pictures = {"skan1.png": png(200, 101), "skan2.png": png(200, 300), "skan3.png": png(200, 102), "skan4.png": png(200, 103)}
    seen = ocr_by_content(monkeypatch, {content: f"Załącznik numer {name}\n" for name, content in pictures.items()})
    monkeypatch.setattr(docx_reader, "MAX_DOCUMENT_PIXELS", 200 * 101 + 200 * 102)
    body = "".join(picture(f"rId{number}") for number in range(1, 5)) + paragraph("Koniec")

    document = extract(docx_package(body, media=pictures), "docx")

    # Drugi obraz nie mieści się w budżecie, trzeci jeszcze tak, a czwarty już nie: zmieściłby się
    # sam, ale nie po pierwszym i trzecim.
    assert document.text == "Załącznik numer skan1.png\nZałącznik numer skan3.png\nKoniec"
    assert len(seen) == 2
    assert document.warnings == [docx_reader._OVER_PIXELS]


def test_docx_ignores_pictures_it_cannot_use(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = Mock(side_effect=AssertionError("żaden z tych obrazów nie nadaje się do OCR"))
    monkeypatch.setattr(subprocess, "run", runner)
    body = paragraph("Wniosek") + "".join(picture(f"rId{number}") for number in range(1, 6)) + picture("rId9")
    data = docx_package(
        body,
        media={"wektor.emf": b"\x01\x00\x00\x00" + b"\x00" * 200, "ikona.png": png(30, 30), "uszkodzony.png": b"\x89PNG\r\n\x1a\n" + b"\x00" * 64},
        targets={"rId4": "https://example.org/zdalny.png", "rId5": "media/brak.png"},
    )

    document = extract(data, "docx")

    assert document.text == "Wniosek"
    assert document.warnings == []
    runner.assert_not_called()


def test_docx_picture_larger_than_its_limit_is_skipped_with_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    small, large = png(200, 100), png(200, 3000)
    seen = ocr_by_content(monkeypatch, {small: "Pieczęć wpływu do urzędu\n"})
    monkeypatch.setattr(docx_reader, "MAX_PICTURE_BYTES", len(large) - 1)
    data = docx_package(picture("rId1") + picture("rId2") + paragraph("Wniosek"), media={"duzy.png": large, "maly.png": small})

    document = extract(data, "docx")

    assert document.text == "Pieczęć wpływu do urzędu\nWniosek"
    assert seen == [small]
    assert document.warnings == [docx_reader._NOT_READ]


@pytest.mark.parametrize("compression", [ZIP_BZIP2, ZIP_LZMA], ids=["bzip2", "lzma"])
@pytest.mark.parametrize("ext", ["docx", "xlsx", "ods"])
def test_zip_entry_with_compression_office_never_writes_is_rejected(ext: str, compression: int) -> None:
    # Dla tych metod zipfile rozpakowuje cały blok wejścia naraz, więc limit odczytu nie chroni pamięci.
    sources = {"docx": docx(paragraph("Wniosek")), "xlsx": xlsx(XLSX_CELL), "ods": ods(ods_row("Wniosek"))}
    buffer = BytesIO()
    with ZipFile(BytesIO(sources[ext])) as source, ZipFile(buffer, "w", compression) as target:
        for name in source.namelist():
            target.writestr(name, source.read(name))
    assert extract(sources[ext], ext).text == "Wniosek"

    with pytest.raises(ExtractionError, match=UNREADABLE):
        extract(buffer.getvalue(), ext)


def test_docx_unpacked_bytes_limit_covers_document_and_notes(monkeypatch: pytest.MonkeyPatch) -> None:
    footnotes = f'<w:footnotes xmlns:w="{WORD_NS}">{paragraph("Przypis")}</w:footnotes>'
    data = docx_package(paragraph("Wniosek"), parts={"word/footnotes.xml": footnotes})
    with ZipFile(BytesIO(data)) as archive:
        unpacked = archive.getinfo("word/document.xml").file_size + archive.getinfo("word/footnotes.xml").file_size

    monkeypatch.setattr(docx_reader, "MAX_UNPACKED_BYTES", unpacked)
    assert extract(data, "docx").text == "Wniosek\nPrzypis"

    # Każda część osobno mieści się w limicie, razem już nie.
    monkeypatch.setattr(docx_reader, "MAX_UNPACKED_BYTES", unpacked - 1)
    with pytest.raises(ExtractionError, match=UNREADABLE):
        extract(data, "docx")


@pytest.mark.parametrize(
    "declaration",
    ['<?xml version="1.0" encoding="shift_jis"?>', '<?xml version="1.0" encoding="brak-takiego"?>'],
    ids=["multi-byte-encoding", "unknown-encoding"],
)
@pytest.mark.parametrize("entry", ["word/document.xml", "word/footnotes.xml", "word/_rels/document.xml.rels"])
def test_docx_unsupported_xml_encoding_is_unreadable(entry: str, declaration: str) -> None:
    # Parser XML zgłasza takie kodowanie jako ValueError albo LookupError; wcześniej kończyło się to kodem 500.
    footnotes = f'<w:footnotes xmlns:w="{WORD_NS}">{paragraph("Przypis")}</w:footnotes>'
    data = docx_package(paragraph("Wniosek") + picture("rId1"), media={"skan.png": png(300, 300)}, parts={"word/footnotes.xml": footnotes})

    with pytest.raises(ExtractionError, match=UNREADABLE):
        extract(rewrite_binary_entry(data, entry, lambda xml: declaration.encode() + xml), "docx")


def rewrite_binary_entry(data: bytes, entry: str, change: Callable[[bytes], bytes]) -> bytes:
    buffer = BytesIO()
    with ZipFile(BytesIO(data)) as source, ZipFile(buffer, "w") as target:
        for name in source.namelist():
            target.writestr(name, change(source.read(name)) if name == entry else source.read(name))
    return buffer.getvalue()


@pytest.mark.parametrize(
    "body",
    [
        # Zagnieżdżenie głębsze niż limit rekurencji Pythona: 400, nie 500.
        paragraph("Wniosek") + "<w:tbl><w:tr><w:tc>" * 400 + paragraph("Tak") + "</w:tc></w:tr></w:tbl>" * 400,
        paragraph("Wniosek") + "<w:p>" + "<w:r>" * 5000 + "<w:t>Tak</w:t>" + "</w:r>" * 5000 + "</w:p>",
        paragraph("Wniosek") + "<w:p>" + "<w:r><w:t>a</w:t></w:r>" * 300_000 + "</w:p>",
    ],
    ids=["deep-tables", "deep-inline", "too-many-elements-in-block"],
)
def test_docx_xml_that_would_exhaust_memory_or_stack_is_unreadable(body: str) -> None:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document_xml(body))

    with pytest.raises(ExtractionError, match=UNREADABLE):
        extract(buffer.getvalue(), "docx")


def test_docx_truncated_after_readable_text_is_unreadable() -> None:
    # Odczyt strumieniowy oddaje akapity przed końcem pliku; częściowy tekst byłby błędem.
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", document_xml(paragraph("Wniosek")).replace("</w:body></w:document>", "<w:p>"))

    with pytest.raises(ExtractionError, match=UNREADABLE):
        extract(buffer.getvalue(), "docx")


def test_docx_memory_does_not_grow_with_number_of_paragraphs() -> None:
    data = docx("<w:p><w:r><w:rPr><w:b/></w:rPr></w:r></w:p>" * 60_000 + paragraph("Tak"))
    tracemalloc.start()
    try:
        text = extract(data, "docx").text
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert text == "Tak"
    # Sam XML ma 2,6 MB. Całe drzewo w pamięci zajmowało ponad 30 MB.
    assert peak < 8 * 1024 * 1024


@pytest.mark.parametrize("root", ["w:body", "w:settings"])
def test_docx_main_part_must_be_a_document(root: str) -> None:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", f'<{root} xmlns:w="{WORD_NS}">{paragraph("Wniosek")}</{root}>')

    with pytest.raises(ExtractionError, match=UNREADABLE):
        extract(buffer.getvalue(), "docx")


def _coi_file(folder: int, pattern: str) -> bytes:
    files = sorted(path for directory in MATERIALS.glob(f"{folder}. *") for path in directory.glob(pattern))
    if not files:
        pytest.skip(f"brak pliku {pattern} z folderu {folder} w {MATERIALS}")
    return files[0].read_bytes()


def _words(text: str) -> list[str]:
    return sorted(word.casefold() for word in "".join(char if char.isalpha() else " " for char in text).split() if len(word) > 3)


@pytest.mark.parametrize("folder", [2, 3, 8])
def test_coi_docx_with_text_boxes_has_words_of_pdf_once(folder: int, ocr_runner: Mock) -> None:
    # Foldery 2 i 8 to strony złożone z pól tekstowych, folder 3 ma jedno pole z adresem urzędu.
    # Przed K2-FINAL każde słowo z pola wychodziło dwa razy (folder 8: 31 tys. znaków zamiast 16 tys.).
    from_docx = extract(_coi_file(folder, "*.docx"), "docx")
    from_pdf = extract(_coi_file(folder, "*.pdf"), "pdf")

    assert _words(from_docx.text) == _words(from_pdf.text)
    assert from_docx.ocr_used is False
    ocr_runner.assert_not_called()


def test_coi_docx_made_of_text_boxes_comes_in_reading_order() -> None:
    lines = extract(_coi_file(8, "*.docx"), "docx").text.splitlines()

    assert lines[0] == "DEKLARACJA O WYSOKOŚCI MIESIĘCZNEJ OPŁATY"
    assert lines.index("A. ORGAN, DO KTÓREGO SKŁADANA JEST DEKLARACJA") < lines.index("B.1 DANE IDENTYFIKACYJNE")
    assert "4. wspólnota mieszkaniowa 5. spółdzielnia mieszkaniowa 6. inny podmiot posiadający nieruchomość" in lines


@pytest.mark.parametrize("folder", [1, 4, 5])
def test_coi_docx_has_all_words_of_pdf_with_notes_and_footers(folder: int, ocr_runner: Mock) -> None:
    files = sorted(
        path
        for directory in MATERIALS.glob(f"{folder}. *")
        for path in directory.glob("*.docx")
        if "wizualizacja" not in path.name.casefold()
    )
    if not files:
        pytest.skip(f"brak pliku .docx z folderu {folder} w {MATERIALS}")

    assert _words(extract(files[0].read_bytes(), "docx").text) == _words(extract(_coi_file(folder, "*.[pP][dD][fF]"), "pdf").text)


@needs_ocr_engine
def test_real_ocr_reads_screenshots_embedded_in_coi_docx() -> None:
    files = sorted(path for directory in MATERIALS.glob("5. *") for path in directory.glob("*wizualizacja*.docx"))
    if not files:
        pytest.skip(f"brak pliku z wizualizacją z folderu 5 w {MATERIALS}")
    data = files[0].read_bytes()
    with ZipFile(BytesIO(data)) as archive:
        assert sum(name.startswith("word/media/") for name in archive.namelist()) == 16

    document = extract(data, "docx")

    # Podpisy pól są tylko na zrzutach ekranu, nie w tekście dokumentu.
    assert document.ocr_used is True
    folded = document.text.casefold()
    assert "wizualizacja" in folded
    assert "kod pocztowy" in folded


JPEG_SCAN = jpeg(1654, 2339)
OTHER_SCAN = jpeg(1654, 2340)


def test_pdf_page_without_text_is_read_from_its_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = ocr_by_content(monkeypatch, {JPEG_SCAN: "Wniosek o wydanie zaświadczenia\nImię i nazwisko\n\x0c"})
    data = scanned_pdf(("", [PdfImage(JPEG_SCAN, 1654, 2339)]))

    document = extract(data, validate_upload("skan.pdf", data, max_bytes=len(data)))

    assert document.text == "Wniosek o wydanie zaświadczenia\nImię i nazwisko"
    assert document.ocr_used is True
    assert document.warnings == []
    # Obraz JPEG trafia do Tesseracta bajt w bajt, bez dekodowania po drodze.
    assert seen == [JPEG_SCAN]


def test_pdf_keeps_text_layer_and_reads_only_pages_without_useful_text(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = ocr_by_content(monkeypatch, {JPEG_SCAN: "Uzasadnienie wniosku\n", OTHER_SCAN: "Strona 4\nPodpis wnioskodawcy\n"})
    with_text = "Wniosek o wydanie decyzji administracyjnej"
    data = scanned_pdf(
        (with_text, [PdfImage(png(600, 400), 600, 400)]),
        ("2", [PdfImage(JPEG_SCAN, 1654, 2339)]),
        ("", []),
        ("Strona 4", [PdfImage(OTHER_SCAN, 1654, 2340)]),
    )

    document = extract(data, "pdf")

    # Strona 1 ma warstwę tekstową, więc jej obraz nie idzie do OCR. Numer strony 2 jest tylko
    # w warstwie tekstowej i zostaje; „Strona 4” jest też na skanie, więc nie stoi dwa razy.
    assert document.text == f"{with_text}\f2\nUzasadnienie wniosku\f\fStrona 4\nPodpis wnioskodawcy"
    assert seen == [JPEG_SCAN, OTHER_SCAN]
    assert document.ocr_used is True
    assert document.warnings == ["Strony PDF bez warstwy tekstowej: 3."]


def test_pdf_reads_page_images_from_top_to_bottom_whatever_the_drawing_order(monkeypatch: pytest.MonkeyPatch) -> None:
    top, middle, bottom = jpeg(1654, 700), jpeg(1654, 701), jpeg(1654, 702)
    seen = ocr_by_content(monkeypatch, {top: "Nagłówek wniosku\n", middle: "Treść wniosku\n", bottom: "Podpis wniosku\n"})
    data = scanned_pdf(
        (
            "",
            [
                PdfImage(bottom, 1654, 702, place=(595, 0, 0, 250, 0, 30)),
                PdfImage(top, 1654, 700, place=(595, 0, 0, 250, 0, 560)),
                PdfImage(middle, 1654, 701, place=(595, 0, 0, 250, 0, 295)),
                # Obraz w zasobach strony, którego strona nie rysuje (wspólne zasoby wielu stron).
                PdfImage(OTHER_SCAN, 1654, 2340, drawn=False),
            ],
        )
    )

    assert extract(data, "pdf").text == "Nagłówek wniosku\nTreść wniosku\nPodpis wniosku"
    assert sorted(seen) == sorted([top, middle, bottom])


def test_pdf_finds_scan_drawn_through_form_object(monkeypatch: pytest.MonkeyPatch) -> None:
    ocr_by_content(monkeypatch, {JPEG_SCAN: "Wniosek ze skanera\n"})

    assert extract(scanned_pdf(("", [PdfImage(JPEG_SCAN, 1654, 2339)]), through_form=True), "pdf").text == "Wniosek ze skanera"


def test_pdf_form_drawing_itself_gives_its_scan_once(monkeypatch: pytest.MonkeyPatch) -> None:
    # Recenzja K2-FINAL, D2: formularz, który rysuje sam siebie, dawał ten sam skan przy każdym poziomie.
    seen = ocr_by_content(monkeypatch, {JPEG_SCAN: "Wniosek ze skanera\n"})

    document = extract(scanned_pdf(("", [PdfImage(JPEG_SCAN, 1654, 2339)]), through_form=True, form_redraws=3), "pdf")

    assert document.text == "Wniosek ze skanera"
    assert seen == [JPEG_SCAN]


def test_pdf_form_drawn_many_times_is_parsed_once(monkeypatch: pytest.MonkeyPatch) -> None:
    parsed: list[object] = []

    class CountingContentStream(pdf_reader.ContentStream):
        def __init__(self, stream: object, pdf: object, *args: object) -> None:
            parsed.append(stream)
            super().__init__(stream, pdf, *args)

    monkeypatch.setattr(pdf_reader, "ContentStream", CountingContentStream)

    assert extract(scanned_pdf(("Strona 1", []), through_form=True, form_uses=50), "pdf").text == "Strona 1"
    assert len(parsed) == 1


def test_pdf_drawing_operations_have_a_budget_per_document(monkeypatch: pytest.MonkeyPatch) -> None:
    ocr_by_content(monkeypatch, {JPEG_SCAN: "Wniosek ze skanera\n"})
    # 120 operacji przed skanem; Do, które rysuje skan, to 123. operacja strony (po q i cm).
    data = scanned_pdf(("", [PdfImage(JPEG_SCAN, 1654, 2339)]), before=b"q Q " * 60)

    monkeypatch.setattr(pdf_reader, "MAX_DRAWING_OPERATIONS", 123)
    assert extract(data, "pdf").text == "Wniosek ze skanera"

    monkeypatch.setattr(pdf_reader, "MAX_DRAWING_OPERATIONS", 122)
    with pytest.raises(ExtractionError, match=UNREADABLE):
        extract(data, "pdf")


def raster_page(samples: bytes, width: int, height: int, **options: object) -> bytes:
    options.setdefault("filter", "/FlateDecode")
    return scanned_pdf(("", [PdfImage(zlib.compress(samples), width, height, **options)]))


@pytest.mark.parametrize(
    ("options", "samples", "expected_header", "expected_rows", "expected_palette"),
    [
        ({}, bytes(range(200)) * 100, (200, 100, 8, 0), b"".join(b"\x00" + bytes(range(200)) for _ in range(100)), b""),
        (
            {"colorspace": "/DeviceRGB"},
            b"\x10\x20\x30" * 20_000,
            (200, 100, 8, 2),
            (b"\x00" + b"\x10\x20\x30" * 200) * 100,
            b"",
        ),
        # Maska 1-bitowa z wierszem dopełnianym do bajtu; /Decode [1 0] odwraca czerń i biel.
        (
            {"colorspace": None, "bits": 1, "extra": "/ImageMask true /Decode [1 0]"},
            b"\xf0" * 26 * 150,
            (203, 150, 1, 0),
            (b"\x00" + b"\x0f" * 26) * 150,
            b"",
        ),
        (
            {"colorspace": "[/Indexed /DeviceRGB 1 <000000 FFFFFF>]", "bits": 1},
            b"\xaa" * 25 * 150,
            (200, 150, 1, 3),
            (b"\x00" + b"\xaa" * 25) * 150,
            b"\x00\x00\x00\xff\xff\xff",
        ),
        (
            {"colorspace": "[/Indexed /DeviceGray 3 <00 55 AA FF>]", "bits": 2},
            b"\x1b" * 50 * 150,
            (200, 150, 2, 3),
            (b"\x00" + b"\x1b" * 50) * 150,
            b"\x00\x00\x00\x55\x55\x55\xaa\xaa\xaa\xff\xff\xff",
        ),
    ],
    ids=["gray", "rgb", "inverted-mask", "rgb-palette", "gray-palette"],
)
def test_pdf_raster_scan_goes_to_ocr_as_png_with_same_pixels(
    monkeypatch: pytest.MonkeyPatch,
    options: dict,
    samples: bytes,
    expected_header: tuple,
    expected_rows: bytes,
    expected_palette: bytes,
) -> None:
    seen: list[bytes] = []

    def tesseract(command: list[str], **arguments: bytes) -> subprocess.CompletedProcess:
        seen.append(arguments["input"])
        return subprocess.CompletedProcess(command, 0, b"Wniosek z rastra\n")

    monkeypatch.setattr(subprocess, "run", tesseract)
    width, height = expected_header[:2]

    document = extract(raster_page(samples, width, height, **options), "pdf")

    assert document.text == "Wniosek z rastra"
    assert len(seen) == 1
    assert png_pixels(seen[0]) == (expected_header, expected_rows, expected_palette)
    assert images.size(seen[0]) == (width, height)


def test_pdf_fax_scan_goes_to_ocr_as_tiff(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[bytes] = []

    def tesseract(command: list[str], **arguments: bytes) -> subprocess.CompletedProcess:
        seen.append(arguments["input"])
        return subprocess.CompletedProcess(command, 0, b"Wniosek z faksu\n")

    monkeypatch.setattr(subprocess, "run", tesseract)
    fax = b"\x00\x10\x01" * 40
    picture_ = PdfImage(fax, 1728, 2339, filter="/CCITTFaxDecode", bits=1, extra="/DecodeParms << /K -1 /Columns 1728 /Rows 2339 >>")

    assert extract(scanned_pdf(("", [picture_])), "pdf").text == "Wniosek z faksu"
    assert seen[0].startswith(b"II*\x00") and seen[0].endswith(fax)
    assert images.size(seen[0]) == (1728, 2339)


@pytest.mark.parametrize(
    "picture_",
    [
        PdfImage(b"\x00" * 64, 1654, 2339, filter="/JBIG2Decode", bits=1),
        PdfImage(b"\x00" * 64, 1654, 2339, filter="/JPXDecode"),
        PdfImage(zlib.compress(b"\x00" * 800 * 400), 200, 400, filter="/FlateDecode", colorspace="/DeviceCMYK"),
        PdfImage(zlib.compress(b"\x00" * 100), 200, 400, filter="/FlateDecode"),
        PdfImage(JPEG_SCAN, 20_000, 20_000),
    ],
    ids=["jbig2", "jpeg-2000", "cmyk-raster", "raster-shorter-than-declared", "over-pixel-limit"],
)
def test_pdf_scan_that_cannot_be_decoded_is_reported_not_guessed(monkeypatch: pytest.MonkeyPatch, picture_: PdfImage) -> None:
    runner = Mock(side_effect=AssertionError("tego obrazu nie umiemy podać Tesseractowi"))
    monkeypatch.setattr(subprocess, "run", runner)
    data = scanned_pdf(("Wniosek o wydanie decyzji administracyjnej", []), ("", [picture_]))

    document = extract(data, "pdf")

    assert document.text == "Wniosek o wydanie decyzji administracyjnej\f"
    assert document.ocr_used is False
    assert document.warnings == [
        "Strony PDF bez warstwy tekstowej: 2.",
        "Strony PDF ze skanem w nieobsługiwanym kodowaniu: 2.",
    ]
    runner.assert_not_called()

    # Sam taki skan to dokument bez treści: kontrolowany błąd, nie pusty wynik.
    with pytest.raises(ExtractionError, match=UNREADABLE):
        extract(scanned_pdf(("", [picture_])), "pdf")


def test_pdf_small_pictures_are_not_read(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = Mock(side_effect=AssertionError("ikona nie idzie do OCR"))
    monkeypatch.setattr(subprocess, "run", runner)
    data = scanned_pdf(("Wniosek o wydanie decyzji administracyjnej", []), ("", [PdfImage(jpeg(30, 30), 30, 30)]))

    document = extract(data, "pdf")

    assert document.warnings == ["Strony PDF bez warstwy tekstowej: 2."]
    runner.assert_not_called()


def test_pdf_ocr_budget_limits_pictures_per_page_and_per_document(monkeypatch: pytest.MonkeyPatch) -> None:
    scans = [jpeg(1654, 1000 + number) for number in range(6)]
    seen = ocr_by_content(monkeypatch, {scan: f"Strona skanu numer {number}\n" for number, scan in enumerate(scans)})

    def page(*numbers: int) -> tuple[str, list[PdfImage]]:
        return "", [PdfImage(scans[number], 1654, 1000 + number, place=(595, 0, 0, 100, 0, 700 - 100 * number)) for number in numbers]

    monkeypatch.setattr(pdf_reader, "MAX_PAGE_PICTURES", 2)
    monkeypatch.setattr(pdf_reader, "MAX_PICTURES", 3)
    document = extract(scanned_pdf(page(0, 1, 2), page(3, 4), page(5)), "pdf")

    # Z pierwszej strony dwa najwyższe obrazy, z drugiej jeden: dokument ma limit trzech.
    assert document.text == "Strona skanu numer 0\nStrona skanu numer 1\fStrona skanu numer 3\f"
    assert sorted(seen) == sorted([scans[0], scans[1], scans[3]])
    assert document.warnings == ["Strony PDF bez warstwy tekstowej: 3."]

    monkeypatch.setattr(pdf_reader, "MAX_PICTURES", 40)
    monkeypatch.setattr(pdf_reader, "MAX_DOCUMENT_PIXELS", 1654 * 1000 + 1654 * 1001)
    assert extract(scanned_pdf(page(0, 1), page(3)), "pdf").text == "Strona skanu numer 0\nStrona skanu numer 1\f"


def test_pdf_with_more_pages_than_limit_is_rejected(monkeypatch: pytest.MonkeyPatch, ocr_runner: Mock) -> None:
    data = pdf("Wniosek", "Uzasadnienie", "Załączniki")
    monkeypatch.setattr(pdf_reader, "MAX_PAGES", 3)
    assert extract(data, "pdf").text == "Wniosek\fUzasadnienie\fZałączniki"

    monkeypatch.setattr(pdf_reader, "MAX_PAGES", 2)
    with pytest.raises(ExtractionError, match=UNREADABLE):
        extract(data, "pdf")


def test_pdf_with_more_text_than_limit_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    data = pdf("Wniosek", "Załączniki")
    monkeypatch.setattr(pdf_reader, "MAX_TEXT_CHARS", len("Wniosek") + len("Załączniki"))
    assert extract(data, "pdf").text == "Wniosek\fZałączniki"

    monkeypatch.setattr(pdf_reader, "MAX_TEXT_CHARS", len("Wniosek") + len("Załączniki") - 1)
    with pytest.raises(ExtractionError, match=UNREADABLE):
        extract(data, "pdf")


def test_pdf_with_broken_drawing_stream_keeps_text_of_other_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = Mock(side_effect=AssertionError("strona z zepsutym rysowaniem nie ma obrazów do OCR"))
    monkeypatch.setattr(subprocess, "run", runner)
    data = scanned_pdf(("Wniosek o wydanie decyzji administracyjnej", []), ("", [PdfImage(JPEG_SCAN, 1654, 2339)]))
    broken = data.replace(b"q 595 0 0 842 0 0 cm /Im", b"q 595 0 0 (z) 0 0 cm /Im")
    assert len(broken) == len(data) and broken != data

    document = extract(broken, "pdf")

    assert document.text == "Wniosek o wydanie decyzji administracyjnej\f"
    assert document.warnings == ["Strony PDF bez warstwy tekstowej: 2."]


def _pdf_with_scan(scan: bytes) -> bytes:
    width, height = images.size(scan)
    colorspace = "/DeviceGray" if scan[scan.index(b"\xff\xc0") + 9] == 1 else "/DeviceRGB"
    return scanned_pdf(("", [PdfImage(scan, width, height, colorspace=colorspace)]), ("1", []))


@needs_ocr_engine
def test_real_ocr_reads_coi_scan_wrapped_in_pdf_through_child_process() -> None:
    scan = _coi_file(5, "*.JPG")
    data = _pdf_with_scan(scan)

    document = extract_in_child_process(data, validate_upload("skan.pdf", data, 10 * 1024 * 1024))

    assert document.ocr_used is True
    first, second = document.text.split("\f")
    assert "wniosek" in first.casefold()
    assert "nadpłat" in first.casefold()
    assert second == "1"
    assert first == ocr.image_text(scan, "pol")
