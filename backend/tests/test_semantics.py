"""Regresje znaczeniowe z żywego E1 (Eden AI, 22.11): zgodność ze źródłem i warianty SHOW.

Dane są syntetyczne i odtwarzają kształt odpowiedzi modelu z F2 i F9, bez treści z materiałów COI.
"""

from itertools import product

import pytest
from test_generator import _analysis_data, _visible_in_form9, by_tech_name

from app import lint, quality
from app.generator import build_form
from app.models import ExtractedDocument, FormAnalysis
from app.repair import repair_analysis

NEUTRAL = "Uzasadnienie sprawy jest opisane w formularzu. " * 6
VARIANTS = ["Stypendium", "Nagroda", "Wyróżnienie"]
DELIVERY = ["Poczta na adres siedziby", "Poczta na inny adres", "Skrzynka ePUAP", "eDoręczenia"]


def _document(text: str) -> ExtractedDocument:
    return ExtractedDocument(source_format="pdf", text=text)


def _field(label: str, kind: str = "TEXT_FIELD", **attrs: object) -> dict:
    return {"label": label, "type": kind, **attrs}


def _when(field: str, equals: str, *alternatives: str) -> dict:
    return {"field": field, "equals": equals, "any_of": list(alternatives)}


# --- Zgodność ze źródłem: duplikaty danych wnioskodawcy (F2) ---------------------------------------


F2_TEXT = NEUTRAL + (
    "Dane wnioskodawcy. Nazwa / Imię i nazwisko. NIP. Numer telefonu. Adres poczty elektronicznej. "
    "Sposób zwrotu: Gotówką w kasie organu. Przelewem na rachunek w banku."
)


def _f2_shaped(**decisions: object) -> FormAnalysis:
    """Model wpisał NIP, telefon i e-mail w przedmiot, ale nie włączył ich w decyzjach szablonu."""
    data = _analysis_data("BOTH", **decisions)
    data["subject_pages"][0]["sections"][0]["fields"] = [
        _field("Nazwa / Imię i nazwisko"), _field("NIP"), _field("Numer telefonu"),
        _field("Adres poczty elektronicznej"), _field("Uzasadnienie", "TEXTAREA"),
    ]
    return FormAnalysis.model_validate(data)


def _titles(form: dict) -> set[str]:
    return {item["title"] for item in by_tech_name(form).values()}


def test_ground_keeps_applicant_duplicates_that_the_template_would_not_show() -> None:
    result = quality.ground(_f2_shaped(), _document(F2_TEXT))
    labels = [field.label for field in result.analysis.subject_pages[0].sections[0].fields]
    assert labels == ["Nazwa / Imię i nazwisko", "NIP", "Numer telefonu", "Adres poczty elektronicznej", "Uzasadnienie"]
    assert result.correction_count == 0
    kept = [note for note in result.notes if note.startswith("Zachowano „")]
    assert len(kept) == 3
    form = build_form(result.analysis)
    assert {"NIP", "Numer telefonu", "Adres poczty elektronicznej"} <= _titles(form)
    assert lint.check(form) == []


def test_ground_removes_only_duplicates_covered_by_supported_decisions() -> None:
    analysis = _f2_shaped(entity_ids=["NIP"], contact=["PHONE", "EMAIL"])
    result = quality.ground(analysis, _document(F2_TEXT))
    labels = [field.label for field in result.analysis.subject_pages[0].sections[0].fields]
    assert labels == ["Nazwa / Imię i nazwisko", "Uzasadnienie"]
    assert result.correction_count == 3
    items = by_tech_name(build_form(result.analysis))
    assert {"nip", "numer_telefonu", "adres_e_mail"} <= set(items)


@pytest.mark.parametrize(("label", "decisions", "evidence"), [
    ("PESEL", {"applicant_pesel": True}, "PESEL"),
    ("NIP", {"entity_ids": ["NIP"]}, "NIP"),
    ("REGON", {"entity_ids": ["REGON"]}, "REGON"),
    ("Numer KRS", {"entity_ids": ["KRS"]}, "KRS"),
    ("Adres zamieszkania", {"person_address": True}, "zamieszkania"),
    ("Adres siedziby", {"entity_address": True}, "siedziby"),
    ("Adres do korespondencji", {"correspondence_address": True}, "korespondencji"),
    ("Telefon kontaktowy", {"contact": ["PHONE"]}, "telefon"),
    ("Adres e-mail", {"contact": ["EMAIL"]}, "e-mail"),
])
def test_every_applicant_duplicate_is_removed_only_when_its_decision_survives(
    label: str, decisions: dict, evidence: str,
) -> None:
    data = _analysis_data("BOTH", **decisions)
    data["subject_pages"][0]["sections"][0]["fields"].append(_field(label))
    analysis = FormAnalysis.model_validate(data)

    supported = quality.ground(analysis, _document(NEUTRAL + evidence))
    assert label not in {field.label for field in supported.analysis.subject_pages[0].sections[0].fields}

    # Bez przesłanki decyzja wyłącza się, a pole musi zostać, żeby dane nie zniknęły z formularza.
    unsupported = quality.ground(analysis, _document(NEUTRAL))
    assert label in {field.label for field in unsupported.analysis.subject_pages[0].sections[0].fields}
    assert any(note == f"Zachowano „{label}” w przedmiocie. Szablon wnioskodawcy nie zbiera tych danych."
               for note in unsupported.notes)


# --- Sygnały błędów modelu, których walidacja nie łapie (F2 Yeah/No, F9 tytuł) ----------------------


def test_notes_flag_options_absent_from_the_source_but_not_yes_no() -> None:
    data = _analysis_data("BOTH")
    data["subject_pages"][0]["sections"][0]["fields"] = [
        _field("Sposób zwrotu opłaty", "RADIO", options=["Yeah", "No"]),
        _field("Forma zwrotu", "RADIO", options=["Gotówką w kasie organu", "Przelewem na rachunek w banku"]),
        _field("Czy dotyczy?", "RADIO", options=["Tak", "Nie"]),
        _field("Zgoda", "CHECKBOX", options=["Tak"]),
    ]
    notes = quality.ground(FormAnalysis.model_validate(data), _document(F2_TEXT)).notes
    flagged = [note for note in notes if note.startswith("Żadna opcja")]
    assert flagged == ["Żadna opcja pola „Sposób zwrotu opłaty” nie występuje w tekście."]


@pytest.mark.parametrize(("title", "flagged"), [
    ("Załącznik Nr 3 do zarządzenia Nr 245/IX/2024 - Rodzaje wniosków", True),
    ("Rodzaje wniosków (załącznik do uchwały nr 7)", True),
    ("Wniosek o przyznanie stypendium, nagrody lub wyróżnienia sportowego", False),
    ("Wniosek o zwrot opłaty skarbowej", False),
])
def test_notes_flag_attachment_designation_as_title(title: str, flagged: bool) -> None:
    data = _analysis_data("BOTH") | {"title": title}
    notes = quality.ground(FormAnalysis.model_validate(data), _document(NEUTRAL)).notes
    assert any(note.startswith("Tytuł wygląda") for note in notes) is flagged


# --- N4: pole wyboru z jedną opcją (F9 „Dodaj podopiecznego”) ---------------------------------------


@pytest.mark.parametrize("kind", ["RADIO", "SELECT"])
def test_n4_single_option_choice_becomes_checkbox_and_keeps_its_conditions(kind: str) -> None:
    data = _analysis_data("BOTH")
    data["subject_pages"][0]["sections"] = [
        {"title": "Podopieczni", "fields": [
            _field("Dane podopiecznego", kind, options=["Dodaj podopiecznego"]),
            _field("Imię i nazwisko podopiecznego", show_if=_when("Dane podopiecznego", "Dodaj podopiecznego")),
            _field("Rodzaj", "RADIO", options=["A", "B"]),
        ]},
        {"title": "Osiągnięcia", "show_if": _when("Dane podopiecznego", "Dodaj podopiecznego"),
         "fields": [_field("Osiągnięcia podopiecznego", "TEXTAREA")]},
    ]
    repaired, notes = repair_analysis(data, last_chance=False)
    fields = repaired["subject_pages"][0]["sections"][0]["fields"]
    assert [field["type"] for field in fields] == ["CHECKBOX", "TEXT_FIELD", "RADIO"]
    assert fields[0]["options"] == ["Dodaj podopiecznego"]
    assert fields[1]["show_if"] == data["subject_pages"][0]["sections"][0]["fields"][1]["show_if"]
    assert notes == [f"N4 'Dane podopiecznego': zmieniono {kind} z jedną opcją na CHECKBOX"]
    assert repair_analysis(repaired, last_chance=False) == (repaired, [])
    form = build_form(FormAnalysis.model_validate(repaired))
    assert lint.check(form) == []
    item = by_tech_name(form)["dane_podopiecznego"]
    assert (item["type"], [option["name"] for option in item["options"]]) == ("CHECKBOX", ["Dodaj podopiecznego"])


# --- Warianty SHOW, także między stronami (F9) ------------------------------------------------------


def _variants_analysis() -> FormAnalysis:
    """Trzy rodzaje wniosku, korespondencja z polem na opcję i zgody na osobnej stronie."""
    data = _analysis_data("BOTH")
    data["subject_pages"] = [
        {"title": "Wybór wniosku", "sections": [
            {"title": "Rodzaj", "fields": [_field("Rodzaj wniosku", "RADIO", options=VARIANTS)]},
            {"title": "Korespondencja klubu", "fields": [
                _field("Sposób korespondencji", "RADIO", options=DELIVERY),
                _field("Inny adres korespondencyjny", show_if=_when("Sposób korespondencji", "Poczta na inny adres")),
                _field("Adres skrzynki ePUAP", show_if=_when("Sposób korespondencji", "Skrzynka ePUAP")),
                _field("Adres skrzynki eDoręczeń", show_if=_when("Sposób korespondencji", "eDoręczenia")),
            ]},
        ]},
        {"title": "Kandydat", "sections": [
            {"title": "Dyscypliny", "show_if": _when("Rodzaj wniosku", "Stypendium"),
             "fields": [_field("Dyscyplina", "CHECKBOX", options=["Hokej", "Karate"])]},
            {"title": "Osiągnięcia", "fields": [
                _field("Opis osiągnięć", "TEXTAREA", show_if=_when("Rodzaj wniosku", "Stypendium", "Nagroda")),
            ]},
            {"title": "Dane trenera", "show_if": _when("Rodzaj wniosku", "Wyróżnienie"), "fields": [
                _field("Czy trener jest pełnoletni?", "RADIO", options=["Tak", "Nie"]),
            ]},
        ]},
        {"title": "Zgody", "sections": [
            {"title": "Zgoda kandydata", "show_if": _when("Rodzaj wniosku", "Stypendium", "Nagroda"),
             "fields": [_field("Zgoda kandydata na przetwarzanie danych", "CHECKBOX", options=["Tak"])]},
            {"title": "Zgoda trenera", "show_if": _when("Rodzaj wniosku", "Wyróżnienie"), "fields": [
                _field("Zgoda trenera na przetwarzanie danych", "CHECKBOX", options=["Tak"]),
                _field("Imię i nazwisko opiekuna trenera",
                       show_if_all=[_when("Czy trener jest pełnoletni?", "Nie")]),
            ]},
        ]},
    ]
    return FormAnalysis.model_validate(data)


def _visible_titles(form: dict, answers: dict[str, list[str]]) -> dict[str, set[str]]:
    """Strona przedmiotu -> widoczne pola. Pole widać, gdy widać je i jego sekcję."""
    visible = {}
    for page in form["tabs"][1:-2]:
        titles = set()
        for question in page["questions"]:
            section = question["field"]
            if not _visible_in_form9(section, answers):
                continue
            titles.update(
                cell["field"]["title"] for cell in section["repeatingSectionGrid"]
                if _visible_in_form9(cell["field"], answers)
            )
        visible[page["title"]] = titles
    return visible


@pytest.mark.parametrize(("variant", "delivery", "adult"), list(product(VARIANTS, DELIVERY, ["Tak", "Nie", None])))
def test_show_variants_across_pages_match_the_paper_routes(variant: str, delivery: str, adult: str | None) -> None:
    form = build_form(_variants_analysis())
    assert lint.check(form) == []
    names = {item["title"]: name for name, item in by_tech_name(form).items()}
    answers = {names["Rodzaj wniosku"]: [variant], names["Sposób korespondencji"]: [delivery]}
    if adult is not None:
        # Odpowiedź zostaje w danych także po zmianie rodzaju wniosku, jak w prawdziwym formularzu.
        answers[names["Czy trener jest pełnoletni?"]] = [adult]

    visible = _visible_titles(form, answers)

    delivery_field = {
        "Poczta na inny adres": "Inny adres korespondencyjny",
        "Skrzynka ePUAP": "Adres skrzynki ePUAP",
        "eDoręczenia": "Adres skrzynki eDoręczeń",
    }.get(delivery)
    choice = {"Rodzaj wniosku", "Sposób korespondencji"} | ({delivery_field} if delivery_field else set())
    candidate, consents = set(), set()
    if variant == "Stypendium":
        candidate.add("Dyscyplina")
    if variant in ("Stypendium", "Nagroda"):
        candidate.add("Opis osiągnięć")
        consents.add("Zgoda kandydata na przetwarzanie danych")
    else:
        candidate.add("Czy trener jest pełnoletni?")
        consents.add("Zgoda trenera na przetwarzanie danych")
        if adult == "Nie":
            consents.add("Imię i nazwisko opiekuna trenera")
    assert visible == {"Wybór wniosku": choice, "Kandydat": candidate, "Zgody": consents}


def test_delivery_option_shows_only_its_own_field() -> None:
    """Regresja F9: adres korespondencyjny nie może się pokazywać przy ePUAP ani eDoręczeniach."""
    form = build_form(_variants_analysis())
    names = {item["title"]: name for name, item in by_tech_name(form).items()}
    shown = {
        delivery: _visible_titles(form, {names["Sposób korespondencji"]: [delivery]})["Wybór wniosku"]
        - {"Rodzaj wniosku", "Sposób korespondencji"}
        for delivery in DELIVERY
    }
    assert shown == {
        "Poczta na adres siedziby": set(),
        "Poczta na inny adres": {"Inny adres korespondencyjny"},
        "Skrzynka ePUAP": {"Adres skrzynki ePUAP"},
        "eDoręczenia": {"Adres skrzynki eDoręczeń"},
    }


@pytest.mark.parametrize("scope", ["field", "section"])
def test_ground_keeps_names_of_other_people_shown_by_a_condition(scope: str) -> None:
    """Regresja F9: „Imię” i „Nazwisko” kandydata lub trenera to nie dane wnioskodawcy z szablonu."""
    data = _analysis_data("BOTH")
    when = _when("Rodzaj wniosku", "Wyróżnienie")
    person = [_field("Imię"), _field("Nazwisko")]
    if scope == "field":
        person = [{**field, "show_if": when} for field in person]
    trainer = {"title": "Dane trenera", "fields": person} | ({"show_if": when} if scope == "section" else {})
    data["subject_pages"] = [{"title": "Kandydat", "sections": [
        {"title": "Rodzaj", "fields": [_field("Rodzaj wniosku", "RADIO", options=VARIANTS), _field("Imię")]},
        trainer,
    ]}]
    result = quality.ground(FormAnalysis.model_validate(data), _document(NEUTRAL))
    sections = result.analysis.subject_pages[0].sections
    assert [field.label for field in sections[0].fields] == ["Rodzaj wniosku"]
    assert [field.label for field in sections[1].fields] == ["Imię", "Nazwisko"]
    assert result.correction_count == 1

