"""Zapisuje propozycje słowników w katalogu wyników E1.

Uruchomienie: backend/.venv/bin/python scripts/propose_dictionaries.py --results ../generated-forms
"""

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import extract, quality
from app.errors import AppError
from app.generator.coi import iter_fields
from generate_forms import (
    DEFAULT_FORMS,
    MATERIALS,
    _control_path,
    _env_file,
    _output_directory,
    _write_json,
)

_CHOICE_TYPES = {"SELECT", "RADIO", "CHECKBOX"}
_CATALOG = quality.COI_DICTIONARIES - {"TERYT_DOWODOWY", "TERYT_4G_DOWODOWY"}
_CHOICE_PROMPT = re.compile(r"^(wybierz|wskaż|podaj) ")
_CATALOG_TOPIC = re.compile(
    r"^(kraje|wojewodztw[oa]|powiat(?:u|y)?|gmin[ay]|miejscowosc[i]?|"
    r"numer(?:y)? kierunkow[ey]|kod kierunkowy)\b"
)
_MARKED_OPTION = re.compile(
    r"^\s*(?:[□■○●\u2610-\u2612•◦\u25aa\u25ab\u2713\u2714*–—\-\uf000-\uf8ff]|\d+[.)]|[IVXLCDM]+\.)\s+(\S.*)$"
)
_WRITE_IN = re.compile(r"^((?:inny|inna|inne)\b.*?)\s*[.…_]{3,}$", re.IGNORECASE)
_GENERIC = {"tak", "nie", "nie dotyczy", "inny", "inna", "inne"}


class SourceList(NamedTuple):
    part: int
    line: int
    values: dict[str, str]
    write_ins: set[str]
    closed: bool


def _key(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def _write_in_keys(value: str) -> set[str]:
    match = _WRITE_IN.fullmatch(value)
    return {_key(value), _key(match[1])} if match else set()


def _source_lists(text: str) -> dict[str, list[SourceList]]:
    lists = defaultdict(list)
    for part, page in enumerate(text.split("\f"), 1):
        lines = [(number, line.strip()) for number, line in enumerate(page.splitlines(), 1) if line.strip()]
        for index, (line_number, heading) in enumerate(lines):
            if not heading.endswith(":"):
                continue
            values = {}
            write_ins = set()
            end = index + 1
            while end < len(lines) and (match := _MARKED_OPTION.match(lines[end][1])):
                value = " ".join(match[1].split())
                if keys := _write_in_keys(value):
                    write_ins.update(keys)
                else:
                    values.setdefault(_key(value), value)
                end += 1
            if end == index + 1:
                continue
            for length in (1, 2):
                following = " ".join(value for _, value in lines[end:end + length])
                if keys := _write_in_keys(following):
                    write_ins.update(keys)
                    end += length
                    break
            # Wiersz bez znacznika może być dalszym ciągiem poprzedniej opcji.
            closed = end == len(lines) or (
                not _MARKED_OPTION.match(lines[end][1])
                and (lines[end][0] > lines[end - 1][0] + 1 or lines[end][1].endswith(":"))
            )
            lists[_key(heading[:-1])].append(SourceList(part, line_number, values, write_ins, closed))
    return lists


def _proposals(form: dict, text: str) -> list[dict]:
    lists = _source_lists(text)
    proposals = {}
    for tab in form["tabs"]:
        for field in iter_fields(tab):
            if field["type"] not in _CHOICE_TYPES or field.get("dictionaryName") in quality.COI_DICTIONARIES:
                continue
            title = field["title"]
            label = _key(title.rstrip().removesuffix(":"))
            topic = _CHOICE_PROMPT.sub("", label)
            if quality.is_country_label(topic) or _CATALOG_TOPIC.match(quality.normalize_text(topic)):
                continue
            sources = lists.get(label)
            if not sources:
                continue
            options = {_key(option["name"]) for option in field["options"]}
            if any(
                not source.closed
                or len(source.values) < 2
                or options - source.write_ins != source.values.keys()
                or _GENERIC & source.values.keys()
                for source in sources
            ):
                continue
            proposal = proposals.setdefault(label, {
                "name": title,
                "fields": [],
                "values": list(sources[0].values.values()),
                "reason": (
                    "Dokument definiuje listę wyboru dla tego pola. Nazwa pola nie wskazuje na znany słownik COI. "
                    "Katalog nie zawiera pełnych list wartości, dlatego zgodność wymaga weryfikacji."
                ),
                "status": "do_weryfikacji",
                "requires_official_approval": True,
                "references": [{"part": source.part, "line": source.line} for source in sources],
            })
            proposal["fields"].append({"techName": field["techName"], "title": title})
    return list(proposals.values())


def _read_result(path: Path) -> dict:
    resolved = path.resolve()
    if resolved.parent != path.parent or _env_file(resolved) or _control_path(resolved):
        raise ValueError(f"Niedozwolona ścieżka wyniku E1: {path.name}.")
    return json.loads(resolved.read_text(encoding="utf-8"))


def _source_file(materials: Path, number: int, filename: str) -> Path:
    if not filename or filename != Path(filename).name or _env_file(Path(filename)):
        raise ValueError(f"Niedozwolona nazwa pliku źródłowego F{number}.")
    candidates = []
    for folder in sorted(materials.glob(f"{number}. *")):
        directory = folder.resolve()
        path = (directory / filename).resolve()
        if path.parent == directory and not _control_path(path) and not _env_file(path) and path.is_file():
            candidates.append(path)
    if len(candidates) != 1:
        raise ValueError(f"Brak jednoznacznego pliku źródłowego F{number}: {filename}.")
    return candidates[0]


def _report(results: Path, materials: Path) -> dict:
    allowed = {f"F{number}": number for number in (*DEFAULT_FORMS, 5)}
    forms = []
    for row in _read_result(results / "report.json")["forms"]:
        name = row["form"]
        if name not in allowed:
            raise ValueError("Raport zawiera formularz spoza zakresu E1.")
        if row["status"] != "OK" or row["lint"]["count"] != 0:
            continue
        source = _source_file(materials, allowed[name], row["file"])
        artifact = f"{name}.coi.json"
        form = _read_result(results / artifact)
        document = extract.extract(source.read_bytes(), row["format"])
        forms.append({
            "form": name,
            "coi_result": artifact,
            "source": {"file": source.name, "format": document.source_format},
            "proposals": _proposals(form, document.text),
        })
    return {"catalog": {"source": "Hacknation - Słowniki", "dictionaries": sorted(_CATALOG)}, "forms": forms}


def main() -> int:
    parser = argparse.ArgumentParser(description="Zapisz propozycje słowników dla gotowych wyników E1.")
    parser.add_argument("--results", required=True, type=Path, help="Katalog zawierający report.json i JSON-y COI")
    parser.add_argument("--materials", type=Path, default=MATERIALS, help="Katalog dokumentów źródłowych COI")
    args = parser.parse_args()
    try:
        results = _output_directory(args.results)
        report = _report(results, args.materials)
        output = results / "dictionary-proposals.json"
        _write_json(output, report)
    except (AppError, OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Błąd przygotowania propozycji: {error}\n")
    print(f"Zapisano raport {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
