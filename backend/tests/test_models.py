"""P0: wspólne modele i fixture są spójne. Te testy pilnują umowy między modułami."""

import html
import json
import re
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError

from app import lint, models
from app.generator import build_form
from app.models import (
    MAX_IMAGES,
    MAX_IMAGES_BYTES,
    ExtractedDocument,
    FormAnalysis,
    SourceFormat,
)

FIXTURES = Path(__file__).parent / "fixtures"
# Nagłówek PNG nie jest poprawnym UTF-8, więc zwykła serializacja bytes do JSON-a by się wywróciła.
PNG_BYTES = b"\x89PNG\r\n\x1a\n\xff\xd8"

RADIO = "Wybierz, co mamy zrobić z nadpłatą"
TO_FUTURE_TAX = "Zaliczyć na poczet przyszłego zobowiązania podatkowego"
TO_ACCOUNT = "Zwrócić przelewem na rachunek bankowy"
FIXTURE_PAGES = ["Informacje o nadpłacie"]
FIXTURE_FIELDS = [
    ("Informacje o nadpłacie", "Podatek, którego dotyczy nadpłata", "TEXT_FIELD", []),
    ("Informacje o nadpłacie", "Kwota", "NUMBER", []),
    ("Informacje o nadpłacie", "Uzasadnienie", "TEXTAREA", []),
    ("Rozliczenie nadpłaty", RADIO, "RADIO", [TO_FUTURE_TAX, TO_ACCOUNT]),
    ("Rozliczenie nadpłaty", "Nazwa podatku", "TEXT_FIELD", []),
    ("Rozliczenie nadpłaty", "Numer rachunku", "TEXT_FIELD", []),
    ("Korekta deklaracji", "Plik deklaracji podatkowej", "FILE_UPLOADER", []),
]
FIXTURE_SHOW_IF = {"Nazwa podatku": (RADIO, TO_FUTURE_TAX), "Numer rachunku": (RADIO, TO_ACCOUNT)}

# Każdy przykład w opisach schematu trafia do modelu. Nowy przykład wymaga dopisania tutaj,
# czyli świadomego sprawdzenia, że nie pochodzi ze zbioru kontrolnego ani z formularzy do oceny.
SCHEMA_EXAMPLES = {
    "Numer rachunku",
    "Rozliczenie nadpłaty",
    "Informacje o nadpłacie",
    "Urząd Gminy Ulan-Majorat",
    "Burmistrz Miasta Lipowo",
    "Wniosek o stwierdzenie nadpłaty podatku",
    "Oświadczam, że…",
}

SHOW_QUERY = re.compile(
    r"^\(\"(?P<option>[^\"]+)\" in tabs\['[^']+' in title\]\.questions\['[^']+' in field\.techName\]"
    r"\.field\.repeatingSectionGrid\['(?P<source>[^']+)' in field\.techName\]\.field\.__userAnswer\)$"
)


def fields_text() -> str:
    return (FIXTURES / "fields.json").read_text(encoding="utf-8")


def fields_json() -> dict:
    return json.loads(fields_text())


def sections(data: dict) -> list[dict]:
    return data["subject_pages"][0]["sections"]


def field(data: dict, label: str) -> dict:
    return next(f for section in sections(data) for f in section["fields"] if f["label"] == label)


def model_prompt_text() -> str:
    return json.dumps(FormAnalysis.model_json_schema(), ensure_ascii=False)


def test_fixture_fields_keeps_its_fields_and_conditions() -> None:
    analysis = FormAnalysis.model_validate(fields_json())
    assert analysis.title == "Wniosek o stwierdzenie nadpłaty podatku"
    assert [page.title for page in analysis.subject_pages] == FIXTURE_PAGES
    flat = [(s.title, f) for page in analysis.subject_pages for s in page.sections for f in s.fields]
    assert [(title, f.label, f.type.value, f.options) for title, f in flat] == FIXTURE_FIELDS
    assert {f.label: (f.show_if.field, f.show_if.equals) for _, f in flat if f.show_if} == FIXTURE_SHOW_IF


def test_fixture_fields_matches_working_reference(coi_working_reference: dict) -> None:
    subject_tabs = coi_working_reference["tabs"][1:-2]
    assert [tab["title"] for tab in subject_tabs] == FIXTURE_PAGES
    reference_fields, reference_show_if = [], {}
    for tab in subject_tabs:
        grid = [(q["field"], item["field"]) for q in tab["questions"] for item in q["field"]["repeatingSectionGrid"]]
        title_of = {f["techName"]: f["title"] for _, f in grid}
        for section, f in grid:
            reference_fields.append((section["title"], f["title"], f["type"], [o["name"] for o in f["options"]]))
            for state in f["states"]:
                query = SHOW_QUERY.match(state["query"])
                assert state["type"] == "SHOW" and query, state
                reference_show_if[f["title"]] = (title_of[query["source"]], query["option"])
    assert reference_fields == FIXTURE_FIELDS
    assert reference_show_if == FIXTURE_SHOW_IF


def _dependents_on_second_page(data: dict) -> None:
    moved = [f for section in sections(data) for f in section["fields"] if "show_if" in f]
    for section in sections(data):
        section["fields"] = [f for f in section["fields"] if "show_if" not in f]
    data["subject_pages"].append({"title": "Druga strona", "sections": [{"title": "Sekcja", "fields": moved}]})


# (opis, zmiana w fields.json, ostatni element loc błędu albo None, fragment typu lub treści błędu)
INVALID_ANALYSES: list[tuple[str, Callable[[dict], object], str | None, str]] = [
    ("pusty tytuł wniosku", lambda d: d.update(title="  "), "title", "string_too_short"),
    ("tytuł ponad 255 znaków", lambda d: d.update(title="x" * 256), "title", "string_too_long"),
    ("pusta nazwa adresata", lambda d: d["addressee"].update(name=""), "name", "string_too_short"),
    ("pusty tytuł strony", lambda d: d["subject_pages"][0].update(title=" "), "title", "string_too_short"),
    ("pusty tytuł sekcji", lambda d: sections(d)[0].update(title=""), "title", "string_too_short"),
    ("pusta etykieta pola", lambda d: field(d, "Kwota").update(label=" "), "label", "string_too_short"),
    ("pusta opcja", lambda d: field(d, RADIO)["options"].append(" "), 2, "string_too_short"),
    ("puste oświadczenie", lambda d: d.update(statements=[""]), 0, "string_too_short"),
    ("pusta etykieta w show_if", lambda d: field(d, "Numer rachunku")["show_if"].update(field=" "), "field", "string_too_short"),
    ("pusta opcja w show_if", lambda d: field(d, "Numer rachunku")["show_if"].update(equals=""), "equals", "string_too_short"),
    ("brak stron", lambda d: d.update(subject_pages=[]), "subject_pages", "too_short"),
    ("strona bez sekcji", lambda d: d["subject_pages"][0].update(sections=[]), "sections", "too_short"),
    ("sekcja bez pól", lambda d: sections(d)[0].update(fields=[]), "fields", "too_short"),
    ("nieznany typ pola", lambda d: field(d, "Kwota").update(type="TEXT"), "type", "enum"),
    ("RADIO bez opcji", lambda d: field(d, "Kwota").update(type="RADIO"), None, "wymaga co najmniej jednej opcji"),
    ("CHECKBOX bez opcji", lambda d: field(d, "Kwota").update(type="CHECKBOX"), None, "wymaga co najmniej jednej opcji"),
    ("SELECT bez opcji", lambda d: field(d, "Kwota").update(type="SELECT"), None, "wymaga co najmniej jednej opcji"),
    ("powtórzona opcja", lambda d: field(d, RADIO)["options"].append(TO_ACCOUNT), None, "powtórzone opcje"),
    ("opcje przy polu tekstowym", lambda d: field(d, "Kwota").update(options=["a", "b"]), None, "nie przyjmuje opcji"),
    ("show_if: nie ma takiego pola", lambda d: field(d, "Numer rachunku")["show_if"].update(field="Brak"), None, "nie ma pola"),
    ("show_if: nie ma takiej opcji", lambda d: field(d, "Numer rachunku")["show_if"].update(equals="Brak"), None, "nie ma opcji"),
    ("show_if: zmieniona opcja źródła", lambda d: field(d, RADIO).update(options=[TO_FUTURE_TAX, "Inna"]), None, "nie ma opcji"),
    ("show_if: źródło nie jest polem wyboru", lambda d: field(d, "Numer rachunku")["show_if"].update(field="Kwota"), None, "nie jest polem wyboru"),
    ("show_if: pole wskazuje samo siebie", lambda d: field(d, RADIO).update(show_if={"field": RADIO, "equals": TO_ACCOUNT}), None, "wskazuje to samo pole"),
    ("show_if: etykieta źródła powtórzona", lambda d: field(d, "Kwota").update(label=RADIO), None, "niejednoznaczna"),
    ("nieznany klucz: analiza", lambda d: d.update(validation=["PESEL"]), "validation", "extra_forbidden"),
    ("nieznany klucz: adresat", lambda d: d["addressee"].update(street="x"), "street", "extra_forbidden"),
    ("nieznany klucz: strona", lambda d: d["subject_pages"][0].update(type="MAIN"), "type", "extra_forbidden"),
    ("nieznany klucz: sekcja", lambda d: sections(d)[0].update(techName="x"), "techName", "extra_forbidden"),
    ("nieznany klucz: pole", lambda d: field(d, "Kwota").update(validation=["REQUIRED"]), "validation", "extra_forbidden"),
    ("nieznany klucz: show_if", lambda d: field(d, "Numer rachunku")["show_if"].update(negate=True), "negate", "extra_forbidden"),
]


@pytest.mark.parametrize(("change", "loc", "fragment"), [case[1:] for case in INVALID_ANALYSES], ids=[case[0] for case in INVALID_ANALYSES])
def test_form_analysis_rejects_invalid_data(change: Callable[[dict], object], loc: str | int | None, fragment: str) -> None:
    data = fields_json()
    change(data)
    with pytest.raises(ValidationError) as caught:
        FormAnalysis.model_validate(data)
    errors = [f"{error['type']} {error['msg']}" for error in caught.value.errors() if loc is None or error["loc"][-1] == loc]
    assert any(fragment in error for error in errors), caught.value.errors()


def test_repeated_labels_are_allowed_when_no_show_if_points_at_them() -> None:
    data = fields_json()
    sections(data)[2]["fields"].append({"label": "  Kwota ", "type": "NUMBER"})
    analysis = FormAnalysis.model_validate(data)
    labels = [f.label for s in analysis.subject_pages[0].sections for f in s.fields]
    assert labels.count("Kwota") == 2



def test_show_if_accepts_source_on_an_earlier_page() -> None:
    data = fields_json()
    _dependents_on_second_page(data)
    analysis = FormAnalysis.model_validate(data)
    moved = analysis.subject_pages[1].sections[0].fields
    assert {f.label: (f.show_if.field, f.show_if.equals) for f in moved if f.show_if} == FIXTURE_SHOW_IF


@pytest.mark.parametrize("source_type", ["RADIO", "CHECKBOX", "SELECT"])
def test_subject_fields_and_sections_accept_compound_conditions(source_type: str) -> None:
    data = fields_json()
    field(data, RADIO).update(type=source_type, options=[TO_ACCOUNT, TO_FUTURE_TAX, "Inny sposób"])
    field(data, "Kwota").update(type="RADIO", options=["Potwierdzona", "Szacunkowa"])
    alternatives = {"field": RADIO, "equals": TO_ACCOUNT, "any_of": ["Inny sposób"]}
    confirmed = {"field": "Kwota", "equals": "Potwierdzona"}
    field(data, "Numer rachunku").update(show_if=alternatives, show_if_all=[confirmed])
    sections(data)[2].update(show_if=alternatives, show_if_all=[confirmed])

    analysis = FormAnalysis.model_validate(data)
    account = analysis.subject_pages[0].sections[1].fields[2]
    correction = analysis.subject_pages[0].sections[2]
    for item in (account, correction):
        assert item.show_if.model_dump() == alternatives
        assert item.show_if_all[0].equals == "Potwierdzona"


@pytest.mark.parametrize(
    ("options", "message"),
    [
        (["Nie ma takiej opcji"], "nie ma opcji 'Nie ma takiej opcji'"),
        ([TO_ACCOUNT], "powtórzone opcje"),
        ([TO_FUTURE_TAX, TO_FUTURE_TAX], "powtórzone opcje"),
    ],
)
def test_show_if_rejects_invalid_alternatives(options: list[str], message: str) -> None:
    data = fields_json()
    field(data, "Numer rachunku")["show_if"]["any_of"] = options
    with pytest.raises(ValidationError, match=message):
        FormAnalysis.model_validate(data)


@pytest.mark.parametrize("location", ["field", "section", "page"])
def test_subject_show_if_rejects_source_after_dependent(location: str) -> None:
    data = fields_json()
    payment = sections(data)[1]["fields"]
    if location == "field":
        payment.reverse()
    elif location == "section":
        sections(data).insert(2, {"title": "Sposób rozliczenia", "fields": [payment.pop(0)]})
    else:
        _dependents_on_second_page(data)
        data["subject_pages"].reverse()
    with pytest.raises(ValidationError, match="źródło .* musi być przed elementem zależnym"):
        FormAnalysis.model_validate(data)


def test_section_show_if_rejects_source_inside_that_section() -> None:
    data = fields_json()
    sections(data)[1]["show_if"] = {"field": RADIO, "equals": TO_ACCOUNT}
    with pytest.raises(ValidationError, match="leży wewnątrz ukrywanej sekcji"):
        FormAnalysis.model_validate(data)


def test_subject_show_if_rejects_ambiguous_source_across_pages() -> None:
    data = fields_json()
    _dependents_on_second_page(data)
    data["subject_pages"][1]["sections"][0]["fields"].append({"label": RADIO, "type": "TEXT_FIELD"})
    with pytest.raises(ValidationError, match="etykieta .* jest niejednoznaczna"):
        FormAnalysis.model_validate(data)


@pytest.mark.parametrize("target", ["field", "section"])
def test_show_if_all_validates_each_condition(target: str) -> None:
    data = fields_json()
    dependent = field(data, "Numer rachunku") if target == "field" else sections(data)[2]
    dependent["show_if_all"] = [
        {"field": RADIO, "equals": TO_ACCOUNT},
        {"field": RADIO, "equals": "Brak"},
    ]
    with pytest.raises(ValidationError, match=r"show_if_all\[1\] .* nie ma opcji 'Brak'"):
        FormAnalysis.model_validate(data)


def test_form_analysis_schema_is_json_for_the_model() -> None:
    schema = FormAnalysis.model_json_schema()
    json.dumps(schema)
    assert {"title", "addressee", "subject_pages"} <= set(schema["required"])
    assert schema["additionalProperties"] is False


def test_schema_examples_are_the_reviewed_ones() -> None:
    assert set(re.findall(r"'([^']+)'", model_prompt_text())) == SCHEMA_EXAMPLES


def test_applicant_decisions_are_required_without_defaults() -> None:
    schema = FormAnalysis.model_json_schema()
    assert {"applicants", "applicant"} <= set(schema["required"])
    assert all("default" not in schema["properties"][key] for key in ("applicants", "applicant"))
    applicant_schema = schema["$defs"]["ApplicantData"]
    assert applicant_schema["additionalProperties"] is False
    assert set(applicant_schema["required"]) == applicant_schema["properties"].keys() == {
        "proxy", "applicant_pesel", "person_address", "entity_ids", "entity_ids_one_of", "entity_address",
        "representative_proof", "correspondence_address", "contact", "applicant_extra_fields",
    }
    assert all("default" not in prop for prop in applicant_schema["properties"].values())


def test_applicant_accepts_explicit_false_and_empty_lists() -> None:
    data = fields_json()
    data["applicants"] = "PERSON"
    data["applicant"] = {
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
    }
    analysis = FormAnalysis.model_validate(data)
    assert analysis.applicant.model_dump(mode="json") == data["applicant"]


def test_applicant_accepts_choice_of_two_entity_ids() -> None:
    data = fields_json()
    data["applicant"].update(entity_ids=["NIP", "REGON"], entity_ids_one_of=True)
    applicant = FormAnalysis.model_validate(data).applicant
    assert applicant.entity_ids_one_of is True
    assert applicant.entity_ids == ["NIP", "REGON"]


@pytest.mark.parametrize(
    ("fixture_name", "changes", "message"),
    [
        pytest.param("analysis_person.json", {"entity_ids": ["NIP"]}, "identyfikatorów podmiotu", id="person-entity-ids"),
        pytest.param(
            "analysis_person.json", {"entity_ids": ["NIP", "REGON"], "entity_ids_one_of": True},
            "nie wybiera jednego identyfikatora podmiotu", id="person-one-of",
        ),
        pytest.param("analysis_person.json", {"entity_address": True}, "adresu siedziby", id="person-entity-address"),
        pytest.param("analysis_person.json", {"representative_proof": True}, "odpisu z rejestru", id="person-representative-proof"),
        pytest.param("analysis_entity.json", {"applicant_pesel": True}, "PESEL wnioskodawcy", id="entity-pesel"),
        pytest.param("analysis_entity.json", {"person_address": True}, "adresu zamieszkania", id="entity-person-address"),
        pytest.param(
            "fields.json", {"entity_ids": ["NIP"], "entity_ids_one_of": True},
            "co najmniej dwóch identyfikatorów", id="one-of-with-one-id",
        ),
        pytest.param(
            "fields.json", {"entity_ids": [], "entity_ids_one_of": True},
            "co najmniej dwóch identyfikatorów", id="one-of-with-no-ids",
        ),
        pytest.param("fields.json", {"entity_ids": ["NIP", "NIP"]}, "Identyfikatory podmiotu nie mogą się powtarzać", id="duplicate-ids"),
        pytest.param("fields.json", {"contact": ["EMAIL", "EMAIL"]}, "Pola kontaktowe nie mogą się powtarzać", id="duplicate-contacts"),
    ],
)
def test_applicant_rejects_inconsistent_decisions(fixture_name: str, changes: dict, message: str) -> None:
    data = json.loads((FIXTURES / fixture_name).read_text(encoding="utf-8"))
    data["applicant"].update(changes)
    with pytest.raises(ValidationError, match=message):
        FormAnalysis.model_validate(data)


@pytest.fixture
def analysis_with_extra_fields() -> dict:
    data = fields_json()
    data["applicant"]["applicant_extra_fields"] = [
        {"label": "Rodzaj dokumentu", "type": "RADIO", "options": ["Dowód osobisty", "Paszport"]},
        {
            "label": "Numer paszportu",
            "type": "TEXT_FIELD",
            "show_if": {"field": "Rodzaj dokumentu", "equals": "Paszport"},
        },
    ]
    return data


def test_applicant_show_if_accepts_choice_from_same_list(analysis_with_extra_fields: dict) -> None:
    fields = FormAnalysis.model_validate(analysis_with_extra_fields).applicant.applicant_extra_fields
    assert fields[1].show_if is not None
    assert fields[1].show_if.field == fields[0].label
    assert fields[1].show_if.equals == fields[0].options[1]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        pytest.param(
            lambda f: f[1]["show_if"].update(field=RADIO, equals=TO_ACCOUNT),
            "w dodatkowych danych wnioskodawcy nie ma pola", id="outside-list",
        ),
        pytest.param(
            lambda f: f.append({"label": "Rodzaj dokumentu", "type": "TEXT_FIELD"}),
            "etykieta 'Rodzaj dokumentu' jest niejednoznaczna", id="ambiguous-label",
        ),
        pytest.param(
            lambda f: f[0].update(show_if={"field": "Rodzaj dokumentu", "equals": "Paszport"}),
            "wskazuje to samo pole", id="self-reference",
        ),
        pytest.param(
            lambda f: f[0].update(type="TEXT_FIELD", options=[]),
            "'Rodzaj dokumentu' nie jest polem wyboru", id="not-a-choice",
        ),
        pytest.param(
            lambda f: f[1]["show_if"].update(equals="Karta pobytu"),
            "nie ma opcji 'Karta pobytu'", id="missing-option",
        ),
    ],
)
def test_applicant_show_if_rejects_invalid_reference(
    analysis_with_extra_fields: dict, change: Callable[[list[dict]], object], message: str,
) -> None:
    change(analysis_with_extra_fields["applicant"]["applicant_extra_fields"])
    with pytest.raises(ValidationError, match=message):
        FormAnalysis.model_validate(analysis_with_extra_fields)


def test_applicant_show_if_still_accepts_later_source_in_same_list(analysis_with_extra_fields: dict) -> None:
    analysis_with_extra_fields["applicant"]["applicant_extra_fields"].reverse()
    fields = FormAnalysis.model_validate(analysis_with_extra_fields).applicant.applicant_extra_fields
    assert fields[0].show_if.field == fields[1].label


@pytest.mark.parametrize("condition_key", ["any_of", "show_if_all"])
def test_applicant_extra_fields_reject_compound_conditions(
    analysis_with_extra_fields: dict, condition_key: str,
) -> None:
    dependent = analysis_with_extra_fields["applicant"]["applicant_extra_fields"][1]
    if condition_key == "any_of":
        dependent["show_if"]["any_of"] = ["Dowód osobisty"]
    else:
        dependent["show_if_all"] = [dependent.pop("show_if")]
    with pytest.raises(ValidationError, match="tylko show_if z field i equals"):
        FormAnalysis.model_validate(analysis_with_extra_fields)


@pytest.mark.parametrize(
    ("original", "normalized"),
    [
        pytest.param("x\ud83d", "x\ufffd", id="lone-high"),
        pytest.param("x\ude00", "x\ufffd", id="lone-low"),
        pytest.param("x\ud83d\ude00", "x😀", id="surrogate-pair"),
        pytest.param("x😀", "x😀", id="emoji"),
    ],
)
def test_analysis_normalizes_unicode_and_builds_utf8(original: str, normalized: str) -> None:
    data = fields_json()
    data["title"] = f" {original} "
    data["subject_pages"][0]["sections"] = [{
        "title": "Odbiór",
        "description": original,
        "fields": [
            {
                "label": f"Wybór {normalized}",
                "type": "RADIO",
                "options": [f" {original} "],
            },
            {
                "label": "Uwagi",
                "type": "TEXT_FIELD",
                "description": original,
                "show_if": {"field": f" Wybór {original} ", "equals": f" {original} "},
            },
        ],
    }]
    analysis = FormAnalysis.model_validate(data)
    subject = analysis.subject_pages[0].sections[0]
    source, target = subject.fields
    assert analysis.title == normalized
    assert subject.description == target.description == normalized
    assert source.options == [normalized]
    assert target.show_if is not None
    assert (target.show_if.field, target.show_if.equals) == (source.label, normalized)
    encoded = json.dumps(build_form(analysis), ensure_ascii=False).encode("utf-8")
    assert normalized.encode("utf-8") in encoded


def test_duplicate_options_are_checked_after_unicode_normalization() -> None:
    data = fields_json()
    field(data, RADIO)["options"] = ["Opcja \ud83d", "Opcja \ude00"]
    with pytest.raises(ValidationError, match="powtórzone opcje"):
        FormAnalysis.model_validate(data)


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*.json")), ids=lambda path: path.name)
def test_every_analysis_fixture_builds_and_passes_lint(path: Path) -> None:
    analysis = FormAnalysis.model_validate_json(path.read_text(encoding="utf-8"))
    assert lint.check(build_form(analysis)) == []


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _strings(item)]
    if isinstance(value, list):
        return [text for item in value for text in _strings(item)]
    return []


def _plain(text: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text)).split()).casefold()


def _coi_texts(form: dict) -> set[str]:
    texts = {form["title"]}
    for tab in form["tabs"]:
        texts.add(tab["title"])
        for question in tab["questions"]:
            for item in [question, *question["field"].get("repeatingSectionGrid", [])]:
                texts.update(item["field"].get(key, "") for key in ("title", "description", "tooltipMessage"))
                texts.update(option["name"] for option in item["field"].get("options", []))
                default = item["field"].get("defaultValue")
                if isinstance(default, str):
                    texts.add(default)
    return {plain for plain in map(_plain, texts) if len(plain) >= 4}


def test_control_set_does_not_leak_into_model_prompt_or_fixtures(
    coi_control_reference: dict, coi_working_reference: dict
) -> None:
    control_only = _coi_texts(coi_control_reference) - _coi_texts(coi_working_reference)
    # REGON jest niezależną wartością kontraktu MVP. Wyłączamy tylko samodzielną etykietę.
    control_only.discard("regon")
    assert control_only, "zbiór kontrolny nie ma własnych tekstów, test nic by nie sprawdzał"
    fixtures = sorted(FIXTURES.glob("*.json"))
    assert "fields.json" in [path.name for path in fixtures]
    # Wartości, nie surowy plik: w tekście JSON-a cudzysłowy i znaki nowej linii są escapowane.
    sources = {"schemat FormAnalysis": _strings(FormAnalysis.model_json_schema())}
    sources |= {path.name: _strings(json.loads(path.read_text(encoding="utf-8"))) for path in fixtures}
    leaks = {name: sorted(text for text in control_only if text in _plain(" ".join(texts))) for name, texts in sources.items()}
    assert {name: found for name, found in leaks.items() if found} == {}


def test_extracted_document_minimal() -> None:
    doc = ExtractedDocument(source_format="pdf", text="WNIOSEK")
    assert doc.source_format is SourceFormat.PDF
    assert doc.ocr_used is False and doc.images == [] and doc.warnings == []


def test_source_format_is_a_closed_set() -> None:
    assert {source.value for source in SourceFormat} == {"pdf", "doc", "docx", "ods", "xlsx", "jpg", "png"}
    for rejected in ["jpeg", "exe", "PDF", ""]:
        with pytest.raises(ValidationError):
            ExtractedDocument(source_format=rejected, text="")


def test_extracted_document_rejects_unknown_keys() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ExtractedDocument(source_format="pdf", text="", ocr=True)


def test_images_stay_out_of_json_dump_and_repr() -> None:
    doc = ExtractedDocument(source_format="png", text="", ocr_used=True, images=[PNG_BYTES])
    assert doc.images == [PNG_BYTES]
    assert "images" not in doc.model_dump()
    assert json.loads(doc.model_dump_json()) == {"source_format": "png", "text": "", "ocr_used": True, "warnings": []}
    assert "images" not in repr(doc)


def test_image_limits_are_the_decided_ones() -> None:
    assert (MAX_IMAGES, MAX_IMAGES_BYTES) == (20, 40 * 1024 * 1024)


def test_images_count_is_limited() -> None:
    ExtractedDocument(source_format="pdf", text="", images=[b"x"] * MAX_IMAGES)
    with pytest.raises(ValidationError, match="too_long") as caught:
        ExtractedDocument(source_format="pdf", text="TAJNA TRESC", images=[b"x"] * (MAX_IMAGES + 1))
    assert "TAJNA TRESC" not in str(caught.value) and "input_value" not in str(caught.value)


def test_images_total_size_is_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(models, "MAX_IMAGES_BYTES", 8)
    ExtractedDocument(source_format="pdf", text="", images=[b"12345", b"123"])
    with pytest.raises(ValidationError, match="limit to 8"):
        ExtractedDocument(source_format="pdf", text="", images=[b"12345", b"1234"])
