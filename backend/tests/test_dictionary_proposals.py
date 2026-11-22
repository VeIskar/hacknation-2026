"""Propozycje słowników z dokumentu i raportu E1."""

import html
import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_extract import docx, pdf

from app import lint
from app.generator import build_form
from app.models import FormAnalysis

REPO = Path(__file__).resolve().parents[2]
TITLE = "Rodzaj oświetlenia"
OPTIONS = ("Lampy parkowe", "Latarnie uliczne", "Oprawy elewacyjne")
LIST = f"{TITLE}:\n" + "\n".join(f"- {option}" for option in OPTIONS)


@pytest.fixture
def proposals(monkeypatch):
    monkeypatch.syspath_prepend(str(REPO / "scripts"))
    return importlib.import_module("propose_dictionaries")


def _form(title=TITLE, options=OPTIONS, **binding):
    field = {
        "title": title,
        "techName": "typ_oswietlenia",
        "type": "SELECT",
        "options": [{"name": value} for value in options],
        **binding,
    }
    return {"tabs": [{"questions": [{"field": {"type": "SECTION", "repeatingSectionGrid": [{"field": field}]}}]}]}


def test_proposes_the_document_list_for_official_approval(proposals):
    [proposal] = proposals._proposals(_form(), f"Wniosek o instalację\fDane instalacji\n{LIST}")
    assert proposal["name"] == TITLE
    assert proposal["fields"] == [{"techName": "typ_oswietlenia", "title": TITLE}]
    assert proposal["values"] == list(OPTIONS)
    assert proposal["references"] == [{"part": 2, "line": 2}]
    assert "nie zawiera pełnych list wartości" in proposal["reason"]
    assert proposal["status"] == "do_weryfikacji"
    assert proposal["requires_official_approval"] is True


@pytest.mark.parametrize(("title", "options", "binding"), [
    ("W jakim państwie się urodziłeś", ("Polska", "Niemcy"), {"dictionaryName": "Kraje"}),
    ("Gmina miejsca zamieszkania", ("Zgierz", "Stryków"), {}),
    ("Kraje pobytu", ("Polska", "Niemcy", "Czechy"), {}),
    ("Posiadane obywatelstwo", ("Polska", "Niemcy"), {}),
    ("Kraj / państwo", ("Polska", "Niemcy"), {}),
    ("Kraj zamieszkania lub pobytu", ("Polska", "Niemcy"), {}),
])
def test_skips_existing_catalog_domain(proposals, title, options, binding):
    text = f"{title}:\n" + "\n".join(f"- {option}" for option in options)
    assert proposals._proposals(_form(title, options, **binding), text) == []


@pytest.mark.parametrize(("options", "text"), [
    (OPTIONS, ""),
    (OPTIONS, "Opis instalacji:\n" + "\n".join(f"- {option}" for option in OPTIONS)),
    (OPTIONS, f"{TITLE}:\n- {OPTIONS[0]}\n- {OPTIONS[1]}\nInne pole:\n- {OPTIONS[2]}"),
    ((OPTIONS[0], "Latarnie", OPTIONS[2]), LIST),
    (OPTIONS, f"{LIST}\n\n{TITLE}:\n- Kinkiety\n- Reflektory"),
    (OPTIONS, f"{LIST}\n\n{TITLE}:\n- Kinkiety"),
    (("Tak", "Nie"), f"{TITLE}:\n- Tak\n- Nie"),
])
def test_skips_options_without_unambiguous_list_evidence(proposals, options, text):
    assert proposals._proposals(_form(options=options), text) == []


def test_deduplicates_source_values_and_omits_write_in(proposals):
    text = f"{LIST}\n- LAMPY   PARKOWE\nInny\nrodzaj ………"
    options = ("lampy parkowe", *OPTIONS[1:], "INNY RODZAJ", "LAMPY PARKOWE")
    [proposal] = proposals._proposals(_form(options=options), text)
    assert proposal["values"] == list(OPTIONS)


def test_does_not_treat_wrapped_options_as_a_shorter_list(proposals):
    text = f"{TITLE}:\n- {OPTIONS[0]}\n- Latarnie\n  uliczne\n- {OPTIONS[2]}"
    assert proposals._proposals(_form(options=(OPTIONS[0], "Latarnie")), text) == []


def test_omits_marked_write_in(proposals):
    option = "Inny rodzaj ………"
    [proposal] = proposals._proposals(_form(options=(*OPTIONS, option)), f"{LIST}\n- {option}")
    assert proposal["values"] == list(OPTIONS)


def test_writes_separate_report_and_preserves_coi_bytes(tmp_path):
    materials = tmp_path / "materialy"
    folder = materials / "2. Formularz testowy"
    folder.mkdir(parents=True)
    filename = "Wniosek o oświetlenie.docx"
    paragraphs = "".join(f"<w:p><w:r><w:t>{html.escape(line)}</w:t></w:r></w:p>" for line in LIST.splitlines())
    (folder / filename).write_bytes(docx(paragraphs))

    results = tmp_path / "wyniki"
    results.mkdir()
    analysis = json.loads((Path(__file__).parent / "fixtures/fields.json").read_text(encoding="utf-8"))
    analysis["subject_pages"] = [{"title": "Oświetlenie", "sections": [{"title": "Instalacja", "fields": [
        {"label": TITLE, "type": "SELECT", "options": OPTIONS},
    ]}]}]
    form = build_form(FormAnalysis.model_validate(analysis))
    assert lint.check(form) == []
    prior = {
        "report.json": json.dumps({"forms": [
            {"form": "F2", "status": "OK", "file": filename, "format": "docx", "lint": {"count": 0}},
            {"form": "F3", "status": "błąd"},
        ]}, ensure_ascii=False).encode(),
        "F2.coi.json": (json.dumps(form, ensure_ascii=False, indent=4) + "\n").encode(),
    }
    for name, data in prior.items():
        (results / name).write_bytes(data)

    result = subprocess.run(
        [sys.executable, str(REPO / "scripts/propose_dictionaries.py"),
         "--results", str(results), "--materials", str(materials)], check=False, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads((results / "dictionary-proposals.json").read_text(encoding="utf-8"))
    assert len(report["catalog"]["dictionaries"]) == 6
    [row] = report["forms"]
    assert row["form"] == "F2"
    assert row["coi_result"] == "F2.coi.json"
    assert row["source"] == {"file": filename, "format": "docx"}
    assert row["proposals"][0]["values"] == list(OPTIONS)
    for name, data in prior.items():
        assert (results / name).read_bytes() == data


def test_refuses_missing_or_control_source(tmp_path, proposals):
    folder = tmp_path / "9. Formularz testowy"
    folder.mkdir()
    with pytest.raises(ValueError, match="Brak jednoznacznego pliku"):
        proposals._source_file(tmp_path, 9, "wniosek.pdf")

    control = tmp_path / "1. Dane kontrolne"
    control.mkdir()
    path = control / "wniosek.pdf"
    path.write_bytes(pdf("Źródło kontrolne"))
    (folder / path.name).symlink_to(path)
    with pytest.raises(ValueError, match="Brak jednoznacznego pliku"):
        proposals._source_file(tmp_path, 9, path.name)
