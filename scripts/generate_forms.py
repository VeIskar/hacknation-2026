"""Buduje JSON-y COI i raport jakości dla formularzy do oddania.

Uruchomienie: backend/.venv/bin/python scripts/generate_forms.py --out ../generated-forms
Ustawienia modelu pochodzą ze środowiska procesu.
"""

import argparse
import html
import json
import logging
import os
import re
import sys
import tempfile
import time
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from traceback import walk_tb
from typing import NamedTuple

import httpx

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from app import analysis, extract, files, generator, lint
from app.config import Settings
from app.errors import AppError, ExtractionError, LLMUnavailable
from app.generator.coi import jsonata_string
from app.models import FormAnalysis

MATERIALS = REPO / "materialy"
DEFAULT_FORMS = (2, 3, 4, 6, 7, 8, 9)
DEFAULT_PREFER = "pdf,docx,doc,jpg,png"
COI_DICTIONARIES = frozenset({
    "Województwo", "Powiat", "Gmina", "Miejscowość", "Kraje", "Numery kierunkowe",
    "TERYT_4G_DOWODOWY", "TERYT_DOWODOWY",
})
APPLICANT_PATTERNS = {
    "PESEL": r"pesel", "NIP": r"\bnip\b", "REGON": r"regon", "KRS": r"\bkrs\b",
    "pełnomocnik": r"pełnomocn", "telefon": r"telefon|\btel\b", "e-mail": r"e-?mail",
    "korespondencja": r"korespondenc", "siedziba": r"siedzib",
}
WORD = re.compile(r"[^\W\d_]+")
QUERY_TOKEN = re.compile(r"""'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*"|\b(and|or)\b""", re.DOTALL)
log = logging.getLogger(__name__)


class _Input(NamedTuple):
    name: str
    path: Path
    format: str


def _selected_forms(value: str | None, include_five: bool) -> tuple[int, ...]:
    allowed = tuple(sorted((*DEFAULT_FORMS, 5))) if include_five else DEFAULT_FORMS
    if value is None:
        return allowed
    try:
        selected = tuple(dict.fromkeys(int(part) for part in value.split(",")))
    except ValueError:
        raise ValueError("--forms wymaga listy numerów oddzielonych przecinkami.") from None
    if set(selected) - set(allowed):
        raise ValueError("Folder 1 jest wykluczony. Wybierz 2, 3, 4, 6, 7, 8, 9 lub 5 z --include-5.")
    return selected


def _formats(value: str) -> tuple[str, ...]:
    requested = [item.strip().lower().lstrip(".") for item in value.split(",")]
    formats = tuple(dict.fromkeys(files.ALIASES.get(part, part) for part in requested))
    if set(formats) - files.SUPPORTED:
        raise ValueError("--prefer wymaga listy obsługiwanych formatów oddzielonych przecinkami.")
    return formats


def _control_path(path: Path) -> bool:
    # Katalogi materiałów mogą być dowiązaniami do oryginalnego archiwum COI.
    return any(part in {"1", "1."} or part.startswith("1. ") for part in path.parts)


def _env_file(path: Path) -> bool:
    return path.name == ".env" or path.name.startswith(".env.")


def _output_directory(path: Path) -> Path:
    out = path.expanduser().resolve()
    if out.is_relative_to(REPO) or any((parent / ".git").exists() for parent in (out, *out.parents)):
        raise ValueError("Katalog wyjściowy musi leżeć poza repozytorium.")
    if _control_path(out):
        raise ValueError("Folder 1 nie może być katalogiem wyjściowym.")
    return out


def _candidates(number: int, prefer: tuple[str, ...]) -> list[_Input]:
    by_format = {}
    for folder in sorted(MATERIALS.glob(f"{number}. *")):
        directory = folder.resolve()
        if _control_path(directory):
            raise ValueError("Dowiązanie do folderu 1 jest niedozwolone.")
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir(), key=lambda item: (item.name.casefold(), item.name)):
            suffix = path.suffix[1:].lower()
            format_name = files.ALIASES.get(suffix, suffix)
            if format_name not in prefer or "wizualizacja" in path.name.casefold():
                continue
            resolved = path.resolve()
            if (
                resolved.is_relative_to(directory) and not _control_path(resolved)
                and not _env_file(resolved) and resolved.is_file()
            ):
                by_format.setdefault(format_name, _Input(path.name, resolved, format_name))
    return [by_format[format_name] for format_name in prefer if format_name in by_format]


def _make_redactor(key: str) -> Callable[[str], str]:
    if not key:
        return str
    forms = {
        key, html.escape(key, quote=False), html.escape(key), jsonata_string(key, "'")[1:-1],
        json.dumps(key, ensure_ascii=False)[1:-1], json.dumps(key, ensure_ascii=True)[1:-1],
    }
    secret = re.compile("|".join(re.escape(form) for form in sorted(forms, key=len, reverse=True)))
    return lambda text: secret.sub("***", text)


def _redact_data(data, redact: Callable[[str], str]):
    if isinstance(data, str):
        return redact(data)
    if isinstance(data, list):
        return [_redact_data(item, redact) for item in data]
    if isinstance(data, dict):
        return {
            redact(key) if isinstance(key, str) else key: _redact_data(value, redact)
            for key, value in data.items()
        }
    return data


@contextmanager
def _safe_logs(redact: Callable[[str], str]) -> Iterator[None]:
    factory = logging.getLogRecordFactory()

    def safe_record(*args, **kwargs) -> logging.LogRecord:
        record = factory(*args, **kwargs)
        record.msg, record.args = redact(record.getMessage()), ()
        if record.exc_info is not None:
            record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        return record

    logging.setLogRecordFactory(safe_record)
    try:
        yield
    finally:
        logging.setLogRecordFactory(factory)


def _objects(value: object) -> Iterator[dict]:
    if isinstance(value, list):
        yield from (item for item in value if isinstance(item, dict))


class _Telemetry(httpx.BaseTransport):
    def __init__(self, inner: httpx.BaseTransport, redact: Callable[[str], str]):
        self.inner = inner
        self.redact = redact
        self.requests: list[dict] = []

    def close(self) -> None:
        """K3 zamyka klienta po każdej próbie. Transport bazowy zamyka skrypt."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        entry = {"status_code": None, "prompt_tokens": None, "completion_tokens": None, "finish_reason": None}
        self.requests.append(entry)
        started = time.perf_counter()
        response = None
        try:
            response = self.inner.handle_request(request)
            entry["status_code"] = response.status_code
            response.read()
        except Exception as error:
            entry["error_class"] = type(error).__name__
            if response is not None:
                response.close()
            raise
        finally:
            entry["elapsed_s"] = time.perf_counter() - started

        try:
            payload = response.json()
        except (ValueError, RecursionError):
            payload = None
        if isinstance(payload, dict):
            usage = payload.get("usage")
            if isinstance(usage, dict):
                for key in ("prompt_tokens", "completion_tokens"):
                    value = usage.get(key)
                    if type(value) is int:
                        entry[key] = value
            first = next(_objects(payload.get("choices")), {})
            if isinstance(reason := first.get("finish_reason"), str):
                entry["finish_reason"] = self.redact(reason)
        if not response.is_success:
            entry["body_excerpt"] = self.redact(response.text)[:300]
        return response


@contextmanager
def _measure(timings: dict[str, float], name: str) -> Iterator[None]:
    started = time.perf_counter()
    try:
        yield
    finally:
        timings[name] += time.perf_counter() - started


def _coi_stats(form: object, analyzed: FormAnalysis) -> dict:
    sections = [section for page in analyzed.subject_pages for section in page.sections]
    show = {"total": 0, "or": 0, "and": 0, "sections": 0}
    validators: Counter[str] = Counter()
    dictionaries: Counter[str] = Counter()
    tabs = form.get("tabs") if isinstance(form, dict) else None
    for page in _objects(tabs):
        for question in _objects(page.get("questions")):
            section = question.get("field")
            if not isinstance(section, dict):
                continue
            fields = [section, *(cell.get("field") for cell in _objects(section.get("repeatingSectionGrid")))]
            for item in fields:
                if not isinstance(item, dict):
                    continue
                if isinstance(dictionary := item.get("dictionaryName"), str):
                    dictionaries[dictionary] += 1
                if isinstance(validation := item.get("validation"), list):
                    validators.update(rule for rule in validation if isinstance(rule, str))
                for state in _objects(item.get("states")):
                    if state.get("type") != "SHOW":
                        continue
                    query = state.get("query")
                    operators = (
                        {match[1] for match in QUERY_TOKEN.finditer(query)} if isinstance(query, str) else set()
                    )
                    show["total"] += 1
                    show["or"] += "or" in operators
                    show["and"] += "and" in operators
                    show["sections"] += item is section
    return {
        "subject": {
            "pages": len(analyzed.subject_pages), "sections": len(sections),
            "fields": sum(len(section.fields) for section in sections),
        },
        "show": show,
        "validators": dict(sorted(validators.items())),
        "dictionaries": dict(sorted(dictionaries.items())),
    }


def _normalized(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def _prefixes(text: str) -> set[str]:
    return {word[:5] for word in WORD.findall(text) if len(word) >= 4 and word.isalpha()}


def _quality(analyzed: FormAnalysis, text: str, dictionaries: dict[str, int]) -> dict:
    normalized = _normalized(text)
    words = _prefixes(normalized)
    subject = [field for page in analyzed.subject_pages for section in page.sections for field in section.fields]
    unsupported_labels = [field.label for field in subject if not words & _prefixes(_normalized(field.label))]
    unsupported_options = [
        option for field in subject for option in field.options if not words & _prefixes(_normalized(option))
    ]
    total = len(subject) + sum(len(field.options) for field in subject)
    matched = total - len(unsupported_labels) - len(unsupported_options)
    applicant = analyzed.applicant
    enabled = {
        "PESEL": applicant.applicant_pesel, **dict.fromkeys(applicant.entity_ids, True),
        "pełnomocnik": applicant.proxy, "telefon": "PHONE" in applicant.contact, "e-mail": "EMAIL" in applicant.contact,
        "korespondencja": applicant.correspondence_address, "siedziba": applicant.entity_address,
    }
    return {
        "text_support": {
            "matched": matched, "total": total, "percent": 100 * matched / total if total else None,
            "unsupported_labels": unsupported_labels, "unsupported_options": unsupported_options,
        },
        "applicant_without_evidence": [
            name for name, pattern in APPLICANT_PATTERNS.items()
            if enabled.get(name) and not re.search(pattern, normalized)
        ],
        "unexpected_dictionaries": sorted(set(dictionaries) - COI_DICTIONARIES),
    }


def _failure(error: Exception, stage: str, requests: list[dict]) -> dict:
    reason = "błąd odczytu" if isinstance(error, ExtractionError) or stage == "read" else "błąd przetwarzania"
    if isinstance(error, LLMUnavailable):
        # K3 używa 503 również dla braku atrapy. Zerowy ruch sam nie oznacza braku budżetu.
        budget = not requests and any(
            frame.f_code is analysis._ensure_fits.__code__ for frame, _ in walk_tb(error.__traceback__)
        )
        reason = "budżet K3 (do K3.1)" if budget else "błąd modelu"
    return {
        "class": type(error).__name__, "stage": stage, "reason": reason, "detail": str(error),
        "status_code": error.status_code if isinstance(error, AppError) else None,
    }


def _write(path: Path, text: str) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", errors="replace", dir=path.parent, delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(text)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _write_json(path: Path, data) -> None:
    _write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def _process_form(
    number: int, prefer: tuple[str, ...], out: Path, settings: Settings, telemetry: _Telemetry,
) -> dict:
    name = f"F{number}"
    timings = dict.fromkeys(("extract", "analyze", "build_lint", "e2e"), 0.0)
    row = {
        "form": name, "status": "błąd", "file": None, "format": None, "inputs": [],
        "timings_s": timings, "requests": telemetry.requests, "error": None,
    }
    stage = "selection"
    with _measure(timings, "e2e"):
        try:
            candidates = _candidates(number, prefer)
            if not candidates:
                raise FileNotFoundError("Brak pliku w wybranych formatach.")
            for candidate in candidates:
                row["file"], row["format"] = candidate.name, candidate.format
                source = {"file": candidate.name, "format": candidate.format, "error": None}
                row["inputs"].append(source)
                try:
                    stage = "read"
                    with candidate.path.open("rb") as stream:
                        data = stream.read(settings.max_file_bytes + 1)
                    stage = "validate_upload"
                    ext = files.validate_upload(candidate.name, data, settings.max_file_bytes)
                    row["format"] = source["format"] = ext
                    stage = "extract"
                    with _measure(timings, "extract"):
                        document = extract.extract(data, ext)
                    stage = "analyze"
                    with _measure(timings, "analyze"):
                        analyzed = analysis.analyze(document, settings=settings, transport=telemetry)
                except ExtractionError as error:
                    source["error"] = _failure(error, stage, telemetry.requests)
                    if candidate == candidates[-1]:
                        raise
                    continue
                break

            with _measure(timings, "build_lint"):
                stage = "build_form"
                form = generator.build_form(analyzed)
                stage = "lint"
                errors = lint.check(form)
            row["lint"] = {"count": len(errors), "first_errors": errors[:5]}
            stage = "write"
            _write_json(out / f"{name}.analysis.json", _redact_data(analyzed.model_dump(mode="json"), telemetry.redact))
            _write_json(out / f"{name}.coi.json", _redact_data(form, telemetry.redact))
            stage = "quality"
            row["stats"] = _coi_stats(form, analyzed)
            row["quality"] = _quality(analyzed, document.text, row["stats"]["dictionaries"])
            row["status"] = "OK"
        except Exception as error:
            log.debug("Błąd formularza %s na etapie %s", name, stage, exc_info=True)
            row["error"] = _failure(error, stage, telemetry.requests)
            if stage in {"read", "validate_upload", "extract", "analyze"}:
                row["inputs"][-1]["error"] = row["error"]
    row["attempts"] = len(telemetry.requests)
    return row


def _display(value: object) -> str:
    return "—" if value is None else html.escape(" ".join(str(value).splitlines())).replace("|", r"\|")


def _counts(values: dict[str, int]) -> str:
    return ", ".join(f"{_display(name)} × {number}" for name, number in values.items()) or "—"


def _markdown(rows: list[dict]) -> str:
    lines = [
        "# Raport generowania COI", "",
        "Oparcie w tekście i decyzje wnioskodawcy bez wykrytej przesłanki są przybliżeniami.", "",
        "| Formularz | Wynik | E2E (s) | Próby | Lint | Oparcie (%) | Bez przesłanki | SHOW or | SHOW and | SHOW sekcje |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        quality = row.get("quality", {})
        support = quality.get("text_support", {}).get("percent")
        show = row.get("stats", {}).get("show", {})
        values = (
            row["form"], row["status"], f"{row['timings_s']['e2e']:.3f}", row["attempts"],
            row.get("lint", {}).get("count"), f"{support:.1f}" if support is not None else None,
            len(quality["applicant_without_evidence"]) if quality else None,
            show.get("or"), show.get("and"), show.get("sections"),
        )
        lines.append("| " + " | ".join(map(_display, values)) + " |")

    for row in rows:
        timings = row["timings_s"]
        lines += [
            "", f"## {row['form']}", "",
            f"- **Plik i format** {_display(row['file'])} / {_display(row['format'])}",
            (
                f"- **Czasy (s)** extract {timings['extract']:.3f} / analyze {timings['analyze']:.3f}"
                f" / build+lint {timings['build_lint']:.3f} / e2e {timings['e2e']:.3f}"
            ),
            f"- **Próby** {row['attempts']}",
        ]
        for index, request in enumerate(row["requests"], 1):
            lines.append(
                f"  - {index}. HTTP {_display(request['status_code'])}, {request['elapsed_s']:.3f} s, "
                f"finish_reason {_display(request['finish_reason'])}, "
                f"tokeny {_display(request['prompt_tokens'])}/{_display(request['completion_tokens'])}"
            )
        for source in row["inputs"]:
            if error := source["error"]:
                lines.append(
                    f"- **Plik odrzucony** {_display(source['file'])} / {_display(source['format'])}"
                    f" / {_display(error['class'])} / {_display(error['stage'])}"
                )
        if error := row["error"]:
            lines.append(
                f"- **Błąd** {_display(error['reason'])} / {_display(error['class'])}"
                f" / {_display(error['stage'])} / {_display(error['status_code'])}"
            )
        if stats := row.get("stats"):
            subject, show, quality = stats["subject"], stats["show"], row["quality"]
            lines += [
                f"- **Lint** {row['lint']['count']}",
                f"- **Przedmiot** strony {subject['pages']} / sekcje {subject['sections']} / pola {subject['fields']}",
                f"- **SHOW** razem {show['total']} / or {show['or']} / and {show['and']} / sekcje {show['sections']}",
                f"- **Walidatory** {_counts(stats['validators'])}",
                f"- **Słowniki** {_counts(stats['dictionaries'])}",
            ]
            if unknown := quality["unexpected_dictionaries"]:
                lines.append("- **Błąd słownika** " + ", ".join(map(_display, unknown)))
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None, *, transport: httpx.BaseTransport | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generuj JSON-y COI do oddania i raport jakości.")
    parser.add_argument("--forms", help="Numery formularzy oddzielone przecinkami")
    parser.add_argument("--include-5", action="store_true", help="Dopuść folder 5")
    parser.add_argument("--prefer", default=DEFAULT_PREFER, help=f"Kolejność formatów (domyślnie {DEFAULT_PREFER})")
    parser.add_argument("--out", type=Path, default=REPO.parent / "generated-forms", help="Katalog poza repozytorium")
    args = parser.parse_args(argv)
    redact = _make_redactor(os.environ.get("LLM_API_KEY", "").strip())
    try:
        numbers = _selected_forms(args.forms, args.include_5)
        prefer = _formats(args.prefer)
        out = _output_directory(args.out)
        settings = Settings.from_env()
        if settings.llm_fixture:
            fixture = Path(settings.llm_fixture)
            resolved = fixture.resolve()
            if _control_path(fixture) or _control_path(resolved) or _env_file(fixture) or _env_file(resolved):
                raise ValueError("LLM_FIXTURE musi wskazywać plik poza folderem 1 i plikami .env.")
        out.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError) as error:
        parser.error(redact(str(error)))

    try:
        inner = transport if transport is not None else httpx.HTTPTransport(trust_env=False)
        with _safe_logs(redact), inner:
            rows = [
                _process_form(number, prefer, out, settings, _Telemetry(inner, redact))
                for number in numbers
            ]
        public_rows = _redact_data(rows, redact)
        _write_json(out / "report.json", {"forms": public_rows})
        _write(out / "report.md", _markdown(public_rows))
    except OSError as error:
        print(redact(f"Błąd przygotowania raportu ({type(error).__name__}). {error}"), file=sys.stderr)
        return 1
    print(redact(f"Raport zapisano w {out}"))
    return int(any(row["error"] is not None for row in rows))


if __name__ == "__main__":
    raise SystemExit(main())
