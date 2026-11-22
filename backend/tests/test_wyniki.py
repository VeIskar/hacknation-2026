"""Zapisane wyniki konkursowe wyniki/F*.coi.json: produkcyjny linter, struktura i brak regresji.

Test nie woła modelu (ani Eden AI, ani Ollamy) i nie potrzebuje dokumentów źródłowych.
Sprawdza powtarzalność przetwarzania zapisanych plików, nie skuteczność nowych wywołań modelu.
"""

import hashlib
import json
import re
from collections import Counter
from copy import deepcopy
from pathlib import Path

import pytest

from app import lint
from app.quality import COI_DICTIONARIES

WYNIKI = Path(__file__).resolve().parents[2] / "wyniki"
FORMS = [f"F{number}" for number in range(2, 10)]

# SHA-256 plików w chwili zapisu. Zmiana pliku musi być świadoma: wtedy aktualizuj też raport.
SHA256 = {
    "F2": "14df810c03704f7879fdc6add041bd78253bc7140d5f197a88aa2cbad3b876b1",
    "F3": "3e4e06fe6da7ea35ffc7e26f71746f7e3858c6803e03a7006e8577bf0094fe8c",
    "F4": "cb34787ba10b110102ac4c1601a4ce725ee44018e546055b6963326fcf4d026e",
    "F5": "5f0ee452879b840447a3df03eeb68221a02a0dfb4e946859768c891a93607220",
    "F6": "22dfcdb1906cca27a64afb0f30b5cddd8856e03a9806dda513e9cfd9ba65c82e",
    "F7": "f4ee0d2d04baddafa44c1d601bcf9b0dfed64cf3e2cba0415dc37a957e4f274c",
    "F8": "02dad62602271fe50009e425b637c30786f0f386d7d33897b9a720517e5a7ab5",
    "F9": "eab0cad5dead0cfd5cfc617482977ec39e5fa6a3180a566377bae77788ef7ceb",
}
# F5 nie zgadza się z wierszem F5 w wyniki/report.md (SHOW, walidatory, słowniki).
# Pochodzenie pliku jest więc niepotwierdzone; patrz wyniki/TESTY.md.
REPORT_MATCHED = [form for form in FORMS if form != "F5"]


def _path(form: str) -> Path:
    return WYNIKI / f"{form}.coi.json"


def _load(form: str) -> dict:
    return json.loads(_path(form).read_text(encoding="utf-8"))


def _walk(questions: list) -> list[dict]:
    fields = []
    for question in questions or []:
        field = question["field"]
        fields.append(field)
        fields.extend(_walk(field.get("repeatingSectionGrid")))
    return fields


def _fields(form: dict) -> list[dict]:
    return [field for tab in form["tabs"] for field in _walk(tab["questions"])]


def _stats(form: dict) -> dict:
    fields = _fields(form)
    return {
        "show": sum(1 for field in fields for state in field.get("states", []) if state.get("type") == "SHOW"),
        "validators": Counter(name for field in fields for name in field.get("validation", [])),
        "dictionaries": Counter(field["dictionaryName"] for field in fields if field.get("dictionaryName")),
    }


def _report_stats() -> dict[str, dict]:
    """Liczby z sekcji „## Fn” w wyniki/report.md (zapis przebiegu Eden AI)."""
    text = (WYNIKI / "report.md").read_text(encoding="utf-8")
    def counts(body: str, label: str) -> Counter:
        line = re.search(rf"\*\*{label}\*\* (.*)", body).group(1)
        return Counter({name: int(count) for name, count in re.findall(r"(\S+) × (\d+)", line)})

    rows = {}
    for form, body in re.findall(r"^## (F\d)\n(.*?)(?=^## |\Z)", text, re.DOTALL | re.MULTILINE):
        rows[form] = {
            "show": int(re.search(r"\*\*SHOW\*\* razem (\d+)", body).group(1)),
            "validators": counts(body, "Walidatory"),
            "dictionaries": counts(body, "Słowniki"),
        }
    return rows


def test_zestaw_f2_f9_jest_kompletny():
    assert sorted(path.name for path in WYNIKI.glob("F*.coi.json")) == [f"{form}.coi.json" for form in FORMS]


@pytest.mark.parametrize("form", FORMS)
def test_plik_bez_zmian(form):
    data = _path(form).read_bytes()
    assert hashlib.sha256(data).hexdigest() == SHA256[form]
    # Zapis jest kanoniczny: odczyt i ponowny zapis dają te same bajty.
    parsed = json.loads(data.decode("utf-8"))
    assert json.dumps(parsed, ensure_ascii=False, indent=2) + "\n" == data.decode("utf-8")


@pytest.mark.parametrize("form", FORMS)
def test_produkcyjny_linter_bez_bledow(form):
    assert lint.check(_load(form)) == []


@pytest.mark.parametrize("form", FORMS)
def test_struktura_stron_sekcji_i_pol(form):
    coi = _load(form)
    assert isinstance(coi["title"], str) and coi["title"].strip()
    tabs = coi["tabs"]
    assert len(tabs) >= 2
    assert tabs[-1]["type"] == "FINISH"
    assert all(tab["type"] == "MAIN" for tab in tabs[:-1])
    for tab in tabs[:-1]:
        assert tab["questions"], tab["title"]
        for question in tab["questions"]:
            assert question["field"]["type"] in {"SECTION", "REPEATING_SECTION"}, tab["title"]
            assert question["field"]["repeatingSectionGrid"], question["field"]["techName"]
    ids = [tab["id"] for tab in tabs] + [field["id"] for field in _fields(coi)]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("form", FORMS)
def test_walidatory_i_slowniki_znane(form):
    fields = _fields(_load(form))
    for field in fields:
        for name in field.get("validation", []):
            assert name in lint._VALIDATORS, f"{field['techName']}: {name}"
        if field.get("dictionaryName"):
            assert field["dictionaryName"] in COI_DICTIONARIES, field["techName"]


@pytest.mark.parametrize("form", REPORT_MATCHED)
def test_zgodnosc_z_raportem_przebiegu(form):
    assert _stats(_load(form)) == _report_stats()[form]


def test_f5_nie_pochodzi_z_przebiegu_w_raporcie():
    # Strażnik statusu: gdy ktoś podmieni F5 na wynik z raportu, ten test każe poprawić TESTY.md.
    assert _stats(_load("F5")) != _report_stats()["F5"]


# Testy negatywne: te same sprawdzenia muszą wykryć uszkodzony plik.

def _errors_with(coi: dict, message: str) -> list[str]:
    return [error for error in lint.check(coi) if message in error]


def _first_show(coi: dict) -> dict:
    return next(state for field in _fields(coi) for state in field.get("states", []) if state.get("type") == "SHOW")


def test_wykrywa_odwolanie_do_nieistniejacego_pola():
    coi = deepcopy(_load("F2"))
    state = _first_show(coi)
    state["query"] = re.sub(r"'[a-z_0-9]+' in field\.techName\]\.field\.__userAnswer",
                            "'nie_ma_takiego_pola' in field.techName].field.__userAnswer", state["query"])
    assert "nie_ma_takiego_pola" in state["query"]
    assert _errors_with(coi, "nie ma pola 'nie_ma_takiego_pola'")


def test_wykrywa_bledna_skladnie_warunku():
    coi = deepcopy(_load("F9"))
    state = _first_show(coi)
    state["query"] = state["query"] + " and ("
    assert _errors_with(coi, "nierozpoznane zapytanie JSONata")


def test_wykrywa_nieznany_walidator():
    coi = deepcopy(_load("F8"))
    next(field for field in _fields(coi) if field.get("validation"))["validation"].append("NIEZNANY")
    assert _errors_with(coi, "nieznany walidator 'NIEZNANY'")


def test_wykrywa_brak_strony_finish():
    coi = deepcopy(_load("F3"))
    coi["tabs"].pop()
    assert _errors_with(coi, "oczekiwano FINISH")
