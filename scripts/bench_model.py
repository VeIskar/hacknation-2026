"""K1: pomiar modelu na formularzu z folderu 5 (DELEGACJA.md, rozdz. 3 i 4).

Mierzy czas, tokeny, poprawność JSON, FormAnalysis.model_validate i zgodność pól przedmiotu
z backend/tests/fixtures/fields.json (nasz opis wniosku z folderu 5).
Folder 1 to zbiór kontrolny (DECISIONS.md, D5): skrypt odmawia jego plików i ich kopii (sha256).
Raport zawiera tylko liczby. Surowe odpowiedzi modelu zapisuje wyłącznie --raw-dir,
i tylko w materialy/ albo poza repozytorium, czyli poza gitem.

Uruchomienie (Ollama na 127.0.0.1:11434):
    backend/.venv/bin/python scripts/bench_model.py --runs 3
    backend/.venv/bin/python scripts/bench_model.py --input materialy/5.*/*.JPG
Ścieżkę podawaj globem: nazwy katalogów w materiałach są w Unicode NFD, więc przepisana ręcznie nie pasuje.
"""

import argparse
import hashlib
import io
import json
import os
import re
import statistics
import sys
import unicodedata
import zipfile
from dataclasses import replace
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import httpx

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from pydantic import ValidationError

from app.config import Settings
from app.errors import LLMUnavailable
from app.llm import ChatResult, answer_token_limit, chat_json, image_part, provider
from app.models import FormAnalysis

MATERIALS = REPO / "materialy"
REFERENCE = REPO / "backend" / "tests" / "fixtures" / "fields.json"
IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
# Etykiety uznajemy za to samo pole od tego podobieństwa. Dobrane ręcznie na parach
# w rodzaju „Numer rachunku” / „Numer rachunku bankowego”, nie z danych kontrolnych.
LABEL_MATCH = 0.75
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

SYSTEM_PROMPT = """Analizujesz papierowy wniosek urzędowy. Opisz jego treść jako JSON zgodny ze schematem.
Zasady:
- Etykiety pól prostym językiem, w drugiej osobie, bez numerów przepisów.
- Miejsce do wpisania po tekście to pole. Kwota lub liczba: NUMBER. Data: DATEPICKER.
  Uzasadnienie lub opis: TEXTAREA. Reszta: TEXT_FIELD.
- Wybór typu „1) … 2) …” albo kwadraty do zaznaczenia: RADIO, gdy jeden wybór, CHECKBOX, gdy wiele.
  Dane dopisywane przy opcji to osobne pole z show_if tej opcji.
- Załączniki: sekcja z opisem i pole FILE_UPLOADER dla każdego załącznika.
- Pomiń dane i adres wnioskodawcy, kontakt, miejscowość, datę, podpis, klauzulę RODO i pola dla urzędu.
- Grupuj pola w sekcje tematyczne.
Zwróć wyłącznie JSON."""

WARMUP_SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}


def default_input() -> Path:
    candidates = [p for p in MATERIALS.glob("5. */*.docx") if "wizualizacja" not in p.name.lower()]
    if not candidates:
        raise SystemExit(f"Brak DOCX z folderu 5 w {MATERIALS}. Rozpakuj materiały COI (DELEGACJA.md, rozdz. 6).")
    return min(candidates)


def check_input(path: Path) -> None:
    resolved = path.resolve()
    if resolved.is_relative_to(MATERIALS.resolve()):
        folder = resolved.relative_to(MATERIALS.resolve()).parts[0]
        if folder.startswith("1."):
            raise SystemExit("Folder 1 to zbiór kontrolny (D5): nie wysyłamy go do modelu.")
    # Materiały COI mają kopie plików z folderu 1 w innych katalogach, więc liczy się treść, nie ścieżka.
    if resolved.is_file():
        control = {_sha256(p) for folder in MATERIALS.glob("1.*") for p in folder.rglob("*") if p.is_file()}
        if _sha256(resolved) in control:
            raise SystemExit(f"{path.name}: ta sama treść co plik z folderu 1 (zbiór kontrolny, D5). Nie wysyłamy go do modelu.")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_output_dir(path: Path) -> None:
    """Surowe odpowiedzi nie mogą trafić do gita: tylko materialy/ (w .gitignore) albo poza repo."""
    resolved = path.resolve()
    if resolved.is_relative_to(REPO) and not resolved.is_relative_to(MATERIALS.resolve()):
        raise SystemExit(f"{path}: zapis w repozytorium tylko pod materialy/ (poza gitem).")


def docx_text(data: bytes) -> str:
    """Tekst akapitów i tabel w kolejności dokumentu. Zastępstwo do czasu extract z K2."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))

    def paragraph(node: ElementTree.Element) -> str:
        return "".join(t.text or "" for t in node.iter(f"{W}t"))

    body = root.find(f"{W}body")
    lines: list[str] = []
    for block in body if body is not None else []:
        if block.tag == f"{W}p":
            lines.append(paragraph(block))
        elif block.tag == f"{W}tbl":
            for row in block.iter(f"{W}tr"):
                cells = [" ".join(paragraph(p) for p in cell.iter(f"{W}p")).strip() for cell in row.iter(f"{W}tc")]
                lines.append(" | ".join(cells))
    return "\n".join(line for line in lines if line.strip())


def build_messages(path: Path) -> list[dict[str, Any]]:
    schema = json.dumps(FormAnalysis.model_json_schema(), ensure_ascii=False)
    system = {"role": "system", "content": f"{SYSTEM_PROMPT}\n\nSchemat JSON:\n{schema}"}
    suffix = path.suffix.lower()
    if suffix in IMAGE_TYPES:
        parts = [{"type": "text", "text": "Formularz jest na obrazie."}, image_part(path.read_bytes(), IMAGE_TYPES[suffix])]
        return [system, {"role": "user", "content": parts}]
    if suffix == ".docx":
        text = docx_text(path.read_bytes())
    elif suffix == ".txt":
        text = path.read_text(encoding="utf-8")
    else:
        raise SystemExit(f"{path.name}: obsługiwane .docx, .txt, .jpg, .png. Pozostałe formaty czyta extract (K2).")
    return [system, {"role": "user", "content": f"Tekst formularza:\n\n{text}"}]


def _normalize(label: str) -> str:
    text = unicodedata.normalize("NFKC", label).casefold()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text)).strip()


def label_similarity(a: str, b: str) -> float:
    x, y = _normalize(a), _normalize(b)
    if not x or not y:
        return 0.0
    if x in y or y in x:
        return 1.0
    return SequenceMatcher(None, x, y).ratio()


def subject_fields(analysis: Any) -> list[tuple[str, str, bool]]:
    """(etykieta, typ, ma show_if) z dowolnego JSON-a, także takiego, który nie przeszedł walidacji."""
    found: list[tuple[str, str, bool]] = []
    pages = analysis.get("subject_pages") if isinstance(analysis, dict) else None
    for page in pages if isinstance(pages, list) else []:
        sections = page.get("sections") if isinstance(page, dict) else None
        for section in sections if isinstance(sections, list) else []:
            fields = section.get("fields") if isinstance(section, dict) else None
            for field in fields if isinstance(fields, list) else []:
                if isinstance(field, dict) and isinstance(field.get("label"), str):
                    found.append((field["label"], str(field.get("type", "")), bool(field.get("show_if"))))
    return found


def field_quality(predicted: Any, reference: dict[str, Any]) -> dict[str, Any]:
    ours, theirs = subject_fields(predicted), subject_fields(reference)
    scored = ((label_similarity(p[0], r[0]), i, j) for i, p in enumerate(ours) for j, r in enumerate(theirs))
    pairs = sorted((s for s in scored if s[0] >= LABEL_MATCH), reverse=True)
    used_pred: set[int] = set()
    matched: dict[int, int] = {}
    for _, i, j in pairs:
        if i not in used_pred and j not in matched:
            used_pred.add(i)
            matched[j] = i
    same_type = sum(1 for j, i in matched.items() if ours[i][1] == theirs[j][1])
    return {
        "fields_predicted": len(ours),
        "fields_reference": len(theirs),
        "fields_matched": len(matched),
        "recall": round(len(matched) / len(theirs), 3) if theirs else None,
        "precision": round(len(matched) / len(ours), 3) if ours else None,
        "type_agreement": round(same_type / len(matched), 3) if matched else None,
        "show_if_predicted": sum(1 for f in ours if f[2]),
        "show_if_reference": sum(1 for f in theirs if f[2]),
        "missing_reference_labels": [theirs[j][0] for j in range(len(theirs)) if j not in matched],
        "applicants_ok": isinstance(predicted, dict)
        and "applicants" in predicted
        and predicted["applicants"] == reference.get("applicants"),
        "addressee_type_ok": isinstance(predicted, dict)
        and isinstance(predicted.get("addressee"), dict)
        and predicted["addressee"].get("type") == reference.get("addressee", {}).get("type"),
    }


def evaluate(content: str, reference: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"json_ok": False, "valid": False, "validation_errors": None, "error_types": []}
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return result
    result["json_ok"] = True
    try:
        FormAnalysis.model_validate(parsed)
        result["valid"] = True
        result["validation_errors"] = 0
    except ValidationError as exc:
        errors = exc.errors(include_input=False, include_url=False)
        result["validation_errors"] = len(errors)
        # Tylko miejsce i rodzaj błędu: komunikat może cytować treść formularza.
        result["error_types"] = [f"{'.'.join(map(str, e['loc']))}: {e['type']}" for e in errors[:5]]
    result.update(field_quality(parsed, reference))
    return result


def ollama_version(base_url: str, transport: httpx.BaseTransport | None) -> str | None:
    root = base_url.rstrip("/").removesuffix("/v1")
    try:
        with httpx.Client(timeout=5, transport=transport, trust_env=False) as client:
            return client.get(f"{root}/api/version").json().get("version")
    except (httpx.HTTPError, ValueError, AttributeError):
        return None


def _summary(runs: list[dict[str, Any]]) -> dict[str, Any]:
    times = [r["elapsed_s"] for r in runs]
    recalls = [r["recall"] for r in runs if r.get("recall") is not None]
    precisions = [r["precision"] for r in runs if r.get("precision") is not None]
    return {
        "runs": len(runs),
        "json_ok": sum(r["json_ok"] for r in runs),
        "valid": sum(r["valid"] for r in runs),
        "thinking_seen": sum(r["reasoning_chars"] > 0 for r in runs),
        "time_median_s": round(statistics.median(times), 1),
        "time_min_s": round(min(times), 1),
        "time_max_s": round(max(times), 1),
        "recall_mean": round(statistics.mean(recalls), 3) if recalls else None,
        "precision_mean": round(statistics.mean(precisions), 3) if precisions else None,
    }


def run_benchmark(
    inputs: list[Path],
    models: list[str] | None,
    *,
    runs: int,
    base_url: str | None = None,
    timeout_s: float | None = None,
    max_tokens: int | None = None,
    raw_dir: Path | None = None,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    for path in inputs:
        check_input(path)
    if raw_dir is not None:
        check_output_dir(raw_dir)
        raw_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings.from_env()
    llm_provider = provider(settings)
    if timeout_s is None:
        timeout_s = settings.llm_timeout_s
        if llm_provider == "ollama" and not os.environ.get("LLM_TIMEOUT_S", "").strip():
            timeout_s = 900.0  # Dotychczasowy domyślny czas pomiaru lokalnego na CPU.
    settings = replace(settings, llm_base_url=base_url or settings.llm_base_url, llm_timeout_s=timeout_s)
    if max_tokens is None:
        max_tokens = answer_token_limit(settings)
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    report: dict[str, Any] = {
        "started": datetime.now(UTC).isoformat(timespec="seconds"),
        "base_url": settings.llm_base_url,
        "ollama_version": ollama_version(settings.llm_base_url, transport) if llm_provider == "ollama" else None,
        "max_tokens": max_tokens,
        "models": {},
    }
    for model in models or [settings.llm_model]:
        model_settings = replace(settings, llm_model=model)
        entry: dict[str, Any] = {"inputs": {}}
        report["models"][model] = entry
        try:
            warmup = chat_json(
                [{"role": "user", "content": 'Odpowiedz {"ok": true}.'}],
                WARMUP_SCHEMA,
                schema_name="Warmup",
                max_tokens=16,
                settings=model_settings,
                transport=transport,
            )
        except LLMUnavailable as exc:
            entry["error"] = f"model niedostępny: {exc.__cause__!r}"
            continue
        entry["load_and_warmup_s"] = round(warmup.elapsed_s, 1)
        for path in inputs:
            messages = build_messages(path)
            results: list[dict[str, Any]] = []
            for run in range(1, runs + 1):
                try:
                    answer: ChatResult = chat_json(
                        messages, FormAnalysis.model_json_schema(), max_tokens=max_tokens,
                        settings=model_settings, transport=transport,
                    )
                except LLMUnavailable as exc:
                    results.append({"run": run, "error": repr(exc.__cause__)})
                    continue
                row = {
                    "run": run,
                    "elapsed_s": round(answer.elapsed_s, 1),
                    "prompt_tokens": answer.prompt_tokens,
                    "completion_tokens": answer.completion_tokens,
                    "reasoning_chars": len(answer.reasoning),
                    "finish_reason": answer.finish_reason,
                }
                row.update(evaluate(answer.content, reference))
                results.append(row)
                if raw_dir is not None:
                    stem = re.sub(r"[^\w.-]+", "_", f"{model}_{path.stem}_{run}")
                    raw = {"model": model, "input": path.name, "run": run, "content": answer.content, "reasoning": answer.reasoning}
                    (raw_dir / f"{stem}.json").write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
            completed = [r for r in results if "error" not in r]
            entry["inputs"][path.name] = {
                "summary": _summary(completed) if completed else {"runs": 0, "errors": len(results)},
                "runs": results,
            }
    return report


def main(argv: list[str] | None = None, transport: httpx.BaseTransport | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, action="append", help="plik formularza; domyślnie DOCX z folderu 5")
    parser.add_argument("--model", action="append", help="model; domyślnie LLM_MODEL lub qwen3.5:4b")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--base-url", help="domyślnie LLM_BASE_URL lub http://localhost:11434/v1")
    parser.add_argument("--timeout", type=float, help="sekundy na zapytanie; domyślnie LLM_TIMEOUT_S (Ollama bez env: 900)")
    parser.add_argument("--max-tokens", type=int, help="domyślnie LLM_MAX_TOKENS lub limit dostawcy")
    parser.add_argument("--raw-dir", type=Path, help="zapis surowych odpowiedzi: tylko materialy/ albo poza repo")
    parser.add_argument("--report", type=Path, help="raport JSON z liczbami: tylko materialy/ albo poza repo")
    args = parser.parse_args(argv)

    if args.report is not None:
        check_output_dir(args.report.parent)
    report = run_benchmark(
        args.input or [default_input()],
        args.model,
        runs=args.runs,
        base_url=args.base_url,
        timeout_s=args.timeout,
        max_tokens=args.max_tokens,
        raw_dir=args.raw_dir,
        transport=transport,
    )
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8")
    print(text)
    unavailable = [m for m, e in report["models"].items() if "error" in e]
    if unavailable:
        print(f"Brak pomiaru dla: {', '.join(unavailable)} (serwer {report['base_url']} nie odpowiada).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
