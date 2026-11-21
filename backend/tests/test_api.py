import asyncio
import json
import tempfile
from collections.abc import Iterator

import pytest
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from samples import PDF, PNG, VALID

from app.config import Settings, get_settings
from app.files import MSG_NAME, MSG_NO_FILE, MSG_TYPE
from app.main import MSG_SERVER_ERROR, app, request_validation_handler

SKELETON = {"title": "Formularz", "tabs": [], "flow": {"links": []}}


@pytest.fixture
def client() -> Iterator[TestClient]:
    app.dependency_overrides[get_settings] = lambda: Settings(max_file_size_mb=1)
    yield TestClient(app)
    app.dependency_overrides.clear()


def post(client: TestClient, filename: str, data: bytes):
    return client.post("/api/forms", files={"file": (filename, data, "application/octet-stream")})


@pytest.mark.parametrize("filename", VALID)
def test_each_format_returns_form_json(client: TestClient, filename: str) -> None:
    response = post(client, filename, VALID[filename][0])
    assert response.status_code == 200, response.text
    assert response.json() == SKELETON


def test_bad_name_is_400(client: TestClient) -> None:
    response = post(client, "wniosek;rm.pdf", PDF)
    assert (response.status_code, response.json()) == (400, {"detail": MSG_NAME})


def test_too_large_is_413(client: TestClient) -> None:
    response = post(client, "wniosek.pdf", PDF.ljust(1024 * 1024 + 1, b"\x00"))
    assert response.status_code == 413
    assert response.json() == {"detail": "Plik jest za duży. Limit to 1 MB."}


def test_much_too_large_is_cut_off_while_streaming(client: TestClient) -> None:
    response = post(client, "wniosek.pdf", PDF.ljust(5 * 1024 * 1024, b"\x00"))
    assert response.status_code == 413


def test_unsupported_type_is_415(client: TestClient) -> None:
    response = post(client, "wniosek.txt", b"zwykly tekst")
    assert (response.status_code, response.json()) == (415, {"detail": MSG_TYPE})


def test_fake_pdf_is_415(client: TestClient) -> None:
    response = post(client, "wniosek.pdf", PNG)
    assert response.status_code == 415
    assert response.json() == {"detail": "Zawartość pliku nie pasuje do rozszerzenia .pdf."}


def test_missing_file_is_400(client: TestClient) -> None:
    response = client.post("/api/forms", data={"inne": "pole"})
    assert (response.status_code, response.json()) == (400, {"detail": MSG_NO_FILE})


def test_empty_file_part_is_400_no_file(client: TestClient) -> None:
    """Formularz HTML bez wybranego pliku wysyła część z filename="" i pustą treścią."""
    body = (
        b'--b\r\nContent-Disposition: form-data; name="file"; filename=""\r\n'
        b"Content-Type: application/octet-stream\r\n\r\n\r\n--b--\r\n"
    )
    response = client.post(
        "/api/forms", content=body, headers={"content-type": "multipart/form-data; boundary=b"}
    )
    assert (response.status_code, response.json()) == (400, {"detail": MSG_NO_FILE})


def test_not_multipart_is_400(client: TestClient) -> None:
    response = client.post("/api/forms", content=PDF, headers={"content-type": "application/pdf"})
    assert (response.status_code, response.json()) == (400, {"detail": MSG_NO_FILE})


def test_two_files_is_400(client: TestClient) -> None:
    response = client.post(
        "/api/forms",
        files=[("file", ("a.pdf", PDF, "application/pdf")), ("file", ("b.pdf", PDF, "application/pdf"))],
    )
    assert response.status_code == 400
    assert isinstance(response.json()["detail"], str)


def test_request_validation_error_is_400_with_text_detail() -> None:
    response = asyncio.run(request_validation_handler(None, RequestValidationError([{"loc": ["x"]}])))
    assert response.status_code == 400
    assert json.loads(response.body) == {"detail": MSG_NO_FILE}


def test_unexpected_error_is_500_with_text_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_: object) -> str:
        raise RuntimeError("tajny szczegół")

    monkeypatch.setattr("app.main.validate_upload", boom)
    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/forms", files={"file": ("wniosek.pdf", PDF, "application/pdf")}
    )
    assert (response.status_code, response.json()) == (500, {"detail": MSG_SERVER_ERROR})


def test_upload_never_touches_disk(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Plik większy niż domyślny bufor Starlette (1 MB) nie może przejść do pliku tymczasowego."""

    def no_disk(self: tempfile.SpooledTemporaryFile) -> None:
        raise AssertionError("plik zapisany na dysk")

    monkeypatch.setattr(tempfile.SpooledTemporaryFile, "rollover", no_disk)
    app.dependency_overrides[get_settings] = lambda: Settings(max_file_size_mb=3)
    response = post(client, "wniosek.pdf", PDF.ljust(2 * 1024 * 1024, b"\x00"))
    assert response.status_code == 200, response.text


def test_default_limit_comes_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_FILE_SIZE_MB", "7")
    assert Settings.from_env().max_file_bytes == 7 * 1024 * 1024
    monkeypatch.delenv("MAX_FILE_SIZE_MB")
    assert Settings.from_env().max_file_size_mb == 10
