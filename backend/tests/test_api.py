import asyncio
import json
import logging
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from samples import PDF, PNG, VALID, XLSX
from test_extract import docx, pdf

from app import lint
from app import main as main_module
from app.config import Settings, get_settings
from app.files import MSG_NAME, MSG_NO_FILE, MSG_TYPE
from app.generator import build_form
from app.llm import UNAVAILABLE_DETAIL
from app.main import MSG_SERVER_ERROR, app, request_validation_handler
from app.models import FormAnalysis

# Warstwa uploadu (M1.1) jest testowana bez łańcucha analizy: process_file to atrapa.
STUB_FORM = {"title": "Atrapa", "tabs": [], "flow": {"links": []}}
FIELDS = Path(__file__).parent / "fixtures" / "fields.json"
MSG_UNREADABLE = "Nie udało się odczytać treści pliku."


@pytest.fixture
def processed(monkeypatch: pytest.MonkeyPatch) -> list[tuple[bytes, str]]:
    calls: list[tuple[bytes, str]] = []

    def stub(data: bytes, ext: str, settings: Settings) -> dict:
        calls.append((data, ext))
        return STUB_FORM

    monkeypatch.setattr(main_module, "process_file", stub)
    return calls


@pytest.fixture
def client(processed: list[tuple[bytes, str]]) -> Iterator[TestClient]:
    app.dependency_overrides[get_settings] = lambda: Settings(max_file_size_mb=1)
    yield TestClient(app)
    app.dependency_overrides.clear()


def post(client: TestClient, filename: str, data: bytes):
    return client.post("/api/forms", files={"file": (filename, data, "application/octet-stream")})


@pytest.mark.parametrize("filename", VALID)
def test_each_format_reaches_the_pipeline_with_its_format(
    client: TestClient, processed: list[tuple[bytes, str]], filename: str
) -> None:
    data, ext = VALID[filename]
    response = post(client, filename, data)
    assert response.status_code == 200, response.text
    assert response.json() == STUB_FORM
    assert processed == [(data, ext)]


def test_bad_name_is_400(client: TestClient) -> None:
    response = post(client, "wniosek;rm.pdf", PDF)
    assert (response.status_code, response.json()) == (400, {"detail": MSG_NAME})


def test_too_large_is_413(client: TestClient) -> None:
    response = post(client, "wniosek.pdf", PDF.ljust(1024 * 1024 + 1, b"\x00"))
    assert response.status_code == 413
    assert response.json() == {"detail": "Plik jest za duży. Limit to 1 MB."}


def test_declared_content_length_over_limit_is_413(client: TestClient) -> None:
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


@pytest.mark.parametrize(
    "content_type",
    ["Multipart/Form-Data; boundary=b", "MULTIPART/FORM-DATA; BOUNDARY=b", "multipart/form-data;boundary=b"],
)
def test_content_type_is_case_insensitive(client: TestClient, content_type: str) -> None:
    """Typ MIME i nazwy parametrów nie zależą od wielkości liter (RFC 2045)."""
    body = (
        b'--b\r\nContent-Disposition: form-data; name="file"; filename="a.pdf"\r\n\r\n'
        + PDF
        + b"\r\n--b--\r\n"
    )
    response = client.post("/api/forms", content=body, headers={"content-type": content_type})
    assert response.status_code == 200, response.text


def test_stream_without_content_length_is_cut_off_early() -> None:
    """Bez Content-Length (chunked) limit działa w pętli odczytu i przerywa ją przed końcem.

    TestClient czyta całe ciało przed wywołaniem aplikacji, więc wołamy ASGI bezpośrednio.
    """
    app.dependency_overrides[get_settings] = lambda: Settings(max_file_size_mb=1)
    chunk = b"\x00" * (512 * 1024)
    total_chunks = 20  # 10 MB, limit to 1 MB
    received = 0
    sent: list[dict] = []

    async def receive() -> dict:
        nonlocal received
        received += 1
        return {"type": "http.request", "body": chunk, "more_body": received < total_chunks}

    async def send(message: dict) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/forms",
        "raw_path": b"/api/forms",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"content-type", b"multipart/form-data; boundary=b")],
        "client": ("test", 1),
        "server": ("test", 80),
    }
    try:
        asyncio.run(app(scope, receive, send))
    finally:
        app.dependency_overrides.clear()

    start = next(m for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    assert start["status"] == 413
    assert json.loads(body) == {"detail": "Plik jest za duży. Limit to 1 MB."}
    assert received <= 3, f"odczytano {received} z {total_chunks} fragmentów"


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


# M1.4: prawdziwy łańcuch extract → analyze → build_form → lint.check, model zastępuje LLM_FIXTURE.
PDF_WITH_TEXT = pdf("WNIOSEK O STWIERDZENIE NADPLATY PODATKU\nDane wnioskodawcy\nKwota nadplaty")
DOCX_WITH_TEXT = docx("<w:p><w:r><w:t>Wniosek o stwierdzenie nadpłaty podatku</w:t></w:r></w:p>")
EXPECTED_FORM = build_form(FormAnalysis.model_validate_json(FIELDS.read_text(encoding="utf-8")))


@pytest.fixture
def pipeline() -> Iterator[TestClient]:
    app.dependency_overrides[get_settings] = lambda: Settings(llm_fixture=str(FIELDS))
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.mark.parametrize(("filename", "data"), [("wniosek.pdf", PDF_WITH_TEXT), ("wniosek.docx", DOCX_WITH_TEXT)])
def test_document_becomes_coi_json_that_passes_linter(pipeline: TestClient, filename: str, data: bytes) -> None:
    response = post(pipeline, filename, data)
    assert response.status_code == 200, response.text
    form = response.json()
    assert lint.check(form) == []
    assert form == EXPECTED_FORM


def test_document_without_text_is_400(pipeline: TestClient) -> None:
    response = post(pipeline, "wniosek.pdf", pdf(""))
    assert (response.status_code, response.json()) == (400, {"detail": MSG_UNREADABLE})


def test_format_without_reader_yet_is_400(pipeline: TestClient) -> None:
    """XLSX przechodzi kontrolę pliku, ale K2 nie ma jeszcze czytnika: 400, nie 500."""
    response = post(pipeline, "wniosek.xlsx", XLSX)
    assert (response.status_code, response.json()) == (400, {"detail": MSG_UNREADABLE})


def test_model_unavailable_is_503(pipeline: TestClient) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(llm_fixture="/brak/atrapy.json")
    response = post(pipeline, "wniosek.pdf", PDF_WITH_TEXT)
    assert (response.status_code, response.json()) == (503, {"detail": UNAVAILABLE_DETAIL})


def test_form_rejected_by_linter_is_500_with_errors_in_log(
    pipeline: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Zły JSON z generatora to nasz błąd, nie użytkownika (tymczasowo 500, decyzja lidera w toku)."""
    monkeypatch.setattr(main_module, "build_form", lambda _: {"title": "x", "tabs": [], "flow": {"links": []}})
    with caplog.at_level(logging.ERROR, logger="app.main"):
        response = post(pipeline, "wniosek.pdf", PDF_WITH_TEXT)
    assert (response.status_code, response.json()) == (500, {"detail": MSG_SERVER_ERROR})
    assert "linter" in caplog.text.lower()
    assert lint.check({"title": "x", "tabs": [], "flow": {"links": []}})[0] in caplog.text


def test_health_answers_while_form_is_analysed(monkeypatch: pytest.MonkeyPatch) -> None:
    """analyze trwa minuty: musi działać poza pętlą zdarzeń, inaczej /health i compose widzą martwe api."""
    started, release = threading.Event(), threading.Event()
    real_analyze = main_module.analyze

    def slow_analyze(doc, *, settings):
        started.set()
        assert release.wait(2), "analiza zablokowała pętlę zdarzeń"
        return real_analyze(doc, settings=settings)

    monkeypatch.setattr(main_module, "analyze", slow_analyze)
    app.dependency_overrides[get_settings] = lambda: Settings(llm_fixture=str(FIELDS))

    async def scenario() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            files = {"file": ("wniosek.pdf", PDF_WITH_TEXT, "application/pdf")}
            form = asyncio.create_task(client.post("/api/forms", files=files))
            await asyncio.to_thread(started.wait, 2)
            health = await client.get("/health")
            release.set()
            return health, await form

    try:
        health, form = asyncio.run(scenario())
    finally:
        release.set()
        app.dependency_overrides.clear()
    assert health.status_code == 200
    assert form.status_code == 200, form.text
