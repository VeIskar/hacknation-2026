"""Odczyt pliku w osobnym procesie z limitem czasu, pamięci i procesora.

Plik od użytkownika może być bombą dekompresyjną albo PDF-em, który parsuje się minutami.
Limit czasu w wątku żądania nie wystarcza: wątku Pythona nie da się przerwać, więc kosztowny
odczyt trwałby dalej w tle. Proces można zabić razem z procesami Tesseracta, które uruchomił.
"""

import json
import logging
import os
import resource
import signal
import subprocess
import sys
import threading
from pathlib import Path

from app.errors import AppError
from app.extract.common import SERVER_ERROR, Reading, unreadable

# Najdłuższy odczyt pliku COI to skan z folderu 9 (16 stron, ok. 10 s). Limit zostawia zapas
# na wolniejszą maszynę i mieści się w celu 180–200 s na cały formularz.
TIMEOUT_SECONDS = 60
# Limit przestrzeni adresowej każdego procesu odczytu, także Tesseracta. Zmierzone minimum dla
# plików COI: PNG z folderu 9 (62 mln pikseli) działa od 512 MB, skany JPG od 192 MB, formaty
# tekstowe od 128 MB. Limit mieści obraz o ocr.MAX_IMAGE_PIXELS pikseli po 4 bajty.
MEMORY_BYTES = 1536 * 1024 * 1024
_WORKER = "app.extract.worker"
# Katalog, w którym leży pakiet `app`: stąd proces potomny importuje czytniki.
_ROOT = Path(__file__).resolve().parents[2]
# Proces odczytu nie dostaje sekretów API (JWT_SECRET, LLM_API_KEY), tylko to, czego potrzebują
# Python i Tesseract.
_ENVIRONMENT = ("PATH", "LD_LIBRARY_PATH", "TESSDATA_PREFIX", "LANG", "LC_ALL", "PYTHONDONTWRITEBYTECODE")
_LOG_TAIL = 300
_CHUNK = 64 * 1024
_DRAIN_SECONDS = 5
# Każdy odczyt to proces do MEMORY_BYTES i do ocr.MAX_WORKERS procesów Tesseracta z tym samym limitem.
# API dzieli maszynę z modelem lokalnym, więc dwa odczyty naraz; kolejne żądania czekają na swoją kolej.
MAX_PARALLEL_READS = 2
_SLOTS = threading.BoundedSemaphore(MAX_PARALLEL_READS)
# Czekanie na miejsce najwyżej tyle, ile trwa jeden pełny odczyt.
QUEUE_SECONDS = TIMEOUT_SECONDS

_logger = logging.getLogger(__name__)


def read(data: bytes, ext: str, language: str) -> Reading:
    """Wynik `readers.read_document` z procesu potomnego. Limit, awaria i zły plik to ExtractionError.

    Najwyżej MAX_PARALLEL_READS odczytów naraz. Żądanie, które nie dostanie miejsca w QUEUE_SECONDS,
    kończy się błędem 500 („Spróbuj ponownie”): wątek API czeka najwyżej tyle, a nie bez końca.
    """
    command = [sys.executable, "-m", _WORKER, ext, language, str(MEMORY_BYTES), str(TIMEOUT_SECONDS)]
    if not _SLOTS.acquire(timeout=QUEUE_SECONDS):
        _logger.warning("Odczyt pliku .%s odrzucony: miejsca odczytu zajęte przez %s s.", ext, QUEUE_SECONDS)
        raise AppError(detail=SERVER_ERROR)
    try:
        code, output, errors = run(command, data, timeout=TIMEOUT_SECONDS)
    finally:
        _SLOTS.release()
    if code is None:
        _logger.warning("Odczyt pliku .%s przerwany po %s s.", ext, TIMEOUT_SECONDS)
        raise unreadable()
    if code < 0:
        _logger.warning("Odczyt pliku .%s zakończony sygnałem %s.", ext, -code)
        raise unreadable()
    try:
        result = json.loads(output)
        if "error" not in result:
            return Reading(str(result["text"]), bool(result["ocr_used"]), [str(item) for item in result["warnings"]])
        kind, reason = result["error"], str(result["reason"])
    except (ValueError, KeyError, TypeError) as exc:
        # Proces nie oddał wyniku: to błąd wdrożenia (brak modułu, zła ścieżka), nie pliku.
        tail = errors[-_LOG_TAIL:].decode("utf-8", "replace")
        _logger.error("Proces odczytu plików nie działa (kod %s): %s", code, tail)
        raise AppError(detail=SERVER_ERROR) from exc
    if kind == "server":
        _logger.error("Odczyt pliku .%s: %s", ext, reason)
        raise AppError(detail=SERVER_ERROR)
    # „crash” to wyjątek, którego czytnik się nie spodziewał: plik odrzucamy, a ślad zostaje w logu.
    _logger.log(logging.WARNING if kind == "crash" else logging.INFO, "Pliku .%s nie udało się odczytać: %s", ext, reason)
    raise unreadable()


def run(command: list[str], data: bytes, *, timeout: float) -> tuple[int | None, bytes, bytes]:
    """Kod wyjścia, stdout i ostatnie _LOG_TAIL bajtów stderr procesu; kod None oznacza przekroczony limit czasu.

    Proces dostaje własną grupę. Po limicie czasu albo po sygnale ginie cała grupa, więc nie
    zostają po nim procesy potomne; proces zakończony sam poczekał na swoje procesy potomne.
    Stderr czyta osobny wątek i trzyma tylko jego koniec:
    zły plik potrafi wywołać dziesiątki megabajtów ostrzeżeń biblioteki.
    """
    environment = {name: os.environ[name] for name in _ENVIRONMENT if name in os.environ}
    errors_end, errors_start = os.pipe()
    tail = bytearray()
    # Wątek startuje przed procesem: gdy proces nie wystartuje, zamknięcie końca do zapisu kończy wątek.
    drain = threading.Thread(target=_keep_tail, args=(errors_end, tail), daemon=True)
    drain.start()
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=errors_start,
            cwd=_ROOT,
            env=environment,
            start_new_session=True,
        )
    finally:
        os.close(errors_start)
    code = None
    try:
        output, _ = process.communicate(data, timeout=timeout)
        code = process.returncode
    except subprocess.TimeoutExpired:
        return None, b"", b""
    finally:
        # Proces, który sam się zakończył, poczekał na swoje procesy potomne. Po limicie czasu
        # albo po sygnale mógł je zostawić.
        if code is None or code < 0:
            _kill_group(process)
        # Stderr kończy się, gdy zamkną go wszystkie procesy grupy; po zabiciu grupy od razu.
        drain.join(_DRAIN_SECONDS)
    return code, output, bytes(tail)


def _keep_tail(descriptor: int, tail: bytearray) -> None:
    """Czyta potok do końca i zostawia w `tail` ostatnie _LOG_TAIL bajtów."""
    with open(descriptor, "rb", buffering=0) as stream:
        while chunk := stream.read(_CHUNK):
            tail += chunk
            del tail[:-_LOG_TAIL]


def _kill_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    # Odbiera stan procesu i zamyka potoki; po SIGKILL kończy się od razu.
    process.communicate()


def limit_resources(memory_bytes: int, cpu_seconds: int) -> None:
    """Limity bieżącego procesu, dziedziczone przez procesy potomne. Woła je proces odczytu na starcie."""
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    # Po miękkim limicie proces dostaje SIGXCPU, sekundę później SIGKILL.
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
