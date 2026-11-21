from pathlib import Path

import pytest
from samples import DOC, DOCX, JPG, ODS, ODT, PDF, PLAIN_ZIP, PNG, VALID, XLSX

from app.errors import UploadError
from app.files import MSG_NAME, MSG_TYPE, validate_upload
from app.files import SUPPORTED as SUPPORTED_FORMATS

LIMIT = 1024 * 1024
MATERIALS = Path(__file__).resolve().parents[2] / "materialy"


def rejected(filename: str, data: bytes, max_bytes: int = LIMIT) -> UploadError:
    with pytest.raises(UploadError) as info:
        validate_upload(filename, data, max_bytes)
    return info.value


@pytest.mark.parametrize("filename", VALID)
def test_accepts_each_format(filename: str) -> None:
    data, ext = VALID[filename]
    assert validate_upload(filename, data, LIMIT) == ext


@pytest.mark.parametrize("filename", ["WNIOSEK.PDF", "Wniosek.Pdf", "skan.JPEG", "skan.JPE"])
def test_extension_case_does_not_matter(filename: str) -> None:
    data = JPG if ".jp" in filename.lower() else PDF
    assert validate_upload(filename, data, LIMIT) in {"pdf", "jpg"}


def test_polish_name_with_spaces_is_fine() -> None:
    assert validate_upload("Wniosek o zwrot opłaty – kopia (2).pdf", PDF, LIMIT) == "pdf"


@pytest.mark.parametrize("char", list(";:></\\|'*%$"))
def test_forbidden_character_in_name(char: str) -> None:
    error = rejected(f"wnio{char}sek.pdf", PDF)
    assert (error.status_code, error.detail) == (400, MSG_NAME)


@pytest.mark.parametrize("filename", ["", "a" * 247 + ".pdf", "wnio\x00sek.pdf", "a\nb.pdf"])
def test_bad_name(filename: str) -> None:
    assert rejected(filename, PDF).status_code == 400


def test_name_of_exactly_250_chars_is_fine() -> None:
    assert validate_upload("a" * 246 + ".pdf", PDF, LIMIT) == "pdf"


def test_too_large() -> None:
    error = rejected("wniosek.pdf", PDF + b"\x00" * LIMIT)
    assert (error.status_code, error.detail) == (413, "Plik jest za duży. Limit to 1 MB.")


def test_exactly_at_limit_is_fine() -> None:
    assert validate_upload("wniosek.pdf", PDF.ljust(LIMIT, b"\x00"), LIMIT) == "pdf"


def test_name_is_checked_before_size() -> None:
    assert rejected("a:b.pdf", PDF * LIMIT).status_code == 400


@pytest.mark.parametrize("filename", ["wniosek.txt", "wniosek.exe", "wniosek", "wniosek.", "x.jp"])
def test_unsupported_type(filename: str) -> None:
    error = rejected(filename, PDF)
    assert (error.status_code, error.detail) == (415, MSG_TYPE)


@pytest.mark.parametrize(
    ("filename", "data"),
    [
        ("fałszywy.pdf", PNG),
        ("fałszywy.pdf", b"to jest zwykly tekst"),
        ("fałszywy.pdf", b""),
        ("fałszywy.png", JPG),
        ("fałszywy.jpg", PNG),
        ("fałszywy.doc", PDF),
        ("fałszywy.docx", XLSX),
        ("fałszywy.docx", PLAIN_ZIP),
        ("fałszywy.xlsx", DOCX),
        ("fałszywy.xlsx", b"PK\x03\x04 uszkodzony zip"),
        ("fałszywy.ods", ODT),
        ("fałszywy.ods", XLSX),
        ("fałszywy.docx", DOC),
    ],
)
def test_content_must_match_extension(filename: str, data: bytes) -> None:
    error = rejected(filename, data)
    ext = filename.rsplit(".", 1)[1]
    assert (error.status_code, error.detail) == (
        415,
        f"Zawartość pliku nie pasuje do rozszerzenia .{ext}.",
    )


def test_fake_pdf_message_keeps_users_extension_case() -> None:
    assert rejected("SKAN.JPEG", PDF).detail == "Zawartość pliku nie pasuje do rozszerzenia .jpeg."


def test_ods_fixture_is_valid_zip() -> None:
    assert validate_upload("arkusz.ods", ODS, LIMIT) == "ods"


def test_doc_that_is_really_docx_is_read_as_docx() -> None:
    assert validate_upload("wniosek.DOC", DOCX, LIMIT) == "docx"


def test_doc_with_other_zip_inside_is_rejected() -> None:
    assert rejected("wniosek.doc", XLSX).status_code == 415


@pytest.mark.parametrize("folder", [2, 3, 4, 5, 6, 7, 8, 9])
def test_every_real_task_file_passes(folder: int) -> None:
    """Pliki z zadania, także .DOC będące DOCX-em (foldery 5 i 7). Folderu 1 nie używamy (D5)."""
    matches = sorted(MATERIALS.glob(f"{folder}. *"))
    if not matches:
        pytest.skip(f"brak folderu {folder} w {MATERIALS}")
    files = [p for p in matches[0].iterdir() if p.suffix.lower() != ".json"]
    assert files
    for path in files:
        assert validate_upload(path.name, path.read_bytes(), 10 * LIMIT) in SUPPORTED_FORMATS
