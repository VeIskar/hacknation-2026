"""Elementy wspólne czytników: komunikat błędu odczytu, czyszczenie tekstu i ograniczony odczyt ZIP."""

import re
from io import BytesIO
from types import TracebackType
from typing import Self
from zipfile import ZipFile

from app.errors import ExtractionError
from app.files import ZIP_ERRORS

UNREADABLE = "Nie udało się odczytać treści pliku."
# Znaki sterujące poza tabulatorem i końcem wiersza oraz niesparowane surogaty UTF-16. Font PDF albo
# komórka arkusza mogą je oddać jako tekst, a \f rozdziela strony i surogat nie daje się zapisać w UTF-8.
NOT_TEXT = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\ud800-\udfff]")


def unreadable() -> ExtractionError:
    return ExtractionError(detail=UNREADABLE)


def clean_text(text: str) -> str:
    """Końce wierszy jako \\n, inne znaki sterujące jako spacja, bez odstępów na brzegach."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return NOT_TEXT.sub(" ", text).strip()


class ZipParts:
    """Wpisy archiwum ZIP czytane w pamięci, ze wspólnym limitem rozpakowanych bajtów dla całego pliku."""

    def __init__(self, data: bytes, max_bytes: int) -> None:
        try:
            self._archive = ZipFile(BytesIO(data))
        except ZIP_ERRORS as exc:
            raise unreadable() from exc
        self._remaining = max_bytes

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        self._archive.close()

    def names(self) -> list[str]:
        return self._archive.namelist()

    def read(self, name: str, *, max_bytes: int | None = None) -> bytes:
        """Treść wpisu. Brak wpisu, uszkodzenie albo przekroczenie limitu to ExtractionError."""
        limit = self._remaining if max_bytes is None else min(max_bytes, self._remaining)
        try:
            with self._archive.open(name) as entry:
                content = entry.read(limit + 1)
        except ZIP_ERRORS as exc:
            raise unreadable() from exc
        if len(content) > limit:
            raise unreadable()
        self._remaining -= len(content)
        return content
