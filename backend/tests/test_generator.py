"""P1: generator JSON COI – build_form(FormAnalysis) -> dict.

Źródła: SZABLONY_SEKCJI.md (format i szablon), wzorzec COI z folderu 5 (coi_working_reference)
oraz dopowiedzenia lidera do P1 (warianty wnioskodawcy, unikalne nazwy, jsonata, UUID5, walidatory).
Formaty jsonaty i układu są tu zapisane niezależnie od kodu generatora.
"""

import ast
import json
import re
import unicodedata
import uuid
from hashlib import sha256
from itertools import pairwise, product
from pathlib import Path

import pytest
from pydantic import ValidationError
from starlette.responses import JSONResponse

from app import lint, quality
from app.generator import build_form, template
from app.generator import form as generator_form
from app.generator.coi import Names, choice_options, jsonata_string, slug
from app.generator.form import subject_page_titles
from app.models import FormAnalysis

FIXTURES = Path(__file__).parent / "fixtures"
ALL_FIXTURES = ["fields.json", "analysis_person.json", "analysis_entity.json", "analysis_edge_cases.json"]

FIELD_KEYS = {
    "id", "type", "techName", "title", "description", "options", "validation", "readOnly",
    "repeatingSectionGrid", "states", "questionOrder", "tooltipMessage",
}
OPTIONAL_KEYS = {"defaultValue", "defaultValueType", "dictionaryName", "multiLevelTree", "searchEnabled", "consentSectionConfig"}
EMPTY_HTML = "<html><head></head><body></body></html>"
# SZABLONY, rozdz. 3, S4 [decyzja]: pełne „Dane podmiotu”; wzorzec z folderu 5 ma tylko Nazwa i NIP.
DECIDED_ADDITIONS = {("Dane", "dane_podmiotu"): ["regon", "numer_krs"]}

ON_BEHALF, ROLE = "wybierz_w_czyim_imieniu_wnioskujesz", "wybierz_jako_kto_wnioskujesz"


def atom(option: str, field_name: str, page: str = "Dane", section: str = "podmiot_wniosku") -> str:
    """Warunek SHOW w formacie COI (SZABLONY, rozdz. 0). Wartości wpisuje się tak, jak stoją w jsonacie."""
    return (
        f"(\"{option}\" in tabs['{page}' in title].questions['{section}' in field.techName]"
        f".field.repeatingSectionGrid['{field_name}' in field.techName].field.__userAnswer)"
    )


OTHER_PERSON = atom("Innej osoby", ON_BEHALF)
LEGAL_ENTITY = atom("Osoby prawnej lub jednostki organizacyjnej", ON_BEHALF)
AS_ATTORNEY = atom("Pełnomocnik", ROLE)
AS_REPRESENTATIVE = atom("Reprezentant", ROLE)

# SPEC.md, „Field contract”: pole z kroku 6 demo (bez id, które zależy od formularza).
SPEC_FIELD_EXAMPLE = {
    "x": 0, "y": 5, "rows": 1, "cols": 3,
    "field": {
        "type": "TEXT_FIELD", "techName": "kod_pocztowy_inna_osoba", "title": "Kod pocztowy", "description": "",
        "options": [], "validation": ["REQUIRED", "ZIP_CODE"], "readOnly": False, "repeatingSectionGrid": [],
        "states": [{"type": "SHOW", "query": "(\"Polska\" in tabs['Dane' in title].questions['adres_zamieszkania_osoby_ktorej_jestes_pelnomocnikiem' in field.techName].field.repeatingSectionGrid['kraj_inna_osoba' in field.techName].field.__userAnswer)"}],
        "questionOrder": 5, "tooltipMessage": "",
    },
}

# SZABLONY, rozdz. 5, dla fields.json. Pola tylko do odczytu z rejestru mają [] (dopowiedzenie lidera).
EXPECTED_VALIDATION = {
    ON_BEHALF: ["REQUIRED"],
    ROLE: ["REQUIRED"],
    "kod_pocztowy": ["REQUIRED", "ZIP_CODE"],
    "nip": ["REQUIRED", "NIP"],
    "regon": ["REQUIRED", "REGON"],
    "kod_pocztowy_siedziba": ["REQUIRED", "ZIP_CODE"],
    "plik_z_odpisem_danych": ["REQUIRED"],
    "kod_pocztowy_inna_osoba": ["REQUIRED", "ZIP_CODE"],
    "plik_dokumentu_z_pelnomocnictwem": ["REQUIRED"],
    "plik_z_potwierdzeniem_przelewu": ["REQUIRED"],
    # Standardy COI przy radiu S10: „walidacja: pole wymagane” (poprawka po recenzji P1).
    "czy_zlozenie_pelnomocnictwa_wymaga_oplaty_skarbowej": ["REQUIRED"],
    "plik_z_potwierdzeniem_przelewu_2": ["REQUIRED"],
    "podatek_ktorego_dotyczy_nadplata": ["REQUIRED"],
    "kwota": ["REQUIRED"],
    "uzasadnienie": ["REQUIRED"],
    "wybierz_co_mamy_zrobic_z_nadplata": ["REQUIRED"],
    "nazwa_podatku": ["REQUIRED"],
    "numer_rachunku": ["REQUIRED"],
    "plik_deklaracji_podatkowej": ["REQUIRED"],
    "adres_e_mail": ["EMAIL"],
}

_LITERAL_DOUBLE = r'"(?:[^"\\]|\\.)*"'
_LITERAL_SINGLE = r"'(?:[^'\\]|\\.)*'"
ATOM = re.compile(
    rf"(?P<option>{_LITERAL_DOUBLE}) in tabs\[(?P<page>{_LITERAL_SINGLE}) in title\]"
    rf"\.questions\[(?P<section>{_LITERAL_SINGLE}) in field\.techName\]"
    rf"\.field\.repeatingSectionGrid\[(?P<field>{_LITERAL_SINGLE}) in field\.techName\]\.field\.__userAnswer"
)
# Sekwencje, które zna tokenizer JSONaty. \' do nich nie należy.
JSONATA_ESCAPES = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}


def analysis(name: str) -> FormAnalysis:
    return FormAnalysis.model_validate_json((FIXTURES / name).read_text(encoding="utf-8"))


def generated(name: str) -> dict:
    return build_form(analysis(name))


def layout(form: dict) -> list[tuple[str, str, list[tuple[str, list[str]]]]]:
    """(tytuł strony, typ, [(techName sekcji, [techName pól wg y])]) – pola we wzorcu nie są posortowane."""
    return [
        (
            page["title"],
            page["type"],
            [
                (q["field"]["techName"], [i["field"]["techName"] for i in sorted(q["field"]["repeatingSectionGrid"], key=lambda i: i["y"])])
                for q in sorted(page["questions"], key=lambda q: q["y"])
            ],
        )
        for page in form["tabs"]
    ]


def elements(form: dict) -> dict[tuple[str, str], dict]:
    """(tytuł strony, techName) -> obiekt field, dla sekcji i pól."""
    result = {}
    for page in form["tabs"]:
        for question in page["questions"]:
            for item in [question, *question["field"]["repeatingSectionGrid"]]:
                result[(page["title"], item["field"]["techName"])] = item["field"]
    return result


def by_tech_name(form: dict) -> dict[str, dict]:
    return {tech_name: item for (_, tech_name), item in elements(form).items()}


def squash(query: str) -> str:
    """Usuwa białe znaki poza literałami w cudzysłowach i apostrofach."""
    out, index, quote = [], 0, None
    while index < len(query):
        char = query[index]
        if quote:
            out.append(char)
            if char == "\\":
                out.append(query[index + 1])
                index += 2
                continue
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
            out.append(char)
        elif not char.isspace():
            out.append(char)
        index += 1
    return "".join(out)


def decode(literal: str) -> str:
    """Wartość literału jsonaty tak, jak odczyta ją JSONata; nieznana sekwencja to błąd."""
    quote, inner, out, index = literal[0], literal[1:-1], [], 0
    while index < len(inner):
        char = inner[index]
        if char == "\\":
            code = inner[index + 1]
            if code == "u":
                out.append(chr(int(inner[index + 2 : index + 6], 16)))
                index += 6
                continue
            assert code in JSONATA_ESCAPES, f"JSONata nie zna sekwencji \\{code} w {literal}"
            out.append(JSONATA_ESCAPES[code])
            index += 2
            continue
        assert char != quote, f"nieescapowany znak {quote} w {literal}"
        out.append(char)
        index += 1
    return "".join(out)


def atoms(query: str) -> list[tuple[str, str, str, str]]:
    """Rozbiera zapytanie na warunki (opcja, strona, sekcja, pole); poza nimi tylko nawiasy, and, or, $not."""
    rest = ATOM.sub("A", query)
    assert re.fullmatch(r"(?:\s|\(|\)|A|and|or|\$not)*", rest), query
    assert rest.count("(") == rest.count(")"), query
    return [tuple(decode(match[key]) for key in ("option", "page", "section", "field")) for match in ATOM.finditer(query)]


def states(item: dict) -> list[str]:
    assert all(state["type"] == "SHOW" for state in item.get("states", [])), item["techName"]
    return [state["query"] for state in item.get("states", [])]


# --- zgodność ze wzorcem z folderu 5 --------------------------------------------------------------


def test_tech_names_match_working_reference(coi_working_reference: dict) -> None:
    expected = layout(coi_working_reference)
    for page_title, _, sections in expected:
        for section_name, fields in sections:
            fields.extend(DECIDED_ADDITIONS.get((page_title, section_name), []))
    assert layout(generated("fields.json")) == expected


def test_show_queries_match_working_reference(coi_working_reference: dict) -> None:
    ours, reference = elements(generated("fields.json")), elements(coi_working_reference)
    with_states = {key for key, item in reference.items() if states(item)}
    assert len(with_states) >= 30, "wzorzec bez warunków – test nic by nie sprawdzał"
    assert {key for key, item in ours.items() if states(item) and key in reference} == with_states
    for key in sorted(with_states):
        assert [squash(q) for q in states(ours[key])] == [squash(q) for q in states(reference[key])], key


def test_nip_only_matches_working_reference_exactly(coi_working_reference: dict) -> None:
    data = analysis("fields.json").model_dump(mode="json")
    data["applicant"]["entity_ids"] = ["NIP"]
    form = build_form(FormAnalysis.model_validate(data))
    assert layout(form) == layout(coi_working_reference)

    def queries(config: dict) -> dict:
        return {key: [squash(query) for query in states(item)] for key, item in elements(config).items()}

    assert queries(form) == queries(coi_working_reference)


def test_subject_page_has_fixture_fields_and_conditions() -> None:
    a = analysis("fields.json")
    page = generated("fields.json")["tabs"][1]
    subject = a.subject_pages[0]
    assert page["title"] == subject.title and page["type"] == "MAIN"
    tech_name_of = {}
    for question, subject_section in zip(page["questions"], subject.sections, strict=True):
        assert question["field"]["title"] == subject_section.title
        for item, subject_field in zip(question["field"]["repeatingSectionGrid"], subject_section.fields, strict=True):
            produced = item["field"]
            tech_name_of[subject_field.label] = (question["field"]["techName"], produced["techName"])
            assert (produced["title"], produced["type"]) == (subject_field.label, subject_field.type.value)
            assert [option["name"] for option in produced["options"]] == subject_field.options
    conditions = 0
    for question, subject_section in zip(page["questions"], subject.sections, strict=True):
        for item, subject_field in zip(question["field"]["repeatingSectionGrid"], subject_section.fields, strict=True):
            if subject_field.show_if is None:
                assert states(item["field"]) == []
                continue
            conditions += 1
            source_section, source_field = tech_name_of[subject_field.show_if.field]
            expected = atom(subject_field.show_if.equals, source_field, page=subject.title, section=source_section)
            assert [squash(q) for q in states(item["field"])] == [squash(expected)]
    assert conditions == 2


def test_subject_field_show_combines_alternatives_with_all_conditions() -> None:
    data = _analysis_data("PERSON")
    section = data["subject_pages"][0]["sections"][0]
    section["fields"] = [
        {"label": "Tryb", "type": "RADIO", "options": ["A", "B", "C"]},
        {"label": "Dokumenty", "type": "CHECKBOX", "options": ["Rachunek", "Potwierdzenie"]},
        {
            "label": "Opis", "type": "TEXTAREA",
            "show_if": {"field": "Tryb", "equals": "A", "any_of": ["B"]},
            "show_if_all": [
                {"field": "Dokumenty", "equals": "Rachunek"},
                {"field": "Dokumenty", "equals": "Potwierdzenie"},
            ],
        },
    ]
    form = build_form(FormAnalysis.model_validate(data))
    a = atom("A", "tryb", "Treść sprawy", "cel_wniosku")
    b = atom("B", "tryb", "Treść sprawy", "cel_wniosku")
    bill = atom("Rachunek", "dokumenty", "Treść sprawy", "cel_wniosku")
    proof = atom("Potwierdzenie", "dokumenty", "Treść sprawy", "cel_wniosku")
    assert states(by_tech_name(form)["opis"]) == [f"({a} or {b}) and {bill} and {proof}"]
    assert lint.check(form) == []


def test_subject_section_show_refers_to_source_on_renamed_page() -> None:
    data = _analysis_data("PERSON")
    data["subject_pages"] = [
        {"title": "Dane", "sections": [{
            "title": "Wybór",
            "fields": [
                {"label": "Imię", "type": "RADIO", "options": ["Wpiszę", "Z rejestru"]},
                {"label": "Zakres", "type": "SELECT", "options": ["Pełny", "Skrócony"]},
            ],
        }]},
        {"title": "DANE", "sections": [{
            "title": "Dane sprawy",
            "show_if": {"field": "Imię", "equals": "Wpiszę"},
            "show_if_all": [{"field": "Zakres", "equals": "Pełny"}],
            "fields": [{"label": "Opis", "type": "TEXTAREA"}],
        }]},
    ]
    form = build_form(FormAnalysis.model_validate(data))
    items = elements(form)
    name = atom("Wpiszę", "imie_2", "Dane wniosku", "wybor")
    scope = atom("Pełny", "zakres", "Dane wniosku", "wybor")
    assert states(items[("DANE wniosku (2)", "dane_sprawy")]) == [f"{name} and {scope}"]
    assert states(items[("DANE wniosku (2)", "opis")]) == []
    assert lint.check(form) == []


def test_subject_show_inherits_visibility_of_sources_transitively() -> None:
    data = _analysis_data("PERSON")
    data["subject_pages"] = [{"title": "Decyzja", "sections": [
        {"title": "Wybory", "fields": [
            {"label": "Tryb", "type": "RADIO", "options": ["A", "B", "C"]},
            {"label": "Zakres", "type": "RADIO", "options": ["Pełny", "Skrócony"]},
        ]},
        {"title": "Szczegóły", "show_if": {"field": "Tryb", "equals": "A", "any_of": ["B"]}, "fields": [
            {"label": "Złożono dokument", "type": "RADIO", "options": ["Tak", "Nie"],
             "show_if": {"field": "Zakres", "equals": "Pełny"}},
        ]},
        {"title": "Potwierdzenie", "show_if_all": [{"field": "Złożono dokument", "equals": "Tak"}], "fields": [
            {"label": "Potwierdzasz?", "type": "RADIO", "options": ["Tak", "Nie"]},
        ]},
        {"title": "Podsumowanie", "fields": [
            {"label": "Opis decyzji", "type": "TEXTAREA", "show_if": {"field": "Potwierdzasz?", "equals": "Tak"}},
        ]},
    ]}]
    form = build_form(FormAnalysis.model_validate(data))
    items = by_tech_name(form)
    a = atom("A", "tryb", "Decyzja", "wybory")
    b = atom("B", "tryb", "Decyzja", "wybory")
    scope = atom("Pełny", "zakres", "Decyzja", "wybory")
    document = atom("Tak", "zlozono_dokument", "Decyzja", "szczegoly")
    confirmation = atom("Tak", "potwierdzasz", "Decyzja", "potwierdzenie")
    assert states(items["szczegoly"]) == [f"({a} or {b})"]
    assert states(items["zlozono_dokument"]) == [scope]
    assert states(items["potwierdzenie"]) == [f"{document} and ({a} or {b}) and {scope}"]
    assert states(items["opis_decyzji"]) == [f"{confirmation} and {document} and ({a} or {b}) and {scope}"]
    assert lint.check(form) == []


# --- format (SZABLONY, rozdz. 0) ------------------------------------------------------------------


def _check_field_keys(item: dict) -> None:
    keys = set(item)
    assert FIELD_KEYS <= keys and keys - FIELD_KEYS <= OPTIONAL_KEYS, (item["techName"], keys ^ FIELD_KEYS)
    for option in item["options"]:
        assert set(option) == {"id", "name", "techName"} and option["id"] == option["name"], option


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_layout_and_keys_follow_coi_format(name: str) -> None:
    form = generated(name)
    assert set(form) == {"title", "tabs", "flow"} and form["title"] == analysis(name).title
    assert [page["type"] for page in form["tabs"]] == ["MAIN"] * (len(form["tabs"]) - 1) + ["FINISH"]
    for page in form["tabs"]:
        assert set(page) == {"id", "title", "type", "questions"}
        y = 0
        for question in page["questions"]:
            section, grid = question["field"], question["field"]["repeatingSectionGrid"]
            assert set(question) == {"x", "y", "rows", "cols", "field"}
            assert (question["x"], question["cols"], question["y"], question["rows"]) == (0, 3, y, len(grid) + 1)
            assert section["type"] == "SECTION" and section["questionOrder"] == y and grid
            assert section["description"].startswith("<html><head></head><body>") and section["description"].endswith("</body></html>")
            _check_field_keys(section)
            for index, item in enumerate(grid):
                assert set(item) == {"x", "y", "rows", "cols", "field"}
                assert (item["x"], item["cols"], item["y"], item["rows"], item["field"]["questionOrder"]) == (0, 3, index, 1, index)
                assert item["field"]["type"] != "SECTION" and item["field"]["repeatingSectionGrid"] == []
                assert item["field"]["description"] == "" or item["field"]["description"].startswith("<html><head></head><body><p>")
                _check_field_keys(item["field"])
            y += len(grid) + 1
    pages = form["tabs"]
    assert [(link["source"], link["target"]) for link in form["flow"]["links"]] == [(a["id"], b["id"]) for a, b in pairwise(pages)]


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_tech_names_and_ids_are_unique(name: str) -> None:
    form = generated(name)
    tech_names = [tech_name for (_, tech_name) in elements(form)]
    assert len(tech_names) == sum(len(q["field"]["repeatingSectionGrid"]) + 1 for p in form["tabs"] for q in p["questions"])
    assert len(set(tech_names)) == len(tech_names)
    assert all(re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*", tech_name) for tech_name in tech_names)
    ids = [p["id"] for p in form["tabs"]] + [i["id"] for i in elements(form).values()] + [link["id"] for link in form["flow"]["links"]]
    assert len(set(ids)) == len(ids) and all(str(uuid.UUID(value)) == value for value in ids)
    assert {uuid.UUID(value).version for value in ids} == {5}
    for item in elements(form).values():
        option_names = [option["techName"] for option in item["options"]]
        assert len(set(option_names)) == len(option_names)


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_show_conditions_point_at_existing_fields_and_options(name: str) -> None:
    form = generated(name)
    pages = {page["title"]: page for page in form["tabs"]}
    assert len(pages) == len(form["tabs"]), "jsonata wybiera stronę po tytule"
    checked = 0
    for item in elements(form).values():
        for query in states(item):
            for option, page_title, section_name, field_name in atoms(query):
                sections = {q["field"]["techName"]: q["field"] for q in pages[page_title]["questions"]}
                grid = {i["field"]["techName"]: i["field"] for i in sections[section_name]["repeatingSectionGrid"]}
                source = grid[field_name]
                allowed = ["Polska"] if source.get("dictionaryName") == "Kraje" else [o["name"] for o in source["options"]]
                assert option in allowed, (item["techName"], option)
                checked += 1
    assert checked > 0


@pytest.mark.parametrize(("name", "count"), [("fields.json", 3), ("analysis_person.json", 2), ("analysis_entity.json", 1), ("analysis_edge_cases.json", 3)])
def test_country_fields_default_to_poland(name: str, count: int) -> None:
    form = generated(name)
    countries = [i["field"] for q in form["tabs"][0]["questions"] for i in q["field"]["repeatingSectionGrid"] if i["field"]["techName"].startswith("kraj")]
    assert len(countries) == count
    for item in countries:
        assert (item["type"], item["defaultValue"], item["dictionaryName"]) == ("SELECT", ["Polska"], "Kraje"), item["techName"]
        assert item["searchEnabled"] is True, item["techName"]


@pytest.mark.parametrize(("name", "suffixes"), [
    pytest.param("fields.json", ("", "_siedziba", "_inna_osoba"), id="F5"),
    pytest.param("analysis_form9.json", ("_siedziba", "_korespondencyjny"), id="F9"),
])
def test_export_binds_coi_dictionaries_to_address_selects(name: str, suffixes: tuple[str, ...]) -> None:
    items = by_tech_name(json.loads(JSONResponse(generated(name)).body))
    dictionaries = {tech_name: item for tech_name, item in items.items() if "dictionaryName" in item}
    assert set(dictionaries) == {f"{prefix}{suffix}" for prefix in ("kraj", "wojewodztwo") for suffix in suffixes}
    for tech_name, item in dictionaries.items():
        country = tech_name.startswith("kraj")
        assert item["dictionaryName"] == ("Kraje" if country else "TERYT_4G_DOWODOWY")
        assert item["type"] == "SELECT" and item["options"] == []
        assert item["defaultValue"] == (["Polska"] if country else [])
        assert item["searchEnabled"] is True and item.get("multiLevelTree", False) is (not country)
        assert item["readOnly"] is False and "defaultValueType" not in item
    for suffix in suffixes:
        foreign_city = items[f"miejscowosc{suffix}_zagranica"]
        assert foreign_city["type"] == "TEXT_FIELD"
        assert "dictionaryName" not in foreign_city and "defaultValue" not in foreign_city


@pytest.mark.parametrize(("name", "addressee", "identity", "editable"), [
    pytest.param(
        "fields.json", "nazwa_urzedu", {"numer_pesel": "MLPZ.pesel"},
        {
            "kod_pocztowy": "MLPZ.postCode",
            "ulica": "MLPZ.street",
            "numer_budynku": "MLPZ.building",
            "numer_lokalu": "MLPZ.apartment",
            "adres_e_mail": "MLPZ.email",
        },
        id="F5",
    ),
    pytest.param("analysis_form9.json", "nazwa_organu", {}, {}, id="F9"),
])
def test_export_binds_initial_values_only_to_matching_fields(
    name: str, addressee: str, identity: dict[str, str], editable: dict[str, str],
) -> None:
    items = by_tech_name(json.loads(JSONResponse(generated(name)).body))
    identity = {"imie": "MLPZ.name", "nazwisko": "MLPZ.surname", **identity}
    editable = {"numer_telefonu": "MLPZ.phoneNumber", **editable}
    actual = {
        tech_name: (item["type"], item.get("defaultValue"), item["defaultValueType"], item["readOnly"])
        for tech_name, item in items.items() if "defaultValueType" in item
    }
    expected = {
        tech_name: ("TEXT_FIELD", source, "EXTERNAL_SYSTEM", tech_name in identity)
        for tech_name, source in (identity | editable).items()
    }
    assert actual == expected
    assert {tech_name for tech_name, item in items.items() if item["readOnly"]} == {addressee, *identity}
    assert items[addressee]["defaultValue"] == analysis(name).addressee.name


# --- warianty wnioskodawcy ------------------------------------------------------------------------


def _data_sections(form: dict) -> list[str]:
    return [q["field"]["techName"] for q in form["tabs"][0]["questions"]]


def test_person_variant_has_no_entity_sections() -> None:
    form = generated("analysis_person.json")
    assert _data_sections(form) == [
        "organ_do_ktorego_jest_skladany_wniosek", "podmiot_wniosku", "twoje_dane", "adres_zamieszkania",
        "dane_innej_osoby", "adres_zamieszkania_osoby_ktorej_jestes_pelnomocnikiem", "pelnomocnictwo",
        "oplata_skarbowa_pelnomocnictwo_1",
    ]
    items = by_tech_name(form)
    assert [o["name"] for o in items[ON_BEHALF]["options"]] == ["Swoim", "Innej osoby"]
    assert ROLE not in items
    assert [squash(q) for q in states(items["pelnomocnictwo"])] == [squash(OTHER_PERSON)]
    assert items["nazwa_organu"]["defaultValue"] == "Burmistrz Miasta Lipowo"


def test_entity_variant_has_no_other_person_sections() -> None:
    form = generated("analysis_entity.json")
    assert _data_sections(form) == [
        "urzad_do_ktorego_jest_skladany_wniosek", "podmiot_wniosku", "twoje_dane",
        "dane_podmiotu", "adres_siedziby", "potwierdzenie_ze_jestes_reprezentantem", "pelnomocnictwo",
        "oplata_skarbowa_pelnomocnictwo_2",
    ]
    items = by_tech_name(form)
    assert ON_BEHALF not in items and "numer_pesel" not in items
    assert [o["name"] for o in items[ROLE]["options"]] == ["Pełnomocnik", "Reprezentant"]
    for name in [ROLE, "dane_podmiotu", "adres_siedziby"]:
        assert states(items[name]) == [], name
    assert states(items["potwierdzenie_ze_jestes_reprezentantem"]) == [AS_REPRESENTATIVE]
    for name in ["pelnomocnictwo", "oplata_skarbowa_pelnomocnictwo_2"]:
        assert states(items[name]) == [AS_ATTORNEY], name


@pytest.mark.parametrize(
    ("title", "verb"),
    [
        ("Wniosek o wydanie karty parkingowej", "wnioskujesz"),
        ("ZGŁOSZENIE imprezy plenerowej", "zgłaszasz"),
        ("Deklaracja udziału w konkursie", "deklarujesz"),
        ("Informacja o zmianie danych", "wnioskujesz"),
    ],
)
def test_applicant_radios_use_verb_from_title(title: str, verb: str) -> None:
    data = json.loads((FIXTURES / "fields.json").read_text(encoding="utf-8"))
    data["title"] = title
    items = by_tech_name(build_form(FormAnalysis.model_validate(data)))
    # techName stałe: od nich zależą warunki SHOW i zgodność ze wzorcem.
    assert (items[ON_BEHALF]["title"], items[ROLE]["title"]) == (f"Wybierz, w czyim imieniu {verb}", f"Wybierz, jako kto {verb}")
    assert [squash(q) for q in states(items[ROLE])] == [squash(LEGAL_ENTITY)]
    assert [squash(q) for q in states(items["pelnomocnictwo"])] == [squash(f"{OTHER_PERSON} or ({LEGAL_ENTITY} and {AS_ATTORNEY})")]


# --- dobór sekcji według decyzji z papieru ----------------------------------------------------------


def _analysis_data(applicants: str, **decisions: object) -> dict:
    return {
        "title": "Wniosek testowy",
        "addressee": {"type": "URZAD", "name": "Urząd Gminy Lipowo"},
        "applicants": applicants,
        "applicant": {
            "proxy": False,
            "applicant_pesel": False,
            "person_address": False,
            "entity_ids": [],
            "entity_ids_one_of": False,
            "entity_address": False,
            "representative_proof": False,
            "correspondence_address": False,
            "contact": [],
            "applicant_extra_fields": [],
        } | decisions,
        "subject_pages": [{
            "title": "Treść sprawy",
            "sections": [{"title": "Cel wniosku", "fields": [{"label": "Uzasadnienie", "type": "TEXTAREA"}]}],
        }],
    }


def _field_names(item: dict) -> list[str]:
    return [cell["field"]["techName"] for cell in item["repeatingSectionGrid"]]


def _assert_person_without_proxy(form: dict, *, pesel: bool, address: bool) -> None:
    expected = ["urzad_do_ktorego_jest_skladany_wniosek", "twoje_dane"]
    if address:
        expected.append("adres_zamieszkania")
    assert _data_sections(form) == expected
    items = by_tech_name(form)
    assert _field_names(items["twoje_dane"]) == ["imie", "nazwisko"] + (["numer_pesel"] if pesel else [])
    assert _field_names(items["dane_do_kontaktu"]) == ["numer_telefonu"]
    if address:
        assert states(items["adres_zamieszkania"]) == []


@pytest.mark.parametrize(
    ("pesel", "address"),
    [pytest.param(True, True, id="F3"), pytest.param(False, True, id="F4"), pytest.param(False, False, id="F7")],
)
def test_person_forms_without_proxy_have_only_paper_fields(pesel: bool, address: bool) -> None:
    data = _analysis_data("PERSON", applicant_pesel=pesel, person_address=address, contact=["PHONE"])
    _assert_person_without_proxy(build_form(FormAnalysis.model_validate(data)), pesel=pesel, address=address)


def test_form3_fixture_has_only_requested_applicant_sections() -> None:
    _assert_person_without_proxy(generated("analysis_form3.json"), pesel=True, address=True)


@pytest.mark.parametrize("identifiers", [pytest.param(["NIP"], id="F2"), pytest.param([], id="F6")])
def test_both_with_proxy_selects_entity_ids_without_register_proof(identifiers: list[str]) -> None:
    data = _analysis_data(
        "BOTH", proxy=True, person_address=True, entity_address=True, entity_ids=identifiers, contact=["PHONE", "EMAIL"],
    )
    items = by_tech_name(build_form(FormAnalysis.model_validate(data)))
    assert _field_names(items["dane_podmiotu"]) == ["nazwa", *[value.lower() for value in identifiers]]
    assert {"numer_pesel", "regon", "numer_krs", "potwierdzenie_ze_jestes_reprezentantem"}.isdisjoint(items)
    assert states(items["dane_podmiotu"]) == states(items["adres_siedziby"]) == [LEGAL_ENTITY]


def test_form8_has_alternative_ids_and_conditional_correspondence_address() -> None:
    data = _analysis_data(
        "BOTH", proxy=True, applicant_pesel=True, person_address=True, entity_ids=["REGON", "NIP"],
        entity_ids_one_of=True, entity_address=True, correspondence_address=True, contact=["PHONE", "EMAIL"],
    )
    items = by_tech_name(build_form(FormAnalysis.model_validate(data)))
    assert items["numer_pesel"]["defaultValue"] == "MLPZ.pesel"
    assert [o["name"] for o in items[ON_BEHALF]["options"]] == [
        "Swoim", "Innej osoby", "Osoby prawnej lub jednostki organizacyjnej",
    ]
    assert _field_names(items["dane_podmiotu"]) == ["nazwa", "nip", "regon"]
    assert "Podaj jeden z: NIP, REGON." in items["dane_podmiotu"]["description"]
    assert items["nip"]["validation"] == ["NIP"]
    assert items["regon"]["validation"] == ["REGON"]
    assert "numer_krs" not in items

    address = "adres_do_korespondencji"
    radio = "czy_adres_do_korespondencji_jest_inny"
    country = "kraj_korespondencyjny"
    assert _field_names(items[address]) == [
        radio, country, "miejscowosc_korespondencyjny_zagranica", "kod_pocztowy_korespondencyjny_zagranica",
        "ulica_korespondencyjny_zagranica", "wojewodztwo_korespondencyjny", "kod_pocztowy_korespondencyjny",
        "ulica_korespondencyjny", "numer_budynku_korespondencyjny", "numer_lokalu_korespondencyjny",
    ]
    assert states(items[address]) == states(items[radio]) == []
    assert (items[radio]["type"], items[radio]["title"], items[radio]["validation"]) == (
        "RADIO", "Czy adres do korespondencji jest inny?", ["REQUIRED"],
    )
    assert [option["name"] for option in items[radio]["options"]] == ["Tak", "Nie"]
    different = atom("Tak", radio, section=address)
    in_poland = atom("Polska", country, section=address)
    assert items[country]["dictionaryName"] == "Kraje"
    assert items[country]["defaultValue"] == ["Polska"]
    for key in [country, "numer_budynku_korespondencyjny", "numer_lokalu_korespondencyjny"]:
        assert states(items[key]) == [different], key
    for key in ["wojewodztwo", "kod_pocztowy", "ulica"]:
        assert states(items[f"{key}_korespondencyjny"]) == [f"{different} and {in_poland}"], key
    for key in ["miejscowosc", "kod_pocztowy", "ulica"]:
        assert states(items[f"{key}_korespondencyjny_zagranica"]) == [f"{different} and $not{in_poland}"], key


def test_form9_has_entity_role_and_additional_applicant_fields() -> None:
    data = _analysis_data(
        "ENTITY", proxy=True, entity_address=True, representative_proof=True, correspondence_address=True,
        applicant_extra_fields=[
            {"label": "Seria i numer dowodu osobistego pełnomocnika", "type": "TEXT_FIELD"},
            {"label": "Adres skrzynki ePUAP", "type": "TEXT_FIELD", "required": False},
        ],
    )
    form = build_form(FormAnalysis.model_validate(data))
    items = by_tech_name(form)
    assert {ON_BEHALF, "numer_pesel", "nip", "regon", "numer_krs", "oplata_skarbowa_pelnomocnictwo_1"}.isdisjoint(items)
    assert [o["name"] for o in items[ROLE]["options"]] == ["Pełnomocnik", "Reprezentant"]
    assert states(items[ROLE]) == []
    assert _data_sections(form)[-5:] == [
        "potwierdzenie_ze_jestes_reprezentantem", "adres_do_korespondencji", "dodatkowe_dane_wnioskodawcy",
        "pelnomocnictwo", "oplata_skarbowa_pelnomocnictwo_2",
    ]
    assert states(items["potwierdzenie_ze_jestes_reprezentantem"]) == [AS_REPRESENTATIVE]
    assert states(items["pelnomocnictwo"]) == states(items["oplata_skarbowa_pelnomocnictwo_2"]) == [AS_ATTORNEY]
    id_card, epuap = "seria_i_numer_dowodu_osobistego_pelnomocnika", "adres_skrzynki_epuap"
    assert _field_names(items["dodatkowe_dane_wnioskodawcy"]) == [id_card, epuap]
    assert items[id_card]["validation"] == ["REQUIRED", "SERIAL_NUMBER_ID_CARD"]
    assert items[epuap]["validation"] == ["EPUAP"]
    assert layout(form)[-2] == ("Kontakt i zgody", "MAIN", [("zgoda_wyrazenie", ["zgoda"])])
    assert lint.check(form) == []


def test_form9_builds_one_configuration_with_resolvable_show_queries() -> None:
    form = generated("analysis_form9.json")
    assert [page["title"] for page in form["tabs"]] == [
        "Dane", "Kandydat", "Osiągnięcia", "Zgody", "Kontakt i zgody", "Strona końcowa",
    ]
    first = form["tabs"][1]["questions"][0]["field"]["repeatingSectionGrid"][0]["field"]
    assert (first["title"], first["type"]) == ("Rodzaj wniosku", "RADIO")
    assert [option["id"] for option in first["options"]] == ["Stypendium", "Nagroda", "Wyróżnienie"]
    items = by_tech_name(form)
    assert all(item["type"] != "REPEATING_SECTION" for item in items.values())
    assert [option["id"] for option in items["liczba_podopiecznych"]["options"]] == ["1", "2", "3", "4"]
    queries = [query for item in items.values() for query in states(item)]
    assert queries and all(lint._parse_query(query) for query in queries)
    assert lint.check(form) == []


def _boolean_value(expression: ast.expr) -> bool:
    if isinstance(expression, ast.Constant) and isinstance(expression.value, bool):
        return expression.value
    assert isinstance(expression, ast.BoolOp), ast.dump(expression)
    values = [_boolean_value(value) for value in expression.values]
    return all(values) if isinstance(expression.op, ast.And) else any(values)


def _visible_in_form9(item: dict, answers: dict[str, list[str]]) -> bool:
    for query in states(item):
        resolved = ATOM.sub(
            lambda atom_match: str(decode(atom_match["option"]) in answers.get(decode(atom_match["field"]), [])),
            query,
        )
        if not _boolean_value(ast.parse(resolved, mode="eval").body):
            return False
    return True


@pytest.mark.parametrize("adult", [True, False, None], ids=["adult", "minor", "unanswered"])
@pytest.mark.parametrize(("kind", "count"), [
    ("Stypendium", 4), ("Nagroda", 4), ("Wyróżnienie", 1), ("Wyróżnienie", 2), ("Wyróżnienie", 3), ("Wyróżnienie", 4),
], ids=["scholarship", "award", "distinction-1", "distinction-2", "distinction-3", "distinction-4"])
def test_form9_every_route_has_visible_subject_pages_and_matching_consents(
    kind: str, count: int, adult: bool | None,
) -> None:
    form = generated("analysis_form9.json")
    # Ukryte odpowiedzi pozostają w danych, jak po zmianie rodzaju wniosku albo liczby podopiecznych.
    ward_is_adult = {number: (number % 2 == 1) == adult for number in range(1, 5)} if adult is not None else {}
    answers = {
        "rodzaj_wniosku": [kind],
        "liczba_podopiecznych": [str(count)],
    }
    if adult is not None:
        answers["czy_kandydat_jest_pelnoletni"] = ["Tak" if adult else "Nie"]
    for number, age in ward_is_adult.items():
        answers[f"czy_podopieczny_{number}_jest_pelnoletni"] = ["Tak" if age else "Nie"]

    visible = {}
    for page in form["tabs"][1:-2]:
        sections = [question["field"] for question in page["questions"]]
        visible[page["title"]] = {
            section["title"] for section in sections
            if _visible_in_form9(section, answers)
            and any(_visible_in_form9(item["field"], answers) for item in section["repeatingSectionGrid"])
        }
        assert visible[page["title"]], (page["title"], answers)

    candidate_sections = {"Wybór wniosku", "Dane kandydata"}
    achievement_sections = {"Opinia macierzystego klubu sportowego"}
    if kind == "Stypendium":
        candidate_sections.add("Dyscypliny sportowe kandydata")
    consents = {"Przechowywanie zgód"}
    if kind == "Wyróżnienie":
        achievement_sections.update({"Podopieczni trenera", "Dokumenty podopiecznych"})
        consents.add("Zgoda trenera")
        for number in range(1, count + 1):
            achievement_sections.add(f"Dane podopiecznego {number}")
            if number in ward_is_adult:
                role = "pełnoletniego podopiecznego" if ward_is_adult[number] else "opiekuna podopiecznego"
                consents.add(f"Zgoda {role} {number}")
    else:
        achievement_sections.add("Osiągnięcia sportowca")
        if adult is not None:
            suffix = "stypendium" if kind == "Stypendium" else "nagrody"
            role = "pełnoletniego kandydata" if adult else "opiekuna kandydata"
            consents.add(f"Zgoda {role} do {suffix}")
    assert visible == {"Kandydat": candidate_sections, "Osiągnięcia": achievement_sections, "Zgody": consents}


@pytest.mark.parametrize("applicants", ["ENTITY", "BOTH"])
def test_entity_without_proxy_reuses_only_available_show_conditions(applicants: str) -> None:
    data = _analysis_data(applicants, representative_proof=True, contact=["EMAIL"])
    items = by_tech_name(build_form(FormAnalysis.model_validate(data)))
    assert {ROLE, "pelnomocnictwo", "adres_siedziby", "oplata_skarbowa_pelnomocnictwo_2"}.isdisjoint(items)
    if applicants == "ENTITY":
        assert "podmiot_wniosku" not in items and ON_BEHALF not in items
        expected = []
    else:
        assert [o["name"] for o in items[ON_BEHALF]["options"]] == ["Swoim", "Osoby prawnej lub jednostki organizacyjnej"]
        expected = [LEGAL_ENTITY]
    assert states(items["dane_podmiotu"]) == states(items["potwierdzenie_ze_jestes_reprezentantem"]) == expected
    assert _field_names(items["dane_do_kontaktu"]) == ["adres_e_mail"]


def test_proxy_for_person_can_omit_the_address() -> None:
    items = by_tech_name(build_form(FormAnalysis.model_validate(_analysis_data("PERSON", proxy=True))))
    assert {"adres_zamieszkania", "adres_zamieszkania_osoby_ktorej_jestes_pelnomocnikiem"}.isdisjoint(items)
    for name in ["dane_innej_osoby", "pelnomocnictwo", "oplata_skarbowa_pelnomocnictwo_1"]:
        assert states(items[name]) == [OTHER_PERSON], name


def test_applicant_extra_show_uses_local_names_after_global_collisions() -> None:
    data = _analysis_data("PERSON", applicant_extra_fields=[
        {"label": "Numer <dowodu>", "type": "TEXT_FIELD", "show_if": {"field": "Imię", "equals": "Inne"}},
        {"label": "Imię", "type": "RADIO", "options": ["Z rejestru", "Inne"]},
    ])
    data["subject_pages"][0]["sections"][0]["fields"].append({"label": "Imię", "type": "TEXT_FIELD"})
    form = build_form(FormAnalysis.model_validate(data))
    items = elements(form)
    name = "dodatkowe_dane_wnioskodawcy"
    assert _data_sections(form)[-1] == name
    assert items[("Dane", name)]["title"] == "Dodatkowe dane wnioskodawcy"
    assert _field_names(items[("Dane", name)]) == ["numer_dowodu", "imie_2"]
    assert states(items[("Dane", "numer_dowodu")]) == [atom("Inne", "imie_2", section=name)]
    assert ("Treść sprawy", "imie_3") in items
    assert lint.check(form) == []


@pytest.mark.parametrize(("applicants", "count"), [("PERSON", 96), ("ENTITY", 576), ("BOTH", 2304)])
def test_applicant_decision_matrix_passes_lint(applicants: str, count: int) -> None:
    """Sprawdza też cykle SHOW w sekcjach i polach standardowej strony Dane."""
    extra_fields = [
        {"label": "Kanał kontaktu", "type": "RADIO", "options": ["ePUAP", "Poczta"]},
        {"label": "Adres skrzynki ePUAP", "type": "TEXT_FIELD", "show_if": {"field": "Kanał kontaktu", "equals": "ePUAP"}},
    ]
    values = {
        "proxy": (False, True),
        "applicant_pesel": (False, True),
        "person_address": (False, True),
        "entity_ids": ([], ["NIP"], ["NIP", "REGON"], ["NIP", "REGON", "KRS"]),
        "entity_ids_one_of": (False, True),
        "entity_address": (False, True),
        "representative_proof": (False, True),
        "correspondence_address": (False, True),
        "contact": ([], ["PHONE"], ["PHONE", "EMAIL"]),
        "applicant_extra_fields": ([], extra_fields),
    }
    checked = 0
    for combination in product(*values.values()):
        decisions = dict(zip(values, combination, strict=True))
        try:
            a = FormAnalysis.model_validate(_analysis_data(applicants, **decisions))
        except ValidationError:
            continue
        form = build_form(a)
        assert lint.check(form) == [], (applicants, decisions)
        assert quality.validator_issues(form) == [], (applicants, decisions)
        assert quality.dictionary_issues(form) == [], (applicants, decisions)
        for item in elements(form).values():
            if item["type"] == "RADIO":
                assert len(item["options"]) >= 2, (applicants, decisions, item["techName"])
            if item["type"] == "SECTION":
                assert item["repeatingSectionGrid"], (applicants, decisions, item["techName"])
        checked += 1
    assert checked == count


# --- przypadki brzegowe ---------------------------------------------------------------------------


def test_edge_cases_get_unique_names_titles_and_escaping() -> None:
    form = generated("analysis_edge_cases.json")
    titles = [page["title"] for page in form["tabs"]]
    assert titles == ["Dane", "Dane wniosku", "Dane wniosku (2)", "Opinia 'sołtysa'", "Kontakt i zgody", "Strona końcowa"]
    items = elements(form)
    # Szablon ma pierwszeństwo: „Imię” i „Twoje dane” z przedmiotu dostają _2, _3.
    assert items[("Dane", "imie")]["defaultValue"] == "MLPZ.name"
    assert [q["field"]["techName"] for q in form["tabs"][1]["questions"]] == ["twoje_dane_2", "twoje_dane_3"]
    assert items[("Dane wniosku", "imie_2")]["title"] == items[("Dane wniosku", "imie_3")]["title"] == "Imię"
    # required z analizy: REQUIRED tylko przy polu obowiązkowym.
    assert (items[("Dane wniosku", "imie_2")]["validation"], items[("Dane wniosku", "imie_3")]["validation"]) == (["REQUIRED"], [])
    # Cudzysłów i backslash w opcji, apostrof w tytule strony, warunek między sekcjami. Całe zapytania:
    # porównanie samych składników nie wykryłoby $not ani zmiany and/or.
    expected = {
        ("Dane wniosku", "informacja_o_oplacie_terminie"): atom('Tak, \\"ekspres\\"', "czy_karta_ma_byc_pilna", "Dane wniosku", "twoje_dane_2"),
        ("Dane wniosku", "uwagi"): atom("Nie \\\\ zwykły tryb", "czy_karta_ma_byc_pilna", "Dane wniosku", "twoje_dane_2"),
        ("Dane wniosku (2)", "adres_do_wysylki"): atom("Pocztą", "sposob_odbioru", "Dane wniosku (2)", "odbior_karty"),
        ("Opinia 'sołtysa'", "plik_z_opinia"): atom("Tak", "czy_masz_opinie", "Opinia \\u0027sołtysa\\u0027", "opinia"),
    }
    for key, query in expected.items():
        assert [squash(q) for q in states(items[key])] == [squash(query)], key
    # TEXT_BLOCK z required: true nie dostaje REQUIRED.
    for key in [("Dane wniosku", "informacja_o_oplacie_terminie"), ("Dane wniosku (2)", "wazna_informacja")]:
        assert (items[key]["type"], items[key]["title"], items[key]["validation"]) == ("TEXT_BLOCK", "", [])
    assert "<strong>Informacja o opłacie &amp; terminie</strong>" in items[("Dane wniosku", "informacja_o_oplacie_terminie")]["description"]
    # Tekst od modelu w HTML-u jest escapowany.
    assert "Wpisz dane &lt;dziecka&gt; &amp; opiekuna." in items[("Dane wniosku", "twoje_dane_2")]["description"]
    assert "Np. &lt;termin&gt; &amp; miejsce odbioru." in items[("Dane wniosku", "uwagi")]["description"]
    assert "„Wniosek o kartę mieszkańca &lt;Kwiatkowo&gt; &amp; okolic – opłata" in items[("Dane", "oplata_info_1")]["description"]
    assert "<dziecka>" not in json.dumps(form, ensure_ascii=False)


def test_statements_become_required_consents() -> None:
    items = by_tech_name(generated("analysis_edge_cases.json"))
    consents = items["zgoda"]["consentSectionConfig"]["consents"]
    assert items["zgoda_wyrazenie"]["title"] == "Zgody i oświadczenia"
    assert [c["required"] for c in consents] == [True, True, True]
    assert "klauzulą informacyjną" in consents[0]["description"]
    assert [c["description"] for c in consents[1:]] == [
        "<html><head></head><body><p>Oświadczam, że mieszkam w gminie.</p></body></html>",
        "<html><head></head><body><p>Oświadczam, że dane są prawdziwe.</p></body></html>",
    ]
    assert by_tech_name(generated("fields.json"))["zgoda_wyrazenie"]["title"] == "Zgoda"


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _strings(item)]
    if isinstance(value, list):
        return [text for item in value for text in _strings(item)]
    return []


PRIVACY_TEXT = "Wyrażam zgodę na przetwarzanie moich danych osobowych zgodnie z klauzulą informacyjną."


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_no_placeholder_links(name: str) -> None:
    assert [text for text in _strings(generated(name)) if re.search(r"href\s*=\s*[\"']#", text)] == []


def test_privacy_consent_without_clause_url_is_plain_text() -> None:
    consent = by_tech_name(generated("fields.json"))["zgoda"]["consentSectionConfig"]["consents"][0]
    assert consent == {"description": f"<html><head></head><body><p>{PRIVACY_TEXT}</p></body></html>", "required": True}


def test_privacy_consent_links_to_configured_clause(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(template, "PRIVACY_CLAUSE_URL", "https://bip.example.pl/klauzula-informacyjna")
    description = by_tech_name(generated("fields.json"))["zgoda"]["consentSectionConfig"]["consents"][0]["description"]
    assert '<a href="https://bip.example.pl/klauzula-informacyjna" rel="noopener noreferrer" target="_blank"' in description
    assert 'aria-label="klauzulą informacyjną (link otwiera się w nowej karcie)">klauzulą informacyjną</a>.' in description


def test_addressee_and_signature_parameters() -> None:
    edge = by_tech_name(generated("analysis_edge_cases.json"))
    assert edge["organ_do_ktorego_jest_skladany_wniosek"]["title"] == "Organ, do którego jest składany wniosek"
    assert (edge["nazwa_organu"]["readOnly"], edge["nazwa_organu"]["defaultValue"]) == (True, "Wójt Gminy Kwiatkowo")
    assert "Zanim wyślesz wniosek" in edge["podglad_1"]["description"]
    signed = by_tech_name(generated("fields.json"))
    assert (signed["nazwa_urzedu"]["readOnly"], signed["nazwa_urzedu"]["defaultValue"]) == (True, "Urząd Gminy Ulan-Majorat")
    assert "Zanim przejdziesz do wyboru sposobu podpisu" in signed["podglad_1"]["description"]


# --- walidatory (SZABLONY, rozdz. 5) i determinizm ------------------------------------------------


def _generated_subject_field(field_data: dict) -> dict:
    data = _analysis_data("PERSON")
    data["subject_pages"][0]["sections"][0]["fields"] = [field_data]
    form = build_form(FormAnalysis.model_validate(data))
    assert lint.check(form) == []
    return form["tabs"][1]["questions"][0]["field"]["repeatingSectionGrid"][0]["field"]


@pytest.mark.parametrize(
    ("label", "validator"),
    [
        pytest.param("Numer PESEL", "PESEL", id="pesel"),
        pytest.param("PESEL", "PESEL", id="pesel-standalone"),
        pytest.param("PESEL dziecka", "PESEL", id="pesel-child"),
        pytest.param("Numer NIP wnioskodawcy", "NIP", id="nip"),
        pytest.param("NIP", "NIP", id="nip-standalone"),
        pytest.param("REGON", "REGON", id="regon"),
        pytest.param("KOD POCZTOWY", "ZIP_CODE", id="zip-uppercase"),
        pytest.param("Kod pocztowy", "ZIP_CODE", id="zip-standalone"),
        pytest.param("Kod pocztowy poprzedniego właściciela", "ZIP_CODE", id="zip-previous-owner"),
        pytest.param("Adres e-mail", "EMAIL", id="e-mail"),
        pytest.param("Adres e-mail (opcjonalnie)", "EMAIL", id="email-optional-note"),
        pytest.param("Adres EMAIL", "EMAIL", id="email"),
        pytest.param("Adres poczty elektronicznej", "EMAIL", id="email-phrase"),
        pytest.param("Adres e-mail (adres poczty elektronicznej)", "EMAIL", id="email-same-category"),
        pytest.param("SERIA I NUMER DOWODU OSOBISTEGO", "SERIAL_NUMBER_ID_CARD", id="id-card"),
        pytest.param("Seria i numer dowodu osobistego pełnomocnika", "SERIAL_NUMBER_ID_CARD", id="id-card-proxy"),
        pytest.param("Adres skrzynki ePUAP", "EPUAP", id="epuap"),
        pytest.param("Adres e-doręczeń", "ADE", id="ade-short"),
        pytest.param("Adres do doręczeń elektronicznych", "ADE", id="ade-phrase"),
        pytest.param("ADRES DO DORECZEN ELEKTRONICZNYCH", "ADE", id="ade-ascii-uppercase"),
        pytest.param(unicodedata.normalize("NFD", "Adres e-doręczeń"), "ADE", id="ade-nfd"),
        pytest.param("Numer domu", None, id="house-number"),
        pytest.param("Kod sprawy", None, id="case-code"),
        pytest.param("Opis", None, id="description"),
        pytest.param("Numer rachunku bankowego", None, id="bank-account"),
        pytest.param("Peselowy identyfikator", None, id="pesel-substring"),
        pytest.param("Numer XNIP", None, id="nip-substring"),
        pytest.param("REGON2026", None, id="regon-substring"),
        pytest.param("Kod pocztowyXYZ", None, id="zip-substring"),
        pytest.param("Adres emailowy", None, id="email-substring"),
        pytest.param("Seria i numer dowoduXYZ", None, id="id-card-substring"),
        pytest.param("Adres ePUAP2", None, id="epuap-substring"),
        pytest.param("Adres e-doręczeńXYZ", None, id="ade-substring"),
        pytest.param("NIP lub REGON", None, id="ambiguous-tax-id"),
        pytest.param("PESEL, kod pocztowy lub adres e-mail", None, id="ambiguous-three"),
        pytest.param("Nr telefonu i e-mail", None, id="phone-and-email"),
        pytest.param("Telefon / e-mail wykonawcy", None, id="phone-slash-email"),
        pytest.param("E-mail lub telefon do kontaktu", None, id="email-or-phone"),
        pytest.param("Kod pocztowy i miejscowość", None, id="zip-and-city"),
        pytest.param("Adres (ulica, nr domu, kod pocztowy, miejscowość)", None, id="full-address"),
        pytest.param("PESEL lub numer paszportu", None, id="pesel-or-passport"),
        pytest.param("PESEL lub seria i numer dowodu", None, id="pesel-or-id-card"),
        pytest.param("Pesel (w przypadku braku – numer dokumentu)", None, id="pesel-with-document-alternative"),
        pytest.param("Imię, nazwisko i PESEL kandydata", None, id="name-and-pesel"),
        pytest.param("Data urodzenia i PESEL", None, id="birth-date-and-pesel"),
        pytest.param("NIP; drugi identyfikator", None, id="semicolon-after-nip"),
        pytest.param("PESEL oraz numer sprawy", None, id="pesel-and-case-number"),
        pytest.param("PESEL albo numer sprawy", None, id="pesel-or-case-number"),
        pytest.param("Adres e-mail (tel. kontaktowy)", None, id="email-with-phone-note"),
    ],
)
def test_text_field_validators_follow_label(label: str, validator: str | None) -> None:
    item = _generated_subject_field({"label": label, "type": "TEXT_FIELD", "required": True})
    assert item["title"] == label
    assert item["validation"] == (["REQUIRED", validator] if validator else ["REQUIRED"])


@pytest.mark.parametrize("field_type", ["TEXTAREA", "NUMBER", "DATEPICKER", "RADIO", "CHECKBOX", "SELECT", "TEXT_BLOCK", "FILE_UPLOADER"])
def test_label_does_not_add_type_validator_to_other_fields(field_type: str) -> None:
    data = {"label": "Numer PESEL", "type": field_type, "required": True}
    if field_type in {"RADIO", "CHECKBOX", "SELECT"}:
        data["options"] = ["Podaję", "Nie podaję"]
    item = _generated_subject_field(data)
    assert item["validation"] == ([] if field_type == "TEXT_BLOCK" else ["REQUIRED"])


def test_analysis_field_validators_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    data = _analysis_data(
        "PERSON", person_address=True,
        applicant_extra_fields=[{"label": "Adres skrzynki ePUAP", "type": "TEXT_FIELD", "required": False}],
    )
    data["subject_pages"][0]["sections"][0]["fields"].append({"label": "Numer PESEL", "type": "TEXT_FIELD"})
    analysis = FormAnalysis.model_validate(data)
    items = by_tech_name(build_form(analysis))
    assert items["numer_pesel"]["validation"] == ["REQUIRED", "PESEL"]
    assert items["adres_skrzynki_epuap"]["validation"] == ["EPUAP"]
    assert items["kod_pocztowy"]["validation"] == ["REQUIRED", "ZIP_CODE"]

    monkeypatch.setattr(generator_form, "ADD_VALIDATORS", False)
    form = build_form(analysis)
    assert all(item["validation"] == [] for item in elements(form).values())
    assert lint.check(form) == []


def test_validators_follow_szablony_chapter_5() -> None:
    form = generated("fields.json")
    items = by_tech_name(form)
    assert {name: item["validation"] for name, item in items.items() if item["validation"]} == EXPECTED_VALIDATION
    for read_only in ["imie", "nazwisko", "numer_pesel", "nazwa_urzedu"]:
        assert (items[read_only]["readOnly"], items[read_only]["validation"]) == (True, [])
    example = next(i for q in form["tabs"][0]["questions"] for i in q["field"]["repeatingSectionGrid"] if i["field"]["techName"] == "kod_pocztowy_inna_osoba")
    assert {**example, "field": {k: v for k, v in example["field"].items() if k != "id"}} == SPEC_FIELD_EXAMPLE


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_validators_switch_off_only_changes_validation(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    with_validators = generated(name)
    monkeypatch.setattr(generator_form, "ADD_VALIDATORS", False)
    without = generated(name)
    assert all(item["validation"] == [] for item in elements(without).values())
    for item in elements(with_validators).values():
        item["validation"] = []
    assert without == with_validators


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_same_analysis_gives_identical_json(name: str) -> None:
    assert json.dumps(generated(name), ensure_ascii=False) == json.dumps(generated(name), ensure_ascii=False)



# Bajty JSONResponse z build_form na origin/main (6945cc1), przed zmianami P1.4.
@pytest.mark.parametrize(("name", "digest"), [
    ("analysis_edge_cases.json", "644c19161a35498996b21391cdc8fa05379fdc20d88d21f1a15f97f8cc4b2ea6"),
    ("analysis_entity.json", "e7d1a7cdabc041662aab19b416c27a12ee53ecb245b58acc79fb59359a97f74a"),
    ("analysis_form3.json", "a49e50927df19637423660fa9d8ff4f8b412880a029b39ac88383c3a0bdcbc5b"),
    ("analysis_person.json", "9809cc667fdb9cff0245e503aca590ffef13170956dadeabef0ee129010d9bf5"),
    ("fields.json", "67083bb0603c207fa49b96cd966ad3b9af9498e28c457cc60dca0727a785456b"),
], ids=["edge_cases", "entity", "form3", "person", "fields"])
def test_legacy_form_bytes_match_origin_main(name: str, digest: str) -> None:
    assert sha256(JSONResponse(generated(name)).body).hexdigest() == digest


def _ids(form: dict) -> set[str]:
    return {item["id"] for item in elements(form).values()} | {page["id"] for page in form["tabs"]}


def test_different_analyses_do_not_share_ids() -> None:
    assert _ids(generated("fields.json")).isdisjoint(_ids(generated("analysis_edge_cases.json")))


def test_ids_derive_from_canonical_analysis_json() -> None:
    a = analysis("fields.json")
    canonical = generator_form.canonical_json(a)
    form_namespace = uuid.uuid5(generator_form.ID_NAMESPACE, canonical)
    form = build_form(a)
    assert form["tabs"][0]["id"] == str(uuid.uuid5(form_namespace, "tab/0"))
    assert by_tech_name(form)["imie"]["id"] == str(uuid.uuid5(form_namespace, "field/imie"))


# --- klocki ---------------------------------------------------------------------------------------


def test_slug_matches_coi_tech_names() -> None:
    assert slug("Wybierz, jako kto wnioskujesz") == "wybierz_jako_kto_wnioskujesz"
    assert slug("Adres e-mail") == "adres_e_mail"
    assert slug("Łódź – Śródmieście, ul. Żółta 5") == "lodz_srodmiescie_ul_zolta_5"
    assert slug("?!") == ""
    assert slug("Straße Ørsted Æble Œuvre Đakovo") == "strasse_orsted_aeble_oeuvre_dakovo"
    # Litery, których NFKD nie rozkłada, małe i wielkie.
    assert slug("ł Ł ß ẞ ø Ø æ Æ œ Œ đ Đ") == "l_l_ss_ss_o_o_ae_ae_oe_oe_d_d"


def test_long_tech_names_are_cut_at_word_boundary_before_suffix() -> None:
    names = Names()
    label = "Oświadczenie" + " bardzo długie" * 10
    assert [names.claim(label, "pole") for _ in range(2)] == [
        "oswiadczenie_bardzo_dlugie_bardzo_dlugie_bardzo_dlugie",
        "oswiadczenie_bardzo_dlugie_bardzo_dlugie_bardzo_dlugie_2",
    ]
    # Granica słowa dokładnie na limicie (nie cofamy się do wcześniejszego _) i słowo dłuższe niż limit.
    assert Names().claim("ab " + "c" * 57 + " d", "pole") == "ab_" + "c" * 57
    unbroken = Names()
    assert [unbroken.claim("x" * 70, "pole") for _ in range(2)] == ["x" * 60, "x" * 60 + "_2"]


def test_names_give_template_priority_and_numbered_collisions() -> None:
    names = Names()
    names.reserve("imie")
    assert [names.claim("Imię", "pole") for _ in range(3)] == ["imie_2", "imie_3", "imie_4"]
    assert names.claim("Imie 2", "pole") == "imie_2_2"
    assert names.claim("?", "pole") == "pole"
    with pytest.raises(ValueError, match="dwa razy"):
        names.reserve("imie")


def nfd(text: str) -> str:
    return unicodedata.normalize("NFD", text)


def test_page_titles_compare_after_nfc_and_casefold() -> None:
    assert nfd("Strona końcowa") != "Strona końcowa"
    titles = [nfd("Strona końcowa"), "DANE", "dane", "Wybór miejsca", nfd("Wybór miejsca"), "KONTAKT I ZGODY"]
    assert subject_page_titles(titles) == [
        f"{nfd('Strona końcowa')} wniosku",
        "DANE wniosku",
        "dane wniosku (2)",
        "Wybór miejsca",
        f"{nfd('Wybór miejsca')} (2)",
        "KONTAKT I ZGODY wniosku",
    ]


def test_choice_options_use_name_as_id() -> None:
    assert choice_options(["Tak", "tak!", "?"]) == [
        {"id": "Tak", "name": "Tak", "techName": "tak"},
        {"id": "tak!", "name": "tak!", "techName": "tak_2"},
        {"id": "?", "name": "?", "techName": "opcja"},
    ]


def test_jsonata_literals_escape_quotes_and_backslashes() -> None:
    assert jsonata_string('a"b\\c\nd') == '"a\\"b\\\\c\\nd"'
    assert jsonata_string("it's \"ok\"", "'") == "'it\\u0027s \"ok\"'"
    for text in ['a"b\\c\nd\x01', "it's", "zwykły tekst"]:
        for quote in "\"'":
            assert decode(jsonata_string(text, quote)) == text
