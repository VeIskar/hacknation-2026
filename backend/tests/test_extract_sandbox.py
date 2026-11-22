"""Piaskownica odczytu: osobny proces, limit czasu, pamięci i procesora, sprzątanie procesów potomnych."""

import copy
import io
import json
import logging
import os
import pickle
import shutil
import signal
import subprocess
import sys
import threading
import time
import tracemalloc
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from extract_builders import png, scanned_pdf, word_document
from test_extract import docx, ods, ods_row, pdf, xlsx

from app.config import Settings
from app.errors import AppError, ExtractionError
from app.extract import extract, readers, sandbox, worker
from app.extract.common import Reading, SetupError
from app.models import SourceFormat

UNREADABLE = "Nie udało się odczytać treści pliku."
SERVER_ERROR = "Coś poszło nie tak. Spróbuj ponownie."
XLSX_ROW = '<row r="1"><c r="A1" t="inlineStr"><is><t>Wniosek</t></is></c></row>'


def python(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # Proces zabity, ale jeszcze nieodebrany przez rodzica, nadal ma wpis: stan Z.
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except (FileNotFoundError, ProcessLookupError):
        # Zniknął między sprawdzeniem a odczytem stanu: brak wpisu albo błąd odczytu wpisu.
        return False


def wait_until_dead(pid: int) -> bool:
    deadline = time.monotonic() + 5
    while alive(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    return not alive(pid)


def heavy_pdf(pages: int, megabytes: int = 60) -> bytes:
    """PDF z recenzji K2.3: strona to 60 MB spacji i jedno słowo, a strumień kompresuje się do 58 kB."""
    stream = zlib.compress(b" " * (megabytes * 1_000_000) + b"BT /F1 12 Tf 72 700 Td (Wniosek) Tj ET", 9)
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for _ in range(pages):
        objects.append(b"<< /Filter /FlateDecode /Length %d >>\nstream\n%b\nendstream" % (len(stream), stream))
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> "
            b"/Contents %d 0 R >>" % len(objects)
        )
        kids.append(b"%d 0 R" % len(objects))
    objects[1] = b"<< /Type /Pages /Kids [%b] /Count %d >>" % (b" ".join(kids), pages)
    body, offsets = b"%PDF-1.4\n", []
    for number, content in enumerate(objects, start=1):
        offsets.append(len(body))
        body += b"%d 0 obj\n%b\nendobj\n" % (number, content)
    table = b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    table += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    return body + table + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, len(body))


@pytest.mark.parametrize(
    ("data", "ext", "expected"),
    [
        (pdf("Wniosek o wydanie zaświadczenia", "Załączniki"), "pdf", "Wniosek o wydanie zaświadczenia\fZałączniki"),
        (docx("<w:p><w:r><w:t>Zażółć gęślą jaźń</w:t></w:r></w:p>"), "docx", "Zażółć gęślą jaźń"),
        (word_document("Wniosek\rZałączniki\r"), "doc", "Wniosek\nZałączniki"),
        (xlsx(XLSX_ROW), "xlsx", "Wniosek"),
        (ods(ods_row("Wniosek", "Kwota")), "ods", "Wniosek | Kwota"),
    ],
    ids=["pdf", "docx", "doc", "xlsx", "ods"],
)
def test_extract_reads_document_in_child_process(data: bytes, ext: str, expected: str) -> None:
    document = extract(data, ext)

    assert document.source_format is SourceFormat(ext)
    assert document.text == expected
    assert document.ocr_used is False
    assert document.images == []
    assert document.warnings == []


def test_extract_passes_ocr_language_and_result_of_child_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Atrapa programu na PATH: proces odczytu to osobny proces, więc atrapa w pamięci testu do niego
    # nie sięga. Dowiązanie do `echo` działa też tam, gdzie /tmp nie pozwala uruchamiać plików
    # (kontener API). Atrapa wypisuje swoje argumenty, więc tekst „ze skanu” to wywołanie Tesseracta.
    (tmp_path / "tesseract").symlink_to(shutil.which("echo"))
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr("app.extract.get_settings", lambda: Settings(ocr_lang="pol+eng"))

    document = extract(png(60, 400), "png")

    assert document.text == "stdin stdout -l pol+eng"
    assert document.ocr_used is True


def test_unreadable_file_in_child_process_is_contract_error(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="app.extract.sandbox")

    with pytest.raises(ExtractionError) as exc_info:
        extract(b"%PDF-1.7\n" + b"\x00\xff losowe bajty " * 64, "pdf")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == UNREADABLE
    assert "czytnik odrzucił plik" in caplog.text


def test_costly_pdf_is_stopped_by_time_limit_and_leaves_no_process(monkeypatch: pytest.MonkeyPatch) -> None:
    # Bez limitu ten plik czyta się ponad 120 s (recenzja K2.3). Wątku nie da się przerwać, proces tak.
    data = heavy_pdf(40)
    assert len(data) < 2_500_000
    started: list[subprocess.Popen] = []
    popen = subprocess.Popen

    def recording(*args: object, **options: object) -> subprocess.Popen:
        started.append(popen(*args, **options))
        return started[-1]

    monkeypatch.setattr(subprocess, "Popen", recording)
    monkeypatch.setattr(sandbox, "TIMEOUT_SECONDS", 2)
    before = time.monotonic()

    with pytest.raises(ExtractionError, match=UNREADABLE):
        extract(data, "pdf")

    assert time.monotonic() - before < 10
    assert len(started) == 1
    assert started[0].returncode is not None
    assert wait_until_dead(started[0].pid)


def test_memory_limit_stops_decompression_bomb(monkeypatch: pytest.MonkeyPatch) -> None:
    # Strona rozpakowuje się do 40 MB. Mieści się w limicie procesu odczytu, a w ciasnym już nie.
    data = heavy_pdf(1, megabytes=40)
    assert len(data) < 50_000
    assert extract(data, "pdf").text == "Wniosek"

    monkeypatch.setattr(sandbox, "MEMORY_BYTES", 120 * 1024 * 1024)
    with pytest.raises(ExtractionError, match=UNREADABLE):
        extract(data, "pdf")


def test_run_kills_whole_process_group_after_time_limit(tmp_path: Path) -> None:
    # Proces odczytu uruchamia Tesseracta. Po limicie czasu nie może po nim zostać żaden proces.
    record = tmp_path / "pid"
    code = (
        "import subprocess, sys, time\n"
        "child = subprocess.Popen(['sleep', '60'])\n"
        f"open({str(record)!r}, 'w').write(str(child.pid))\n"
        "time.sleep(60)\n"
    )
    before = time.monotonic()

    result = sandbox.run(python(code), b"", timeout=1.5)

    assert result == (None, b"", b"")
    assert time.monotonic() - before < 10
    assert wait_until_dead(int(record.read_text()))


def test_run_kills_children_left_by_process_ended_with_signal(tmp_path: Path) -> None:
    # Jak Tesseract w procesie odczytu: proces potomny nie dziedziczy potoków, którymi wraca wynik.
    record = tmp_path / "pid"
    code = (
        "import os, signal, subprocess\n"
        "child = subprocess.Popen(['sleep', '60'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
        f"open({str(record)!r}, 'w').write(str(child.pid))\n"
        "os.kill(os.getpid(), signal.SIGSEGV)\n"
    )

    code_returned, _, _ = sandbox.run(python(code), b"", timeout=20)

    assert code_returned == -signal.SIGSEGV
    assert wait_until_dead(int(record.read_text()))


def test_run_passes_input_and_returns_output_and_exit_code() -> None:
    code = "import sys; data = sys.stdin.buffer.read(); sys.stdout.buffer.write(data[::-1]); sys.stderr.write('uwaga'); sys.exit(3)"

    assert sandbox.run(python(code), b"abc", timeout=20) == (3, b"cba", b"uwaga")


def test_child_process_does_not_get_api_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "tajny-klucz-podpisu")
    monkeypatch.setenv("LLM_API_KEY", "tajny-klucz-modelu")
    monkeypatch.setenv("TESSDATA_PREFIX", "/dane/jezykowe")

    _, output, _ = sandbox.run(python("import json, os; print(json.dumps(dict(os.environ)))"), b"", timeout=20)

    environment = json.loads(output)
    assert "JWT_SECRET" not in environment
    assert "LLM_API_KEY" not in environment
    assert environment["TESSDATA_PREFIX"] == "/dane/jezykowe"
    assert environment["PATH"] == os.environ["PATH"]


def test_cpu_limit_ends_busy_process_and_is_inherited_by_children() -> None:
    limited = "from app.extract.sandbox import limit_resources; limit_resources(2**31, 1)\n"

    code, _, _ = sandbox.run(python(limited + "while True: pass"), b"", timeout=20)
    assert code == -signal.SIGXCPU

    # Tesseract startuje z procesu odczytu, więc dziedziczy jego limity.
    child = "import subprocess, sys; sys.exit(-subprocess.run([sys.executable, '-c', 'while True: pass']).returncode)"
    code, _, _ = sandbox.run(python(limited + child), b"", timeout=20)
    assert code == signal.SIGXCPU


def test_memory_limit_fails_large_allocation_and_is_inherited_by_children() -> None:
    limited = "from app.extract.sandbox import limit_resources; limit_resources(200 * 1024 * 1024, 30)\n"
    allocate = "try:\n    bytearray(400 * 1024 * 1024)\n    print('przydzielono')\nexcept MemoryError:\n    print('odmowa')"

    assert sandbox.run(python(limited + allocate), b"", timeout=20)[1].strip() == b"odmowa"
    child = f"import subprocess, sys; print(subprocess.run([sys.executable, '-c', {allocate!r}], capture_output=True).stdout.decode())"
    assert sandbox.run(python(limited + child), b"", timeout=20)[1].strip() == b"odmowa"
    assert sandbox.run(python(allocate), b"", timeout=20)[1].strip() == b"przydzielono"


@pytest.mark.parametrize(
    ("outcome", "error", "status", "level", "logged"),
    [
        ((None, b"", b""), ExtractionError, 400, logging.WARNING, "przerwany po"),
        ((-9, b"", b""), ExtractionError, 400, logging.WARNING, "sygnałem 9"),
        ((0, b'{"error": "unreadable", "reason": "czytnik odrzucil plik"}', b""), ExtractionError, 400, logging.INFO, "czytnik"),
        ((1, b'{"error": "crash", "reason": "KeyError w _fib (12)"}', b""), ExtractionError, 400, logging.WARNING, "KeyError w _fib"),
        ((0, b'{"error": "server", "reason": "brak biblioteki olefile"}', b""), AppError, 500, logging.ERROR, "olefile"),
        ((1, b"", b"No module named app.extract.worker"), AppError, 500, logging.ERROR, "No module named"),
        ((0, b'{"text": "bez pozostalych pol"}', b""), AppError, 500, logging.ERROR, "nie działa"),
        ((0, b"[1, 2]", b""), AppError, 500, logging.ERROR, "nie działa"),
    ],
    ids=["timeout", "signal", "unreadable", "crash", "server", "no-result", "incomplete-result", "wrong-result-type"],
)
def test_read_maps_child_outcome_to_error_and_log(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    outcome: tuple,
    error: type[AppError],
    status: int,
    level: int,
    logged: str,
) -> None:
    monkeypatch.setattr(sandbox, "run", lambda command, data, timeout: outcome)
    caplog.set_level(logging.DEBUG, logger="app.extract.sandbox")

    with pytest.raises(AppError) as exc_info:
        sandbox.read(b"dane", "doc", "pol")

    assert type(exc_info.value) is error
    assert exc_info.value.status_code == status
    assert exc_info.value.detail == (UNREADABLE if status == 400 else SERVER_ERROR)
    assert [(record.levelno, logged in record.getMessage()) for record in caplog.records] == [(level, True)]


def test_read_starts_worker_with_format_language_and_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def run(command: list[str], data: bytes, timeout: float) -> tuple[int, bytes, bytes]:
        calls.append((command, data, timeout))
        return 0, json.dumps({"text": "Wniosek", "ocr_used": True, "warnings": ["uwaga"]}).encode(), b""

    monkeypatch.setattr(sandbox, "run", run)
    monkeypatch.setattr(sandbox, "TIMEOUT_SECONDS", 7)
    monkeypatch.setattr(sandbox, "MEMORY_BYTES", 123456789)

    assert sandbox.read(b"dane", "png", "pol+eng") == Reading("Wniosek", True, ["uwaga"])
    assert calls == [([sys.executable, "-m", "app.extract.worker", "png", "pol+eng", "123456789", "7"], b"dane", 7)]


def run_worker(monkeypatch: pytest.MonkeyPatch, capsysbinary: pytest.CaptureFixture[bytes], data: bytes) -> dict:
    monkeypatch.setattr(worker, "limit_resources", lambda memory, cpu: None)
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(data)))
    worker.main(["doc", "pol", "1000", "5"])
    return json.loads(capsysbinary.readouterr().out)


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (ExtractionError(detail=UNREADABLE), {"error": "unreadable", "reason": "czytnik odrzucił plik"}),
        (SetupError(reason="Tesseract nie wczytał języka 'zzz'"), {"error": "server", "reason": "Tesseract nie wczytał języka 'zzz'"}),
        (ModuleNotFoundError("No module named 'olefile'", name="olefile"), {"error": "server", "reason": "brak biblioteki olefile"}),
        (MemoryError(), {"error": "unreadable", "reason": "limit pamięci"}),
    ],
    ids=["unreadable", "setup", "missing-library", "memory"],
)
def test_worker_reports_reader_failure_as_result(
    monkeypatch: pytest.MonkeyPatch, capsysbinary: pytest.CaptureFixture[bytes], failure: Exception, expected: dict
) -> None:
    def failing(data: bytes, ext: str, *, language: str) -> Reading:
        raise failure

    monkeypatch.setattr(readers, "read_document", failing)

    assert run_worker(monkeypatch, capsysbinary, b"dane") == expected


def test_worker_applies_limits_before_reading_and_reports_when_it_cannot(
    monkeypatch: pytest.MonkeyPatch, capsysbinary: pytest.CaptureFixture[bytes]
) -> None:
    order = []
    monkeypatch.setattr(worker, "limit_resources", lambda memory, cpu: order.append(("limity", memory, cpu)))
    monkeypatch.setattr(readers, "read_document", lambda data, ext, *, language: order.append((ext, language, data)) or Reading("x"))
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"dane")))

    worker.main(["doc", "pol", "1000", "5"])

    assert order == [("limity", 1000, 5), ("doc", "pol", b"dane")]
    assert json.loads(capsysbinary.readouterr().out) == {"text": "x", "ocr_used": False, "warnings": []}

    def refuse(memory: int, cpu: int) -> None:
        raise ValueError("current limit exceeds maximum limit")

    monkeypatch.setattr(worker, "limit_resources", refuse)
    worker.main(["doc", "pol", "1000", "5"])
    assert json.loads(capsysbinary.readouterr().out)["error"] == "server"


def test_worker_crash_report_names_error_type_and_place_without_document_content(
    capsysbinary: pytest.CaptureFixture[bytes],
) -> None:
    try:
        int("PESEL 44051401359")
    except ValueError as error:
        worker._report_crash(type(error), error, error.__traceback__)

    report = json.loads(capsysbinary.readouterr().out)
    assert report["error"] == "crash"
    assert report["reason"].startswith("ValueError w test_worker_crash_report")
    assert "44051401359" not in report["reason"]


def test_run_keeps_only_tail_of_child_errors_without_buffering_them() -> None:
    # Jak pypdf, który przy każdym rysowaniu zapętlonego formularza wypisuje ostrzeżenie: 30 MB na stderr.
    code = "import sys\nfor _ in range(30_000):\n    sys.stderr.write('x' * 999 + '\\n')\nsys.stderr.write('koniec')\nsys.stdout.write('wynik')"
    tracemalloc.start()
    try:
        code_returned, output, errors = sandbox.run(python(code), b"", timeout=60)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()

    assert (code_returned, output) == (0, b"wynik")
    assert errors.endswith(b"x\nkoniec")
    assert len(errors) == sandbox._LOG_TAIL
    assert peak < 5 * 1024 * 1024


def test_run_reads_whole_output_and_input_larger_than_pipe_buffer() -> None:
    data = bytes(range(256)) * 4096
    code = "import sys; data = sys.stdin.buffer.read(); sys.stderr.write('e' * 200_000); sys.stdout.buffer.write(data[::-1])"

    assert sandbox.run(python(code), data, timeout=20) == (0, data[::-1], b"e" * sandbox._LOG_TAIL)


def test_parallel_reads_wait_for_a_free_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    running, peak = 0, 0
    lock = threading.Lock()

    def run(command: list[str], data: bytes, timeout: float) -> tuple[int, bytes, bytes]:
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
        time.sleep(0.2)
        with lock:
            running -= 1
        return 0, json.dumps({"text": data.decode(), "ocr_used": False, "warnings": []}).encode(), b""

    monkeypatch.setattr(sandbox, "run", run)
    with ThreadPoolExecutor(max_workers=8) as pool:
        texts = list(pool.map(lambda number: sandbox.read(str(number).encode(), "pdf", "pol").text, range(8)))

    assert texts == [str(number) for number in range(8)]
    assert peak == 2
    assert sandbox.MAX_PARALLEL_READS == 2


def test_slot_is_released_after_failed_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sandbox, "run", lambda command, data, timeout: (None, b"", b""))

    for _ in range(sandbox.MAX_PARALLEL_READS + 1):
        with pytest.raises(ExtractionError):
            sandbox.read(b"dane", "pdf", "pol")

    monkeypatch.setattr(sandbox, "run", lambda command, data, timeout: (0, b'{"text": "x", "ocr_used": false, "warnings": []}', b""))
    assert sandbox.read(b"dane", "pdf", "pol").text == "x"


def test_read_that_waits_too_long_for_a_slot_is_server_error(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # Bez limitu czekania zalew ciężkich plików trzymałby wątki API minutami, a klienci dawno by odeszli.
    slots = threading.BoundedSemaphore(1)
    slots.acquire()
    monkeypatch.setattr(sandbox, "_SLOTS", slots)
    monkeypatch.setattr(sandbox, "QUEUE_SECONDS", 0.2)
    monkeypatch.setattr(sandbox, "run", lambda command, data, timeout: (0, b'{"text": "x", "ocr_used": false, "warnings": []}', b""))
    caplog.set_level(logging.WARNING, logger="app.extract.sandbox")
    errors: list[AppError] = []

    def attempt() -> None:
        try:
            sandbox.read(b"dane", "pdf", "pol")
        except AppError as error:
            errors.append(error)

    reader = threading.Thread(target=attempt, daemon=True)
    reader.start()
    reader.join(5)

    assert not reader.is_alive()
    assert [(type(error), error.status_code, error.detail) for error in errors] == [(AppError, 500, SERVER_ERROR)]
    assert "zajęte" in caplog.text
    slots.release()
    assert sandbox.read(b"dane", "pdf", "pol").text == "x"


def test_real_worker_does_not_write_library_warnings_to_stderr() -> None:
    # Strona rysuje formularz, który rysuje sam siebie: pypdf ostrzega o cyklu na każdej stronie.
    page = ("Wniosek o wydanie decyzji administracyjnej", [])
    data = scanned_pdf(*[page] * 20, through_form=True, form_redraws=1)
    command = [sys.executable, "-m", "app.extract.worker", "pdf", "pol", str(sandbox.MEMORY_BYTES), "20"]

    process = subprocess.run(command, input=data, capture_output=True, cwd=sandbox._ROOT, check=False)

    assert process.returncode == 0
    assert json.loads(process.stdout)["text"] == "\f".join([page[0]] * 20)
    assert process.stderr == b""


def test_pdf_form_drawing_itself_is_read_quickly_through_child_process(monkeypatch: pytest.MonkeyPatch) -> None:
    # 2000 wywołań samego siebie na każdym poziomie: bez strażnika cykli odczyt trwałby do limitu czasu.
    data = scanned_pdf(("Strona 1", []), through_form=True, form_redraws=2000)
    assert len(data) < 20_000
    monkeypatch.setattr(sandbox, "TIMEOUT_SECONDS", 20)
    before = time.monotonic()

    document = extract(data, "pdf")

    assert document.text == "Strona 1"
    assert time.monotonic() - before < 10


def test_setup_error_keeps_reason_after_copy_and_pickle() -> None:
    error = SetupError(reason="brak danych języka 'zzz'")

    for copied in (pickle.loads(pickle.dumps(error)), copy.copy(error)):
        assert type(copied) is SetupError
        assert (copied.reason, copied.status_code, copied.detail) == (error.reason, 500, SERVER_ERROR)


def test_unexpected_reader_error_in_real_child_is_contract_error(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    # Prawdziwy proces z czytnikiem, który rzuca nieprzewidziany wyjątek: odpowiedź 400 i ślad w logu.
    package = tmp_path / "app" / "extract"
    package.mkdir(parents=True)
    source = Path(sandbox.__file__).parent
    for name in ("worker.py", "sandbox.py", "common.py"):
        (package / name).write_text((source / name).read_text())
    (package / "__init__.py").write_text("")
    (package / "readers.py").write_text("def read_document(data, ext, *, language):\n    raise KeyError(data.decode())\n")
    for name in ("errors.py", "files.py", "config.py"):
        (tmp_path / "app" / name).write_text((source.parent / name).read_text())
    (tmp_path / "app" / "__init__.py").write_text("")
    command = [sys.executable, "-m", "app.extract.worker", "doc", "pol", str(sandbox.MEMORY_BYTES), "20"]
    process = subprocess.run(command, input=b"tajna tresc dokumentu", capture_output=True, cwd=tmp_path, check=False)

    assert process.returncode == 1
    assert json.loads(process.stdout) == {"error": "crash", "reason": "KeyError w read_document (2)"}
    assert b"tajna tresc" not in process.stdout
