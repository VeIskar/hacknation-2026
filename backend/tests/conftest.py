"""Wzorce COI leżą poza gitem, w materialy/ (SPEC.md, „Real and mocked”).

Test, który ich potrzebuje, bierze je przez fixture i jest pomijany, gdy materiałów nie ma.
Folder 5 to zbiór roboczy, folder 1 to zbiór kontrolny (docs/ZESTAW_TESTOWY.md, pkt 1).
"""

import json
from pathlib import Path

import pytest

MATERIALS = Path(__file__).resolve().parents[2] / "materialy"


def _coi_reference(folder: int) -> dict:
    matches = sorted(MATERIALS.glob(f"{folder}. */konfiguracja_form_*.json"))
    if not matches:
        pytest.skip(f"brak wzorca COI z folderu {folder} w {MATERIALS}")
    return json.loads(matches[0].read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def coi_working_reference() -> dict:
    return _coi_reference(5)


@pytest.fixture(scope="session")
def coi_control_reference() -> dict:
    return _coi_reference(1)
