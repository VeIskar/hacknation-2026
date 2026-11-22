import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app import lint, quality
from app.analysis import analyze
from app.auth import AuthError, require_token
from app.config import Settings, get_settings
from app.errors import AppError
from app.extract import extract
from app.files import MSG_NO_FILE, read_single_file, validate_upload
from app.generator import build_form
from app.llm import provider

log = logging.getLogger(__name__)

MSG_SERVER_ERROR = "Coś poszło nie tak. Spróbuj ponownie."

UPLOAD_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["file"],
                    "properties": {"file": {"type": "string", "format": "binary"}},
                }
            }
        },
    }
}

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    get_settings()  # zła wartość w .env zatrzymuje start z nazwą zmiennej, a nie daje 500 później
    yield


app = FastAPI(title="Cyfryzacja formularzy", lifespan=lifespan)


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


@app.exception_handler(AuthError)
async def auth_error_handler(_: Request, exc: AuthError) -> JSONResponse:
    # RFC 6750, 3: odpowiedź 401 mówi, jakiego schematu oczekujemy.
    return JSONResponse(
        {"detail": exc.detail}, status_code=exc.status_code, headers={"WWW-Authenticate": "Bearer"}
    )


@app.exception_handler(RequestValidationError)
async def request_validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    # D2: bez 422, detail zawsze tekstem (front pokazuje go bez zmian).
    return JSONResponse({"detail": MSG_NO_FILE}, status_code=400)


@app.exception_handler(Exception)
async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
    log.exception("Nieoczekiwany błąd", exc_info=exc)
    return JSONResponse({"detail": MSG_SERVER_ERROR}, status_code=500)


class FormRejectedByLinter(RuntimeError):
    """Generator dał JSON, który nie przechodzi lintera: błąd po naszej stronie, więc 500 (handler ogólny)."""


def process_file(data: bytes, ext: str, settings: Settings) -> dict[str, Any]:
    """Łańcuch z DELEGACJA rozdz. 2: odczyt → analiza → JSON COI → linter.

    Błędy AppError (400 z odczytu, 503 z analizy) idą dalej do app_error_handler.
    Zła odpowiedź lintera to 500. Wymaga decyzji lidera; do tego czasu błędy trafiają do logu.
    """
    document = extract(data, ext)
    analyzed = analyze(document, settings=settings)
    if not settings.llm_fixture:
        grounded = quality.ground(analyzed, document)
        analyzed = grounded.analysis
        corrections = grounded.correction_count
        log.info("Korekty strażnika %d, uwagi %d", corrections, len(grounded.notes) - corrections)
    form = build_form(analyzed)
    errors = lint.check(form)
    if errors:
        log.error("JSON odrzucony przez linter (%d błędów): %s", len(errors), "; ".join(errors[:20]))
        raise FormRejectedByLinter(f"{len(errors)} błędów lintera")
    return form


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/info")
def info(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, str]:
    return {"llm": provider(settings), "model": settings.llm_model}


@app.post("/api/forms", openapi_extra=UPLOAD_BODY, dependencies=[Depends(require_token)])
async def create_form(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> JSONResponse:
    filename, data = await read_single_file(request, settings.max_file_bytes)
    ext = validate_upload(filename, data, settings.max_file_bytes)
    # OCR i model trwają do minut: w wątku, żeby /health i inne żądania nie czekały.
    form = await run_in_threadpool(process_file, data, ext, settings)
    return JSONResponse(form)
