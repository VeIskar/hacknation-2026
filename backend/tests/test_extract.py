import subprocess
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock
from zipfile import ZipFile

import pytest
from samples import JPG, PNG

import app.extract as extract_module
from app.config import Settings
from app.errors import AppError, ExtractionError
from app.extract import extract
from app.files import validate_upload
from app.models import SourceFormat

MATERIALS = Path(__file__).resolve().parents[2] / "materialy"
WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def docx(body: str, *, entry: str = "word/document.xml", trailing: str = "") -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        xml = f'<w:document xmlns:w="{WORD_NS}"><w:body>{body}</w:body></w:document>'
        archive.writestr(entry, xml + trailing)
    return buffer.getvalue()


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
    ("folder", "suffix", "keyword"),
    [(1, ".docx", "numer"), (5, ".docx", "nadpłat"), (5, ".doc", "nadpłat")],
    ids=["control-docx", "working-docx", "working-docx-with-doc-extension"],
)
def test_extracts_coi_document(folder: int, suffix: str, keyword: str) -> None:
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

    assert document.source_format is SourceFormat.DOCX
    assert "wniosek" in document.text.casefold()
    assert keyword in document.text.casefold()


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
