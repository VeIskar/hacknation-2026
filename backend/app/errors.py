"""Błędy przepływu z kodem HTTP. main.py zamienia każdy AppError na odpowiedź {"detail": ...}.

Treści komunikatów: SPEC.md, rozdz. „API contract”.
"""


class AppError(Exception):
    status_code: int = 500

    def __init__(self, detail: str, status_code: int | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        if status_code is not None:
            self.status_code = status_code


class UploadError(AppError):
    """Zła nazwa (400), za duży plik (413), zły typ lub treść (415). Rzuca app/files.py."""

    status_code = 400


class ExtractionError(AppError):
    """Nie da się odczytać treści z pliku (422). Rzuca app/extract."""

    status_code = 422


class LLMUnavailable(AppError):
    """Model nie odpowiada albo przekroczył czas (503). Rzuca app/llm.py."""

    status_code = 503
