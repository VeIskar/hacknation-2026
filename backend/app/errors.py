"""Błędy przepływu z kodem HTTP. main.py zamienia każdy AppError na odpowiedź {"detail": ...}.

Kody i treści komunikatów: SPEC.md, rozdz. „API contract”.
Argumenty są wyłącznie nazwane: UploadError(detail="...", status_code=415).
"""


def _rebuild(cls: type["AppError"], detail: str, status_code: int) -> "AppError":
    return cls(detail=detail, status_code=status_code)


class AppError(Exception):
    status_code: int = 500
    allowed_status_codes: frozenset[int] = frozenset(range(400, 600))

    def __init__(self, *, detail: str, status_code: int | None = None) -> None:
        if not isinstance(detail, str):
            raise TypeError(f"detail ma być tekstem, jest {type(detail).__name__}")
        if not detail.strip():
            raise ValueError("detail nie może być pusty")
        code = type(self).status_code if status_code is None else status_code
        # bool jest podtypem int, a True jako kod HTTP to zawsze pomyłka wywołującego.
        if isinstance(code, bool) or not isinstance(code, int):
            raise TypeError(f"status_code ma być liczbą całkowitą, jest {type(code).__name__}")
        if code not in self.allowed_status_codes:
            raise ValueError(f"{type(self).__name__} nie przyjmuje kodu HTTP {code}")
        super().__init__(detail)
        self.detail = detail
        self.status_code = code

    def __reduce__(self) -> tuple:
        # Domyślne pickle i copy wołają cls(*args), a konstruktor przyjmuje tylko argumenty nazwane.
        # Bez tego błąd rzucony w procesie roboczym (np. OCR) nie wróciłby do procesu API.
        return (_rebuild, (type(self), self.detail, self.status_code))


class UploadError(AppError):
    """Zła nazwa (400), za duży plik (413), zły typ lub treść (415). Rzuca app/files.py."""

    status_code = 400
    allowed_status_codes = frozenset({400, 413, 415})


class ExtractionError(AppError):
    """Plik przeszedł kontrolę, ale nie da się odczytać jego treści (400). Rzuca app/extract."""

    status_code = 400
    allowed_status_codes = frozenset({400})


class LLMUnavailable(AppError):
    """Model nie odpowiada, przekroczył czas albo nie zwrócił poprawnej analizy (503).

    Rzucają app/llm.py i app/analysis.py.
    """

    status_code = 503
    allowed_status_codes = frozenset({503})
