import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.errors import AppError
from app.files import MSG_NO_FILE, read_single_file, validate_upload

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


@app.exception_handler(RequestValidationError)
async def request_validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    # D2: bez 422, detail zawsze tekstem (front pokazuje go bez zmian).
    return JSONResponse({"detail": MSG_NO_FILE}, status_code=400)


@app.exception_handler(Exception)
async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
    log.exception("Nieoczekiwany błąd", exc_info=exc)
    return JSONResponse({"detail": MSG_SERVER_ERROR}, status_code=500)


def form_skeleton() -> dict[str, Any]:
    """M1.1: stały szkielet do czasu generatora (P1) i sklejenia (M1.4)."""
    return {"title": "Formularz", "tabs": [], "flow": {"links": []}}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/forms", openapi_extra=UPLOAD_BODY)
async def create_form(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> JSONResponse:
    filename, data = await read_single_file(request, settings.max_file_bytes)
    validate_upload(filename, data, settings.max_file_bytes)
    return JSONResponse(form_skeleton())
