"""Proces odczytu jednego pliku: `python -m app.extract.worker <format> <język OCR> <bajty pamięci> <sekundy CPU>`.

Plik przychodzi na stdin, wynik wychodzi na stdout jako JSON. Uruchamia go `sandbox.read`.
"""

import json
import logging
import sys
import traceback
from types import TracebackType

from app.errors import ExtractionError
from app.extract.common import SetupError
from app.extract.sandbox import limit_resources


def main(arguments: list[str]) -> None:
    ext, language, memory_bytes, cpu_seconds = arguments
    # Czytniki łapią błędy, których spodziewają się po złym pliku. Każdy inny wyjątek też kończy
    # się wynikiem dla procesu API, zamiast śladu stosu na stderr.
    sys.excepthook = _report_crash
    try:
        limit_resources(int(memory_bytes), int(cpu_seconds))
    except (OSError, ValueError):
        _write({"error": "server", "reason": "nie można ustawić limitów zasobów procesu odczytu"})
        return
    _write(_result(sys.stdin.buffer.read(), ext, language))


def _result(data: bytes, ext: str, language: str) -> dict:
    try:
        from app.extract.readers import read_document

        reading = read_document(data, ext, language=language)
        return {"text": reading.text, "ocr_used": reading.ocr_used, "warnings": reading.warnings}
    except ExtractionError:
        return {"error": "unreadable", "reason": "czytnik odrzucił plik"}
    except SetupError as exc:
        return {"error": "server", "reason": exc.reason}
    except ImportError as exc:
        return {"error": "server", "reason": f"brak biblioteki {exc.name}"}
    except MemoryError:
        return {"error": "unreadable", "reason": "limit pamięci"}


def _report_crash(kind: type[BaseException], error: BaseException, trace: TracebackType | None) -> None:
    """Do logu API trafia typ błędu i miejsce w kodzie, bez komunikatu: ten mógłby cytować dokument."""
    frames = traceback.extract_tb(trace)
    place = f"{frames[-1].name} ({frames[-1].lineno})" if frames else "?"
    _write({"error": "crash", "reason": f"{kind.__name__} w {place}"})


def _write(result: dict) -> None:
    sys.stdout.buffer.write(json.dumps(result).encode("ascii"))
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    # pypdf i olefile ostrzegają przez logging na stderr, przy złym pliku nawet przy każdym obiekcie
    # (54 MB z PDF 26 kB). Proces API czyta ze stderr tylko końcówkę, więc te wpisy nic nie wnoszą.
    # Wyłączone tylko tu, nie w main(): testy wołają main() w procesie pytesta.
    logging.disable(logging.CRITICAL)
    main(sys.argv[1:])
