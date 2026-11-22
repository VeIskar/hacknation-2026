"""P4 na danych syntetycznych i fixture'ach analizy."""

import unicodedata

import pytest
from test_generator import _analysis_data, by_tech_name, generated

from app import lint, quality
from app.generator import build_form
from app.models import ExtractedDocument, FormAnalysis

NEUTRAL = "Uzasadnienie sprawy jest opisane w formularzu. " * 6
COUNTRIES = ["Polska", "Czechy", "Słowacja", "Litwa", "Niemcy", "Austria"]


def _document(text: str) -> ExtractedDocument:
    return ExtractedDocument(source_format="docx", text=text)


def _valid(data: dict) -> FormAnalysis:
    return FormAnalysis.model_validate(data)


def _subject_fields(analysis: FormAnalysis) -> list[str]:
    return [field.label for page in analysis.subject_pages for section in page.sections for field in section.fields]


@pytest.mark.parametrize(("key", "on", "off", "evidence", "non_evidence"), [
    ("applicant_pesel", True, False, ["PESEL"], ""),
    ("proxy", True, False, ["pełnomocnictwo", "Pelnomocnik"], ""),
    ("representative_proof", True, False, ["KRS", "rejestrze", "odpisem", "pełnomocnictwo", "reprezentanta"], ""),
    ("correspondence_address", True, False, ["korespondencję"], ""),
    ("person_address", True, False, ["zamieszkania", "zameldowania", "adres"], ""),
    ("entity_address", True, False, ["siedziby", "adres"], ""),
    ("entity_ids", ["NIP"], [], ["NIP:"], "poprzedniknip"),
    ("entity_ids", ["REGON"], [], ["REGON-u"], ""),
    ("entity_ids", ["KRS"], [], ["KRS:"], "przedkrs"),
    ("contact", ["PHONE"], [], ["telefonu", "tel."], "hotel"),
    ("contact", ["EMAIL"], [], ["e-mail", "email", "poczty elektronicznej", "pocztą\nelektroniczną"], ""),
])
def test_ground_disables_only_unsupported_applicant_decisions(
    key: str, on: object, off: object, evidence: list[str], non_evidence: str,
) -> None:
    analysis = _valid(_analysis_data("BOTH", **{key: on}))
    for phrase in evidence:
        supported = quality.ground(analysis, _document(NEUTRAL + unicodedata.normalize("NFD", phrase.upper())))
        assert supported.analysis == analysis
        assert supported.correction_count == 0

    unsupported = quality.ground(analysis, _document(NEUTRAL + non_evidence))
    assert getattr(unsupported.analysis.applicant, key) == off
    assert getattr(analysis.applicant, key) == on
    assert unsupported.correction_count == 1
    assert FormAnalysis.model_validate(unsupported.analysis.model_dump(mode="json")) == unsupported.analysis


def test_ground_preserves_order_and_disables_alternative_ids_when_one_remains() -> None:
    analysis = _valid(_analysis_data("ENTITY", entity_ids=["KRS", "REGON", "NIP"], entity_ids_one_of=True))
    two = quality.ground(analysis, _document(NEUTRAL + " KRS, NIP."))
    assert two.analysis.applicant.entity_ids == ["KRS", "NIP"]
    assert two.analysis.applicant.entity_ids_one_of
    one = quality.ground(analysis, _document(NEUTRAL + " NIP."))
    assert one.analysis.applicant.entity_ids == ["NIP"]
    assert not one.analysis.applicant.entity_ids_one_of
    assert one.correction_count == 3


def test_ground_does_not_enable_any_applicant_decision() -> None:
    analysis = _valid(_analysis_data("BOTH"))
    text = NEUTRAL + "PESEL, NIP, REGON, KRS, pełnomocnictwo, odpis, siedziba, adres, korespondencja, telefon, e-mail."
    result = quality.ground(analysis, _document(text))
    assert result.analysis == analysis
    assert result.correction_count == 0


@pytest.mark.parametrize("length", [199, 200])
def test_ground_threshold_after_normalization(length: int) -> None:
    analysis = _valid(_analysis_data("PERSON", proxy=True))
    text = unicodedata.normalize("NFD", "ą" * length)
    result = quality.ground(analysis, _document(text))
    if length == 199:
        assert result.analysis == analysis
        assert result.notes == ["za mało tekstu"]
        assert result.correction_count == 0
    else:
        assert not result.analysis.applicant.proxy
        assert result.correction_count == 1


def test_ground_matches_closed_label_list_and_removes_empty_pages_and_sections() -> None:
    exact = (
        "imię", "nazwisko", "imię i nazwisko", "nazwisko i imię", "pesel", "numer pesel",
        "nip", "regon", "krs", "numer krs", "adres zamieszkania", "adres siedziby",
        "adres do korespondencji", "telefon", "numer telefonu", "telefon kontaktowy",
        "e-mail", "adres e-mail", "adres poczty elektronicznej", "nazwa wnioskodawcy",
        "imię i nazwisko wnioskodawcy",
    )
    distinct = ["Imię kandydata", "Telefon opiekuna", "Numer PESEL osoby wskazanej"]
    # Każdy duplikat ma decyzję szablonu z przesłanką w tekście, więc szablon go pokaże.
    data = _analysis_data(
        "BOTH", applicant_pesel=True, entity_ids=["NIP", "REGON", "KRS"], person_address=True,
        entity_address=True, correspondence_address=True, contact=["PHONE", "EMAIL"],
    )
    data["subject_pages"] = [
        {"title": "Duplikaty", "sections": [{
            "title": "Identyfikacja",
            "fields": [{"label": unicodedata.normalize("NFD", label.upper()), "type": "TEXT_FIELD"} for label in exact],
        }]},
        {"title": "Kandydat", "sections": [
            {"title": "Kontakt", "fields": [{"label": "Telefon", "type": "TEXT_FIELD"}]},
            {"title": "Dane osoby", "fields": [{"label": label, "type": "TEXT_FIELD"} for label in distinct]},
        ]},
    ]
    analysis = _valid(data)
    evidence = " PESEL, NIP, REGON, KRS, adres zamieszkania i siedziby, korespondencja, telefon, e-mail."
    grounded = quality.ground(analysis, _document(NEUTRAL + evidence))
    assert grounded.analysis.applicant == analysis.applicant
    assert [page.title for page in grounded.analysis.subject_pages] == ["Kandydat"]
    assert [section.title for section in grounded.analysis.subject_pages[0].sections] == ["Dane osoby"]
    assert _subject_fields(grounded.analysis) == distinct
    assert len(analysis.subject_pages) == 2
    assert grounded.correction_count == len(exact) + 1


@pytest.mark.parametrize("target", ["field", "section"])
@pytest.mark.parametrize("key", ["show_if", "show_if_all"])
def test_ground_preserves_duplicate_label_used_as_show_source(key: str, target: str) -> None:
    data = _analysis_data("BOTH")
    source = {"label": "Imię", "type": "RADIO", "options": ["Tak", "Nie"]}
    dependent = {"label": "Uzasadnienie", "type": "TEXTAREA"}
    section = {"title": "Uzasadnienie", "fields": [dependent]}
    condition = {"field": "Imię", "equals": "Tak"}
    (dependent if target == "field" else section)[key] = condition if key == "show_if" else [condition]
    data["subject_pages"] = [
        {"title": "Wybór", "sections": [{"title": "Opcje", "fields": [source]}]},
        {"title": "Uzasadnienie", "sections": [section]},
    ]
    result = quality.ground(_valid(data), _document(NEUTRAL))
    assert _subject_fields(result.analysis) == ["Imię", "Uzasadnienie"]
    assert result.correction_count == 0
    assert lint.check(build_form(result.analysis)) == []


def test_ground_keeps_subject_if_every_page_would_be_removed() -> None:
    data = _analysis_data("BOTH", entity_ids=["REGON"])
    data["subject_pages"][0]["sections"][0]["fields"] = [{"label": "Imię", "type": "TEXT_FIELD"}]
    analysis = _valid(data)
    result = quality.ground(analysis, _document(NEUTRAL))
    assert result.analysis.subject_pages == analysis.subject_pages
    assert result.analysis.applicant.entity_ids == []
    assert result.correction_count == 1
    assert any("opróżniłoby wszystkie strony" in note for note in result.notes)


def test_ground_reports_unsupported_labels_without_removing_them_or_quoting_document() -> None:
    data = _analysis_data("BOTH")
    data["subject_pages"][0]["sections"][0]["fields"] = [
        {"label": "Dyscyplina", "type": "RADIO", "options": ["Łucznictwo", "Piłka"]},
        {"label": "Wypożyczalnia", "type": "TEXT_FIELD"},
        {"label": "Cel", "type": "TEXT_FIELD"},
        {"label": "Wynik turnieju", "type": "TEXT_FIELD"},
    ]
    analysis = _valid(data)
    result = quality.ground(analysis, _document(NEUTRAL + " Lucznik wypozyczenie cel ZNACZNIK-DOKUMENTU."))
    assert result.analysis == analysis
    assert result.correction_count == 0
    assert result.notes == [
        "Brak oparcia w tekście dla pola „Cel”.",
        "Brak oparcia w tekście dla pola „Wynik turnieju”.",
    ]


def _coi_field(title: str, validation: list[str], kind: str = "TEXT_FIELD", **properties: object) -> dict:
    field = {"title": title, "type": kind, "validation": validation} | properties
    return {"tabs": [{"questions": [{"field": {"type": "SECTION", "repeatingSectionGrid": [{"field": field}]}}]}]}


@pytest.mark.parametrize(("rule", "title"), [
    ("PESEL", "Numer PESEL"), ("NIP", "NIP podatnika"), ("REGON", "Numer REGON"),
    ("ZIP_CODE", "Kod pocztowy"), ("EMAIL", "Adres poczty elektronicznej"),
    ("SERIAL_NUMBER_ID_CARD", "Seria i numer dowodu osobistego"),
    ("EPUAP", "Skrzynka ePUAP"), ("ADE", "Adres do e-Doręczeń"),
])
def test_type_validator_checks_kind_and_label(rule: str, title: str) -> None:
    assert quality.validator_issues(_coi_field(title, [rule])) == []
    wrong_title = quality.validator_issues(_coi_field("Uzasadnienie", [rule], readOnly=True))
    assert len(wrong_title) == 1 and rule in wrong_title[0] and "etykiety" in wrong_title[0]
    wrong_kind = quality.validator_issues(_coi_field(title, [rule], kind="TEXTAREA"))
    assert len(wrong_kind) == 1 and rule in wrong_kind[0] and "TEXT_FIELD" in wrong_kind[0]


@pytest.mark.parametrize(("title", "rule"), [
    ("Numer PESEL", "PESEL"), ("PESEL", "PESEL"), ("Kod pocztowy", "ZIP_CODE"), ("Adres e-mail", "EMAIL"),
])
def test_missing_type_validator_is_reported_only_for_editable_fields(title: str, rule: str) -> None:
    missing = quality.validator_issues(_coi_field(title, ["REQUIRED"]))
    assert len(missing) == 1 and rule in missing[0]
    assert quality.validator_issues(_coi_field(title, [], readOnly=True)) == []


def test_zip_code_is_forbidden_on_foreign_address() -> None:
    assert quality.validator_issues(_coi_field("Kod pocztowy", [], techName="kod_pocztowy_zagranica")) == []
    invalid = quality.validator_issues(_coi_field("Kod pocztowy", ["ZIP_CODE"], techName="kod_pocztowy_zagranica"))
    assert len(invalid) == 1 and "ZIP_CODE" in invalid[0] and "zagranica" in invalid[0]


@pytest.mark.parametrize("rules", [["NIP", "REGON"], ["NIP", "NIP"]])
def test_at_most_one_type_validator(rules: list[str]) -> None:
    issues = quality.validator_issues(_coi_field("NIP lub REGON", ["REQUIRED", *rules]))
    assert len(issues) == 1 and "więcej niż jeden" in issues[0]


@pytest.mark.parametrize("kind", ["SECTION", "TEXT_BLOCK", "INFO_SECTION"])
def test_required_is_forbidden_on_non_input_elements(kind: str) -> None:
    issues = quality.validator_issues(_coi_field("Informacja", ["REQUIRED"], kind=kind))
    assert len(issues) == 1 and kind in issues[0] and "REQUIRED" in issues[0]


def test_dictionary_issues_reports_unknown_names_and_missing_country_dictionary() -> None:
    for name in (
        "Województwo", "Powiat", "Gmina", "Miejscowość", "Kraje", "Numery kierunkowe",
        "TERYT_4G_DOWODOWY", "TERYT_DOWODOWY",
    ):
        assert quality.dictionary_issues(_coi_field("Wybór", [], kind="SELECT", dictionaryName=name)) == []

    unknown = quality.dictionary_issues(_coi_field("Wybór", [], kind="SELECT", dictionaryName="Numer działki"))
    assert len(unknown) == 1 and "Numer działki" in unknown[0]
    options = [{"id": country, "name": country} for country in COUNTRIES]
    missing = quality.dictionary_issues(_coi_field("Kraj urodzenia", [], kind="TEXT_FIELD"))
    assert len(missing) == 1 and "Kraje" in missing[0]
    for kind in ("RADIO", "SELECT", "CHECKBOX"):
        assert quality.dictionary_issues(_coi_field("Kraj urodzenia", [], kind=kind, options=options)) == []
    assert quality.dictionary_issues(_coi_field("Państwo", [], kind="SELECT", dictionaryName="Kraje")) == []
    assert quality.dictionary_issues(_coi_field("Kod kraju", [], kind="SELECT")) == []


@pytest.mark.parametrize("name", [
    "fields.json", "analysis_form3.json", "analysis_form9.json",
    "analysis_person.json", "analysis_entity.json", "analysis_edge_cases.json",
])
def test_generated_fixtures_pass_quality_checks(name: str) -> None:
    form = generated(name)
    assert quality.validator_issues(form) == []
    assert quality.dictionary_issues(form) == []


@pytest.mark.parametrize("label", [
    "Kraj urodzenia", "Państwo", "Obywatelstwo", "Posiadane obywatelstwo",
    "Kraj / państwo", "Kraj zamieszkania lub pobytu", "Kod kraju", "Krajowy rejestr",
])
def test_generator_matches_country_labels_by_word(label: str) -> None:
    data = _analysis_data("PERSON")
    data["subject_pages"][0]["sections"][0]["fields"] = [{"label": label, "type": "TEXT_FIELD"}]
    form = build_form(_valid(data))
    field = next(field for field in by_tech_name(form).values() if field["title"] == label)
    if label in {"Kod kraju", "Krajowy rejestr"}:
        assert field["type"] == "TEXT_FIELD" and "dictionaryName" not in field
    else:
        assert (field["type"], field["dictionaryName"], field["options"]) == ("SELECT", "Kraje", [])
        assert field["searchEnabled"] and "defaultValue" not in field
    assert lint.check(form) == []
    assert quality.dictionary_issues(form) == []


@pytest.mark.parametrize(("label", "kind", "options"), [
    pytest.param("Państwo członkowskie UE?", "RADIO", ["Tak", "Nie"], id="tak-nie"),
    pytest.param("Kraj urodzenia", "SELECT", COUNTRIES[:4], id="cztery-opcje"),
    pytest.param("Data nabycia obywatelstwa", "TEXT_FIELD", [], id="atrybut-obywatelstwa"),
    pytest.param("Kraj i miejscowość urodzenia", "TEXT_FIELD", [], id="dwie-dane"),
    pytest.param("Kraj urodzenia", "CHECKBOX", COUNTRIES, id="checkbox"),
    pytest.param("Kraj urodzenia", "FILE_UPLOADER", [], id="plik"),
])
def test_country_label_preserves_specialized_field(label: str, kind: str, options: list[str]) -> None:
    data = _analysis_data("PERSON")
    data["subject_pages"][0]["sections"][0]["fields"] = [{"label": label, "type": kind, "options": options}]
    form = build_form(_valid(data))
    field = next(field for field in by_tech_name(form).values() if field["title"] == label)
    assert field["type"] == kind and "dictionaryName" not in field
    assert [option["name"] for option in field["options"]] == options
    assert lint.check(form) == []
    assert quality.dictionary_issues(form) == []


@pytest.mark.parametrize("special", ["TAK", "Nie", "IŃNY", "Inne"])
def test_country_choices_with_special_option_stay_inline(special: str) -> None:
    data = _analysis_data("PERSON")
    options = [*COUNTRIES, special]
    data["subject_pages"][0]["sections"][0]["fields"] = [
        {"label": "Kraj urodzenia", "type": "RADIO", "options": options},
    ]
    form = build_form(_valid(data))
    country = by_tech_name(form)["kraj_urodzenia"]
    assert country["type"] == "RADIO" and "dictionaryName" not in country
    assert [option["name"] for option in country["options"]] == options
    assert quality.dictionary_issues(form) == []


@pytest.mark.parametrize(("kind", "count"), [("SELECT", 6), ("RADIO", 5)])
def test_country_field_preserves_closed_choices(kind: str, count: int) -> None:
    data = _analysis_data("PERSON")
    data["subject_pages"][0]["sections"][0]["fields"] = [
        {"label": "Kraj urodzenia", "type": kind, "options": COUNTRIES[:count]},
    ]
    form = build_form(_valid(data))
    field = by_tech_name(form)["kraj_urodzenia"]
    assert field["type"] == kind and "dictionaryName" not in field
    assert [option["id"] for option in field["options"]] == COUNTRIES[:count]
    assert lint.check(form) == []
    assert quality.dictionary_issues(form) == []


@pytest.mark.parametrize(("scope", "key"), [
    ("field", "show_if"), ("field", "show_if_all"), ("section", "show_if"),
    ("section", "show_if_all"), ("applicant", "show_if"),
])
@pytest.mark.parametrize(("options", "chosen"), [
    pytest.param(["Polska", "Inny"], "Inny", id="dwie-opcje"),
    pytest.param(COUNTRIES, "Czechy", id="szesc-krajow"),
])
def test_country_used_as_show_source_preserves_inline_options(
    scope: str, key: str, options: list[str], chosen: str,
) -> None:
    data = _analysis_data("PERSON")
    source = {"label": "Kraj zamieszkania", "type": "RADIO", "options": options, "required": False}
    dependent = {"label": "Miejscowość", "type": "TEXT_FIELD"}
    section = {"title": "Dalsze dane", "fields": [dependent]}
    condition = {"field": "Kraj zamieszkania", "equals": chosen}
    (section if scope == "section" else dependent)[key] = condition if key == "show_if" else [condition]
    if scope == "applicant":
        data["applicant"]["applicant_extra_fields"] = [source, dependent]
    else:
        data["subject_pages"][0]["sections"][0]["fields"] = [source]
        data["subject_pages"].append({"title": "Dodatkowe informacje", "sections": [section]})
    form = build_form(_valid(data))
    items = by_tech_name(form)
    country = items["kraj_zamieszkania"]
    assert country["type"] == "RADIO" and "dictionaryName" not in country
    assert [option["id"] for option in country["options"]] == options
    assert country["validation"] == [] and "defaultValue" not in country
    target = items["dalsze_dane" if scope == "section" else "miejscowosc"]
    assert f'"{chosen}" in tabs' in target["states"][0]["query"]
    assert lint.check(form) == []
    assert quality.dictionary_issues(form) == []


def test_subject_closed_choices_do_not_prevent_country_dictionary_in_applicant_data() -> None:
    label = "Kraj urodzenia"
    data = _analysis_data("PERSON", applicant_extra_fields=[{"label": label, "type": "TEXT_FIELD"}])
    data["subject_pages"][0]["sections"][0]["fields"] = [
        {"label": label, "type": "RADIO", "options": COUNTRIES},
        {
            "label": "Miejscowość urodzenia", "type": "TEXT_FIELD",
            "show_if_all": [{"field": "Kraj urodzenia", "equals": "Austria"}],
        },
    ]
    form = build_form(_valid(data))
    items = by_tech_name(form)
    assert items["kraj_urodzenia"]["dictionaryName"] == "Kraje"
    assert items["kraj_urodzenia_2"]["type"] == "RADIO"
    assert [item["name"] for item in items["kraj_urodzenia_2"]["options"]] == COUNTRIES
    assert lint.check(form) == []
    assert quality.dictionary_issues(form) == []


def test_generator_omits_zip_code_for_foreign_tech_name() -> None:
    data = _analysis_data("PERSON")
    data["subject_pages"][0]["sections"][0]["fields"] = [
        {"label": "Kod pocztowy zagranica", "type": "TEXT_FIELD"},
    ]
    form = build_form(_valid(data))
    assert by_tech_name(form)["kod_pocztowy_zagranica"]["validation"] == ["REQUIRED"]
    assert quality.validator_issues(form) == []
