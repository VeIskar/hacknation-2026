import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.models import FormAnalysis
from app.repair import repair_analysis


def _field(label: str, field_type: str = "TEXT_FIELD", **attrs: object) -> dict:
    return {"label": label, "type": field_type, **attrs}


def _section(title: str, *fields: dict, **attrs: object) -> dict:
    return {"title": title, "fields": list(fields), **attrs}


def _check(field: str = "Tryb", equals: str = "A", **attrs: object) -> dict:
    return {"field": field, "equals": equals, **attrs}


def _form(*sections: dict, extra: tuple[dict, ...] = ()) -> dict:
    return {
        "title": "Wniosek testowy",
        "addressee": {"type": "URZAD", "name": "Urząd testowy"},
        "applicants": "BOTH",
        "applicant": {
            "proxy": False, "applicant_pesel": False, "person_address": False,
            "entity_ids": [], "entity_ids_one_of": False, "entity_address": False,
            "representative_proof": False, "correspondence_address": False,
            "contact": [], "applicant_extra_fields": list(extra),
        },
        "subject_pages": [{"title": "Przedmiot", "sections": list(sections)}],
    }


def test_n1_removes_repeated_options_in_all_scopes_and_preserves_order() -> None:
    condition = {"field": "Tryb", "equals": "A", "any_of": ["A", "C", "B", " C ", "B"]}
    data = _form(
        _section("Wybór", _field("Tryb", "RADIO", options=["A", "B", "C"]), _field("Opis", show_if=condition)),
        _section("Załączniki", _field("Załącznik", show_if_all=[condition]), show_if=condition),
        extra=(
            _field("Odbiór", "RADIO", options=["Osobiście", "Pocztą"]),
            _field("Kod", show_if={"field": "Odbiór", "equals": "Pocztą", "any_of": ["Pocztą"]}),
        ),
    )
    # JSON po parsowaniu nie współdzieli słowników między warunkami.
    data = json.loads(json.dumps(data))
    original = deepcopy(data)
    repaired, notes = repair_analysis(data, last_chance=False)
    first, second = repaired["subject_pages"][0]["sections"]
    assert first["fields"][1]["show_if"]["any_of"] == ["C", "B"]
    assert second["show_if"]["any_of"] == ["C", "B"]
    assert second["fields"][0]["show_if_all"][0]["any_of"] == ["C", "B"]
    assert repaired["applicant"]["applicant_extra_fields"][1]["show_if"]["any_of"] == []
    assert len(notes) == 4
    assert data == original
    assert repair_analysis(repaired, last_chance=False) == (repaired, [])
    FormAnalysis.model_validate(repaired)


@pytest.mark.parametrize("ids", [[], ["NIP"], ["NIP", "REGON"]])
def test_n2_turns_off_choice_of_identifier_only_without_two_options(ids: list[str]) -> None:
    data = _form(_section("Sekcja", _field("Opis")))
    data["applicant"].update(entity_ids=ids, entity_ids_one_of=True)
    repaired, notes = repair_analysis(data, last_chance=False)
    assert repaired["applicant"]["entity_ids_one_of"] is (len(ids) >= 2)
    assert repaired["applicant"]["entity_ids"] == ids
    assert len(notes) == int(len(ids) < 2)
    FormAnalysis.model_validate(repaired)


@pytest.mark.parametrize("options", [{}, {"options": None}, {"options": []}], ids=["brak", "null", "puste"])
def test_n3_fills_checkbox_choices_only(options: dict) -> None:
    radio = _field("Tryb", "RADIO", **options)
    select = _field("Kategoria", "SELECT", **options)
    data = _form(
        _section("Sekcja", _field("Zgoda", "CHECKBOX", **options), radio, select),
        extra=(_field("Oświadczenie", "CHECKBOX", **options),),
    )
    repaired, notes = repair_analysis(data, last_chance=False)
    checkbox, new_radio, new_select = repaired["subject_pages"][0]["sections"][0]["fields"]
    assert checkbox["options"] == ["Tak"]
    assert repaired["applicant"]["applicant_extra_fields"][0]["options"] == ["Tak"]
    assert (new_radio, new_select) == (radio, select)
    assert len(notes) == 2


@pytest.mark.parametrize("data", [None, 3, "bez obiektu", [1, {"options": None}], {}, {
    "subject_pages": [False, {"sections": {"fields": "błędny typ"}}, {"sections": [{"fields": [None]}]}],
    "applicant": {"entity_ids": None, "entity_ids_one_of": True, "applicant_extra_fields": False},
}])
def test_repair_leaves_unexpected_data_unchanged(data: object) -> None:
    assert repair_analysis(data, last_chance=False) == (data, [])


def test_existing_fields_fixture_needs_no_repairs() -> None:
    data = json.loads((Path(__file__).parent / "fixtures" / "fields.json").read_text(encoding="utf-8"))
    for last_chance in (False, True):
        repaired, notes = repair_analysis(data, last_chance=last_chance)
        assert repaired == data and notes == []
        assert repaired is not data
        assert repaired["subject_pages"] is not data["subject_pages"]


@pytest.mark.parametrize("options", [{}, {"options": None}, {"options": []}], ids=["brak", "null", "puste"])
def test_s1_converts_empty_choices_and_keeps_their_own_conditions(options: dict) -> None:
    trigger = _field("Tryb", "RADIO", options=["A", "B"])
    switch = _field("Dodatkowe dane", "RADIO", required=False, show_if=_check(), show_if_all=[_check()], **options)
    related = _check("Dodatkowe dane", "Włącz", any_of=["Inny"])
    data = _form(
        _section("Sterowanie", trigger, switch),
        _section("Dane", _field("Opis", show_if_all=[related]), show_if=related),
        extra=(
            _field("Dodaj informację", "SELECT", **options),
            _field("Informacja", show_if=_check("Dodaj informację", "Dodaj")),
        ),
    )
    data = json.loads(json.dumps(data))
    assert repair_analysis(data, last_chance=False) == (data, [])
    repaired, notes = repair_analysis(data, last_chance=True)
    controls, details = repaired["subject_pages"][0]["sections"]
    assert controls["fields"] == [trigger, {**switch, "type": "CHECKBOX", "options": ["Tak"]}]
    assert details["show_if"] == _check("Dodatkowe dane", "Tak", any_of=[])
    assert details["fields"][0]["show_if_all"] == [details["show_if"]]
    extra = repaired["applicant"]["applicant_extra_fields"]
    assert extra[0] == _field("Dodaj informację", "CHECKBOX", options=["Tak"])
    assert extra[1]["show_if"] == _check("Dodaj informację", "Tak", any_of=[])
    assert len(notes) == 5 and all(note.startswith("S1 ") for note in notes)
    FormAnalysis.model_validate(repaired)
    assert repair_analysis(repaired, last_chance=True) == (repaired, [])


@pytest.mark.parametrize(("sections", "message"), [
    ([_section("Sekcja", _field("Cel", show_if=_check()))], "w przedmiocie nie ma pola"),
    ([_section("Sekcja", _field("Tryb", "RADIO", options=["A", "Z"]), _field("Tryb", "SELECT", options=["A", "Z"]),
               _field("Cel", show_if=_check()))], "jest niejednoznaczna w przedmiocie"),
    ([_section("Sekcja", _field("Tryb"), _field("Cel", show_if=_check()))], "nie jest polem wyboru"),
    ([_section("Sekcja", _field("Tryb", "RADIO", options=["A", "Z"], show_if=_check()))], "wskazuje to samo pole"),
    ([_section("Sekcja", _field("Cel", show_if=_check()), _field("Tryb", "RADIO", options=["A", "Z"]))], "musi być przed"),
    ([_section("Sekcja", _field("Tryb", "RADIO", options=["A", "Z"]), show_if=_check())], "wewnątrz ukrywanej sekcji"),
    ([_section("Sekcja", _field("Tryb", "RADIO", options=["A", "Z"]),
               _field("Cel", show_if=_check(equals="B", any_of=["A"])))], "nie ma opcji 'B'"),
], ids=["brak", "niejednoznaczna", "typ", "samo-odwolanie", "kolejnosc", "wewnatrz-sekcji", "equals"])
def test_s2_subject_matches_each_reason_rejected_by_the_model(sections: list[dict], message: str) -> None:
    data = _form(*sections)
    ordinary, notes = repair_analysis(data, last_chance=False)
    assert ordinary == data and notes == []
    with pytest.raises(ValidationError, match=message):
        FormAnalysis.model_validate(ordinary)

    repaired, notes = repair_analysis(data, last_chance=True)
    page = repaired["subject_pages"][0]
    assert all("show_if" not in node for section in page["sections"] for node in [section, *section["fields"]])
    assert len(notes) == 1 and notes[0].startswith("S2 ")
    FormAnalysis.model_validate(repaired)


def test_s2_preserves_valid_cross_page_references_and_filters_only_invalid_alternatives() -> None:
    data = _form(_section("Wybór", _field("Tryb", "SELECT", options=["A", "B", "C"])))
    data["subject_pages"].append({"title": "Dalsze dane", "sections": [_section(
        "Szczegóły", _field("Wpisz szczegóły"), show_if_all=[
            _check(equals="A", any_of=["X", "C", "Y", "B"]), _check("Nieistniejące pole"),
        ],
    )]})
    with pytest.raises(ValidationError, match="nie ma opcji 'X'"):
        FormAnalysis.model_validate(data)
    repaired, notes = repair_analysis(data, last_chance=True)
    section = repaired["subject_pages"][1]["sections"][0]
    assert section["show_if_all"] == [_check(equals="A", any_of=["C", "B"])]
    assert len(notes) == 2
    FormAnalysis.model_validate(repaired)


@pytest.mark.parametrize(("extra", "message"), [
    ((_field("Cel", show_if=_check()),), "w dodatkowych danych wnioskodawcy nie ma pola"),
    ((_field("Cel", show_if=_check()), _field("Tryb", "RADIO", options=["A", "Z"]),
      _field("Tryb", "SELECT", options=["A", "Z"])), "jest niejednoznaczna"),
    ((_field("Tryb", "RADIO", options=["A", "Z"], show_if=_check()),), "wskazuje to samo pole"),
    ((_field("Cel", show_if=_check()), _field("Tryb")), "nie jest polem wyboru"),
    ((_field("Cel", show_if=_check(equals="B")), _field("Tryb", "RADIO", options=["A", "Z"])), "nie ma opcji 'B'"),
], ids=["poza-lista", "niejednoznaczna", "samo-odwolanie", "typ", "equals"])
def test_s2_applicant_uses_the_same_source_scope_as_the_model(extra: tuple[dict, ...], message: str) -> None:
    data = _form(_section("Przedmiot", _field("Tryb", "RADIO", options=["A", "Z"])), extra=extra)
    with pytest.raises(ValidationError, match=message):
        FormAnalysis.model_validate(data)
    repaired, notes = repair_analysis(data, last_chance=True)
    assert all("show_if" not in field for field in repaired["applicant"]["applicant_extra_fields"])
    assert len(notes) == 1
    FormAnalysis.model_validate(repaired)


def test_s2_applicant_drops_forbidden_compound_conditions_and_keeps_later_source() -> None:
    data = _form(_section("Przedmiot", _field("Opis")), extra=(
        _field("Cel", show_if=_check(any_of=["B"]), show_if_all=[_check(equals="B")]),
        _field("Tryb", "SELECT", options=["A", "B"]),
    ))
    with pytest.raises(ValidationError, match="tylko show_if z field i equals"):
        FormAnalysis.model_validate(data)
    repaired, notes = repair_analysis(data, last_chance=True)
    assert repaired["applicant"]["applicant_extra_fields"][0] == _field("Cel", show_if=_check())
    assert len(notes) == 2
    FormAnalysis.model_validate(repaired)
