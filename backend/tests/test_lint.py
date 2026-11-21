"""P2: zgodność COI, błędy ze ścieżką i odporność na uszkodzone dane."""

import json
import re
from collections import OrderedDict
from copy import deepcopy
from enum import StrEnum
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import lint
from app.generator import build_form
from app.models import FormAnalysis

FIXTURES = Path(__file__).parent / "fixtures"
FIRST_QUESTION = "tabs[0].questions[0]"
FIRST_SECTION = f"{FIRST_QUESTION}.field"
FIRST_FIELD = f"{FIRST_SECTION}.repeatingSectionGrid[0].field"
CHOICE_SECTION = "tabs[0].questions[1].field"
CHOICE_FIELD = f"{CHOICE_SECTION}.repeatingSectionGrid[0].field"
FINISH_FIELD = "tabs[3].questions[0].field.repeatingSectionGrid[0].field"
CONSENTS = "tabs[2].questions[1].field.repeatingSectionGrid[0].field.consentSectionConfig"
STATE = f"{FIRST_FIELD}.states[0]"
DELETE = object()


def _parts(path: str) -> list[str | int]:
    return [int(part) if part.isdecimal() else part for part in re.findall(r"[^.\[\]]+", path)]


def _at(form: dict, path: str):
    value = form
    for part in _parts(path):
        value = value[part]
    return value


def _change(form: dict, path: str, value: object) -> None:
    parent = form
    *parts, last = _parts(path)
    for part in parts:
        parent = parent[part]
    if value is DELETE:
        del parent[last]
    else:
        parent[last] = value


@pytest.fixture
def working_copy(coi_working_reference: dict) -> dict:
    return deepcopy(coi_working_reference)


def _reverse_keys(value: object) -> object:
    if isinstance(value, dict):
        return {key: _reverse_keys(value[key]) for key in reversed(value)}
    if isinstance(value, list):
        return [_reverse_keys(item) for item in value]
    return value


def _atom(option: str, page: str, section: str, field: str, *, repeating: bool = False) -> str:
    # Niezależny zapis ścieżek z Reguł, łącznie z "in" bez spacji po apostrofie.
    page, section, field = (name.replace("'", r"\u0027") for name in (page, section, field))
    prefix = f"{json.dumps(option, ensure_ascii=False)} in tabs['{page}'in title].questions['{section}' in field.techName].field"
    if repeating:
        return f"{prefix}.__userAnswer[$repeatingSectionIndex]['{field}'in fieldTechName].answers"
    return f"{prefix}.repeatingSectionGrid['{field}' in field.techName].field.__userAnswer"


def _choice_query(form: dict, *, repeating: bool = False, **overrides: str) -> str:
    choice = _at(form, CHOICE_FIELD)
    values = {
        "option": choice["options"][0]["id"],
        "page": form["tabs"][0]["title"],
        "section": _at(form, CHOICE_SECTION)["techName"],
        "field": choice["techName"],
    } | overrides
    return _atom(**values, repeating=repeating)


def _show(form: dict, query: str, kind: str = "SHOW") -> None:
    _change(form, f"{FIRST_FIELD}.states", [{"type": kind, "query": query}])


def test_control_reference(coi_control_reference: dict) -> None:
    assert lint.check(coi_control_reference) == []


def test_working_reference(coi_working_reference: dict) -> None:
    assert lint.check(coi_working_reference) == []


def test_ordered_dict_form(coi_working_reference: dict) -> None:
    def ordered(value: object) -> object:
        if isinstance(value, dict):
            return OrderedDict((key, ordered(item)) for key, item in value.items())
        if isinstance(value, list):
            return [ordered(item) for item in value]
        return value

    assert lint.check(OrderedDict(coi_working_reference)) == []
    assert lint.check(ordered(coi_working_reference)) == []


def test_strenum_as_field_type(working_copy: dict) -> None:
    class Kind(StrEnum):
        RADIO = "RADIO"

    _change(working_copy, f"{CHOICE_FIELD}.type", Kind.RADIO)
    assert lint.check(working_copy) == []


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*.json")), ids=lambda path: path.name)
def test_all_generated_forms(path: Path) -> None:
    analysis = FormAnalysis.model_validate_json(path.read_text(encoding="utf-8"))
    assert lint.check(build_form(analysis)) == []


@pytest.mark.parametrize("variant", ["key-order", "question-order", "crlf", "no-states"])
def test_working_reference_variants(working_copy: dict, variant: str) -> None:
    if variant == "key-order":
        working_copy = _reverse_keys(working_copy)
    elif variant == "question-order":
        questions = working_copy["tabs"][0]["questions"]
        questions.reverse()
        assert [q["y"] for q in questions] != sorted(q["y"] for q in questions)
    elif variant == "crlf":
        query = _choice_query(working_copy)
        _show(working_copy, f"$not(\r\n{query}\r\n)\r\nand ({query}\r\nor {query})")
    else:
        _change(working_copy, f"{FIRST_SECTION}.states", DELETE)
    assert lint.check(working_copy) == []


def test_schema_compatibility(working_copy: dict) -> None:
    _change(working_copy, "title", "a" * 255)
    _change(working_copy, f"{FIRST_QUESTION}.x", 0.5)
    _change(working_copy, f"{FIRST_FIELD}.questionOrder", 1.5)
    _change(working_copy, f"{FIRST_FIELD}.defaultValue", ["wartość"])
    _change(working_copy, f"{FIRST_FIELD}.validation", {})
    _change(working_copy, f"{CHOICE_FIELD}.options[0].techName", DELETE)
    working_copy["dodatkowe"] = {"a": [{"b": False}]}
    assert lint.check(working_copy) == []


def test_all_nine_validator_names(working_copy: dict) -> None:
    _change(working_copy, f"{FIRST_FIELD}.validation", [
        "REQUIRED", "EMAIL", "PESEL", "NIP", "REGON", "ZIP_CODE", "EPUAP", "ADE", "SERIAL_NUMBER_ID_CARD",
    ])
    assert lint.check(working_copy) == []


def test_info_section_and_read_only_state(working_copy: dict) -> None:
    _change(working_copy, f"{FINISH_FIELD}.type", "INFO_SECTION")
    _show(working_copy, _choice_query(working_copy), "READ_ONLY")
    assert lint.check(working_copy) == []


def _add_choice_page(form: dict, page: str, option: dict, *, member: str, repeating: bool) -> str:
    section, name = "sekcja_testowa", "wybor_testowy"
    form["tabs"].insert(-1, {
        "id": "strona-testowa",
        "title": page,
        "type": "MAIN",
        "questions": [{
            "x": 0, "y": 0, "rows": 2, "cols": 3,
            "field": {"id": "sekcja-testowa", "type": "REPEATING_SECTION" if repeating else "SECTION",
                      "techName": section,
                      "title": "Sekcja testowa", "repeatingSectionGrid": [{
                          "x": 0, "y": 0, "rows": 1, "cols": 3,
                          "field": {"id": "pole-testowe", "type": "RADIO", "techName": name,
                                    "options": [option], "validation": []},
                      }]},
        }],
    })
    previous_link = form["flow"]["links"][-1]
    finish = previous_link["target"]
    previous_link["target"] = "strona-testowa"
    form["flow"]["links"].append({"id": "link-testowy", "source": "strona-testowa", "target": finish})
    return _atom(option[member], page, section, name, repeating=repeating)


@pytest.mark.parametrize("member", ["id", "name"])
def test_jsonata_escaped_literals_and_option_identity(working_copy: dict, member: str) -> None:
    option = {"id": "wariant-1", "name": 'Opcja "A" \\ B'}
    repeated = _add_choice_page(working_copy, "Dane 'obywatela'", option, member=member, repeating=True)
    normal = _choice_query(working_copy)
    _show(working_copy, f"$not(\r\n{repeated}) or (({normal}) and ({repeated}))")
    assert lint.check(working_copy) == []


def test_jsonata_double_quote_in_single_quoted_page_title(working_copy: dict) -> None:
    option = {"id": "wariant-1", "name": "Opcja"}
    query = _add_choice_page(working_copy, 'Dane "x"', option, member="id", repeating=False)
    assert """tabs['Dane "x"'in title]""" in query
    _show(working_copy, query)
    assert lint.check(working_copy) == []


def test_jsonata_raw_tab_and_lf_in_quoted_literals(working_copy: dict) -> None:
    option = {"id": "wariant-1", "name": "A\tB\nC"}
    query = _add_choice_page(working_copy, "Dane\tA\nB", option, member="name", repeating=False)
    # Format JSONata dopuszcza surowe znaki także wewnątrz literałów.
    query = query.replace(r"\t", "\t").replace(r"\n", "\n")
    _show(working_copy, query)
    assert lint.check(working_copy) == []


def test_jsonata_decode_value_error_becomes_diagnostic(
    working_copy: dict, monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = _choice_query(working_copy, option="opcja-testowa")
    _show(working_copy, query)

    def loads(literal: str, **kwargs: object) -> str:
        if literal == '"opcja-testowa"':
            raise ValueError("błąd dekodowania literału")
        return json.loads(literal, **kwargs)

    monkeypatch.setattr(lint, "json", SimpleNamespace(loads=loads))
    assert lint.check(working_copy) == [f"{STATE}.query: nierozpoznane zapytanie JSONata"]


@pytest.mark.parametrize(("path", "value", "error_path", "message"), [
    pytest.param(f"{FIRST_QUESTION}.x", True, f"{FIRST_QUESTION}.x", "oczekiwano liczby", id="1-bool-x"),
    pytest.param(f"{FIRST_QUESTION}.rows", "1", f"{FIRST_QUESTION}.rows", "oczekiwano liczby", id="1-rows-type"),
    pytest.param(f"{FIRST_SECTION}.questionOrder", False, f"{FIRST_SECTION}.questionOrder", "oczekiwano liczby", id="1-order-type"),
    pytest.param(f"{FIRST_FIELD}.readOnly", 1, f"{FIRST_FIELD}.readOnly", "oczekiwano flagi logicznej", id="1-read-only-type"),
    pytest.param(f"{FIRST_FIELD}.defaultValue", 1, f"{FIRST_FIELD}.defaultValue", "oczekiwano tekstu lub tablicy", id="1-default-type"),
    pytest.param(f"{FIRST_FIELD}.options", [None], f"{FIRST_FIELD}.options[0]", "oczekiwano obiektu", id="1-option-object"),
    pytest.param(f"{CHOICE_FIELD}.options[0].techName", 1, f"{CHOICE_FIELD}.options[0].techName", "oczekiwano tekstu", id="1-option-tech-name-type"),
    pytest.param(f"{CONSENTS}.files", {}, f"{CONSENTS}.files", "oczekiwano tablicy", id="1-consent-files"),
    pytest.param(f"{CONSENTS}.required", 1, f"{CONSENTS}.required", "oczekiwano flagi logicznej", id="1-consent-config-required"),
    pytest.param("title", " ", "title", "wymagany niepusty tekst", id="2-empty-title"),
    pytest.param("title", "a" * 256, "title", "maksymalnie 255 znaków", id="2-long-title"),
    pytest.param("tabs[0].title", " ", "tabs[0].title", "wymagany niepusty tekst", id="blank-tab-title"),
    pytest.param("tabs", [], "tabs", "wymagane co najmniej dwie strony", id="3-too-few-tabs"),
    pytest.param("tabs[3].type", "MAIN", "tabs[3].type", "oczekiwano FINISH", id="3-last-is-main"),
    pytest.param("tabs[1].type", "FINISH", "tabs[1].type", "oczekiwano MAIN", id="3-finish-in-middle"),
    pytest.param("tabs[1].questions", [], "tabs[1].questions", "strona musi zawierać co najmniej jedno pole w sekcji", id="3-no-questions"),
    pytest.param(f"{FIRST_SECTION}.type", "TEXT_FIELD", f"{FIRST_SECTION}.type", "na stronie wymagana jest sekcja", id="4-field-outside-section"),
    pytest.param(f"{FIRST_FIELD}.type", "REPEATING_SECTION", f"{FIRST_FIELD}.type", "sekcja nie może zawierać sekcji", id="4-nested-section"),
    pytest.param(f"{FIRST_SECTION}.title", DELETE, f"{FIRST_SECTION}.title", "brak wymaganego klucza", id="4-section-title"),
    pytest.param(f"{FIRST_SECTION}.techName", DELETE, f"{FIRST_SECTION}.techName", "brak wymaganego klucza", id="4-section-tech-name"),
    pytest.param(f"{FIRST_FIELD}.techName", DELETE, f"{FIRST_FIELD}.techName", "brak wymaganego klucza", id="4-field-tech-name"),
    pytest.param(f"{FIRST_SECTION}.title", " ", f"{FIRST_SECTION}.title", "wymagany niepusty tekst", id="blank-section-title"),
    pytest.param(f"{FIRST_SECTION}.techName", " ", f"{FIRST_SECTION}.techName", "wymagany niepusty tekst", id="blank-section-tech-name"),
    pytest.param(f"{FIRST_FIELD}.techName", " ", f"{FIRST_FIELD}.techName", "wymagany niepusty tekst", id="blank-field-tech-name"),
    pytest.param(f"{FIRST_FIELD}.type", " ", f"{FIRST_FIELD}.type", "wymagany niepusty tekst", id="blank-field-type"),
    pytest.param(f"{FIRST_FIELD}.validation", DELETE, f"{FIRST_FIELD}.validation", "brak wymaganego klucza", id="4-validation-key"),
    pytest.param(f"{FIRST_FIELD}.repeatingSectionGrid", [None], f"{FIRST_FIELD}.repeatingSectionGrid", "tylko sekcja może zawierać pola", id="4-field-grid"),
    pytest.param(f"{FIRST_FIELD}.type", "SIGNATURE", f"{FIRST_FIELD}.type", "niedozwolony typ pola 'SIGNATURE'", id="5-unknown-field-type"),
    pytest.param(f"{FINISH_FIELD}.type", "NUMBER", f"{FINISH_FIELD}.type", "na stronie FINISH dozwolone są tylko TEXT_BLOCK i INFO_SECTION", id="5-input-on-finish"),
    pytest.param(f"{FIRST_FIELD}.validation", ["FAKE"], f"{FIRST_FIELD}.validation[0]", "nieznany walidator 'FAKE'", id="6-unknown-validator"),
    pytest.param(f"{FIRST_FIELD}.validation", [{"type": "REQUIRED"}], f"{FIRST_FIELD}.validation[0]", "oczekiwano tekstu", id="6-validator-object"),
    pytest.param(f"{FIRST_FIELD}.validation", {"REQUIRED": True}, f"{FIRST_FIELD}.validation", "oczekiwano tablicy", id="6-nonempty-validation-object"),
    pytest.param(f"{FINISH_FIELD}.validation", ["REQUIRED"], f"{FINISH_FIELD}.validation", "pole informacyjne nie może mieć walidatorów", id="6-validator-on-text-block"),
    pytest.param(f"{FIRST_SECTION}.states", [{"type": "READ_ONLY", "query": "x"}], f"{FIRST_SECTION}.states[0].type", "stan sekcji musi mieć typ SHOW", id="7-section-state-type"),
    pytest.param(f"{FIRST_FIELD}.states", [{"type": "HIDE", "query": "x"}], f"{STATE}.type", "stan pola musi mieć typ SHOW lub READ_ONLY", id="7-field-state-type"),
    pytest.param(f"{FIRST_FIELD}.states", [{"type": "SHOW", "query": " \r\n"}], f"{STATE}.query", "wymagany niepusty tekst", id="7-empty-query"),
    pytest.param(f"{FIRST_FIELD}.states", [{"query": "true"}], f"{STATE}.type", "brak wymaganego klucza", id="missing-state-type"),
    pytest.param(f"{CHOICE_FIELD}.options", DELETE, f"{CHOICE_FIELD}.options", "brak wymaganego klucza", id="8-options-key"),
    pytest.param(f"{CHOICE_FIELD}.options", [], f"{CHOICE_FIELD}.dictionaryName", "brak wymaganego klucza", id="8-no-dictionary"),
    pytest.param(f"{CHOICE_FIELD}.options[0].id", DELETE, f"{CHOICE_FIELD}.options[0].id", "brak wymaganego klucza", id="8-option-id"),
    pytest.param(f"{CHOICE_FIELD}.options[0].name", DELETE, f"{CHOICE_FIELD}.options[0].name", "brak wymaganego klucza", id="8-option-name"),
    pytest.param(CONSENTS, DELETE, CONSENTS, "brak wymaganego klucza", id="8-no-consent-config"),
    pytest.param(f"{CONSENTS}.consents", DELETE, f"{CONSENTS}.consents", "brak wymaganego klucza", id="8-no-consents"),
    pytest.param(f"{CONSENTS}.consents", [], f"{CONSENTS}.consents", "wymagana co najmniej jedna zgoda", id="8-empty-consents"),
    pytest.param(f"{CONSENTS}.consents[0].description", DELETE, f"{CONSENTS}.consents[0].description", "brak wymaganego klucza", id="8-consent-description"),
    pytest.param(f"{CONSENTS}.consents[0].description", " ", f"{CONSENTS}.consents[0].description", "wymagany niepusty tekst", id="blank-consent-description"),
    pytest.param(f"{CONSENTS}.consents[0].required", DELETE, f"{CONSENTS}.consents[0].required", "brak wymaganego klucza", id="8-consent-required"),
    pytest.param(f"{CONSENTS}.consents[0].required", 0, f"{CONSENTS}.consents[0].required", "oczekiwano flagi logicznej", id="8-consent-required-type"),
    pytest.param("flow.links[0].source", "nieznane", "flow.links[0].source", "nie ma strony o id 'nieznane'", id="9-unknown-source"),
    pytest.param("flow.links[0].target", "nieznane", "flow.links[0].target", "nie ma strony o id 'nieznane'", id="9-unknown-target"),
    pytest.param(f"{FIRST_QUESTION}.x", DELETE, f"{FIRST_QUESTION}.x", "brak wymaganego klucza", id="missing-grid-x"),
])
def test_broken_working_reference(working_copy: dict, path: str, value: object, error_path: str, message: str) -> None:
    _change(working_copy, path, value)
    assert f"{error_path}: {message}" in lint.check(working_copy)


def test_page_with_empty_section_has_no_fields(working_copy: dict) -> None:
    questions = working_copy["tabs"][1]["questions"]
    working_copy["tabs"][1]["questions"] = questions[:1]
    questions[0]["field"]["repeatingSectionGrid"] = []
    assert "tabs[1].questions: strona musi zawierać co najmniej jedno pole w sekcji" in lint.check(working_copy)


def test_one_finish_page_is_not_enough(working_copy: dict) -> None:
    working_copy["tabs"] = working_copy["tabs"][-1:]
    working_copy["flow"]["links"] = []
    assert lint.check(working_copy) == ["tabs: wymagane co najmniej dwie strony"]


def test_dictionary_name_cannot_be_blank(working_copy: dict) -> None:
    choice = _at(working_copy, CHOICE_FIELD)
    choice.update(options=[], dictionaryName=" ")
    assert f"{CHOICE_FIELD}.dictionaryName: wymagany niepusty tekst" in lint.check(working_copy)


@pytest.mark.parametrize(("key", "value", "message"), [
    ("description", DELETE, "brak wymaganego klucza"),
    ("description", "", "wymagany niepusty tekst"),
    ("validation", ["EMAIL"], "pole informacyjne nie może mieć walidatorów"),
])
def test_info_section_requirements(working_copy: dict, key: str, value: object, message: str) -> None:
    _change(working_copy, f"{FINISH_FIELD}.type", "INFO_SECTION")
    _change(working_copy, f"{FINISH_FIELD}.{key}", value)
    assert f"{FINISH_FIELD}.{key}: {message}" in lint.check(working_copy)


@pytest.mark.parametrize(("source", "target"), [
    ("tabs[0].id", "tabs[1].id"),
    (f"{FIRST_SECTION}.id", f"{FIRST_FIELD}.id"),
    ("tabs[0].id", f"{FIRST_FIELD}.id"),
    ("flow.links[0].id", "flow.links[1].id"),
    (f"{FIRST_SECTION}.techName", f"{FIRST_FIELD}.techName"),
])
def test_global_duplicates(working_copy: dict, source: str, target: str) -> None:
    duplicate = _at(working_copy, source)
    _change(working_copy, target, duplicate)
    assert f"{target}: powtórzony {duplicate!r}" in lint.check(working_copy)


def test_flow_unreachable_page(working_copy: dict) -> None:
    working_copy["flow"]["links"][0]["target"] = working_copy["tabs"][2]["id"]
    assert "tabs[1].id: strona nieosiągalna od pierwszej strony" in lint.check(working_copy)


def test_flow_reachable_dead_end(working_copy: dict) -> None:
    first, second, third, _ = (tab["id"] for tab in working_copy["tabs"])
    links = working_copy["flow"]["links"]
    links[1]["target"] = second
    links.append({"id": "nowy-link", "source": first, "target": third})
    assert lint.check(working_copy) == ["tabs[1].id: ze strony MAIN nie można dojść do FINISH"]


def test_flow_out_of_finish(working_copy: dict) -> None:
    first, _, _, finish = (tab["id"] for tab in working_copy["tabs"])
    working_copy["flow"]["links"].append({"id": "nowy-link", "source": finish, "target": first})
    assert "flow.links[3].source: link nie może wychodzić ze strony FINISH" in lint.check(working_copy)


def test_flow_cannot_traverse_finish_to_reach_another_page(working_copy: dict) -> None:
    _, second, _, finish = (tab["id"] for tab in working_copy["tabs"])
    links = working_copy["flow"]["links"]
    links[0]["target"] = finish
    links.append({"id": "nowy-link", "source": finish, "target": second})
    assert lint.check(working_copy) == [
        "flow.links[3].source: link nie może wychodzić ze strony FINISH",
        "tabs[1].id: strona nieosiągalna od pierwszej strony",
        "tabs[2].id: strona nieosiągalna od pierwszej strony",
    ]


def test_flow_cycle_with_a_way_to_finish(working_copy: dict) -> None:
    first, second, _, _ = (tab["id"] for tab in working_copy["tabs"])
    working_copy["flow"]["links"].append({"id": "nowy-link", "source": second, "target": first})
    assert lint.check(working_copy) == []



@pytest.mark.parametrize("return_kind", ["SHOW", "READ_ONLY"])
def test_lint_detects_only_show_cycles_between_pages(working_copy: dict, return_kind: str) -> None:
    later = _add_choice_page(
        working_copy, "Dodatkowy wybór", {"id": "tak", "name": "Tak"}, member="id", repeating=False,
    )
    _change(working_copy, f"{CHOICE_FIELD}.states", [{"type": "SHOW", "query": later}])
    later_field = "tabs[3].questions[0].field.repeatingSectionGrid[0].field"
    _change(working_copy, f"{later_field}.states", [{"type": return_kind, "query": _choice_query(working_copy)}])
    expected = [f"{later_field}.states[0].query: cykl zależności SHOW"] if return_kind == "SHOW" else []
    assert lint.check(working_copy) == expected


@pytest.mark.parametrize("target", [CHOICE_FIELD, CHOICE_SECTION], ids=["self-reference", "hidden-source"])
def test_lint_detects_cycle_when_show_hides_its_own_source(working_copy: dict, target: str) -> None:
    _change(working_copy, f"{CHOICE_FIELD}.states", [])
    _change(working_copy, f"{target}.states", [{"type": "SHOW", "query": _choice_query(working_copy)}])
    assert lint.check(working_copy) == [f"{target}.states[0].query: cykl zależności SHOW"]


@pytest.mark.parametrize(("key", "message"), [
    ("page", "nie ma strony 'nieznane'"),
    ("section", "nie ma sekcji 'nieznane' na wskazanej stronie"),
    ("field", "nie ma pola 'nieznane' we wskazanej sekcji"),
    ("option", "nie ma opcji 'nieznane' we wskazanym polu"),
])
def test_jsonata_unknown_reference(working_copy: dict, key: str, message: str) -> None:
    _show(working_copy, _choice_query(working_copy, **{key: "nieznane"}))
    assert f"{STATE}.query: {message}" in lint.check(working_copy)


def test_jsonata_checks_references_after_the_first_atom(working_copy: dict) -> None:
    valid = _choice_query(working_copy)
    unknown_option = _choice_query(working_copy, option="nieznane")
    _show(working_copy, f"({valid}) or $not({unknown_option})")
    assert f"{STATE}.query: nie ma opcji 'nieznane' we wskazanym polu" in lint.check(working_copy)


def test_jsonata_empty_options_without_dictionary_do_not_match(working_copy: dict) -> None:
    query = _choice_query(working_copy, option="nieznane")
    choice = _at(working_copy, CHOICE_FIELD)
    choice["options"] = []
    choice.pop("dictionaryName", None)
    _show(working_copy, query)
    assert f"{STATE}.query: nie ma opcji 'nieznane' we wskazanym polu" in lint.check(working_copy)


@pytest.mark.parametrize("pattern", [
    "true", "({atom}", "{atom})", "({atom}) and", "({atom}) ({atom})",
    "$not {atom}", "()", "({atom}) xor ({atom})", "({atom}) && ({atom})", "{atom} trailing",
    "{atom}and {atom}", "{atom}or {atom}",
])
def test_jsonata_unrecognized_syntax(working_copy: dict, pattern: str) -> None:
    _show(working_copy, pattern.format(atom=_choice_query(working_copy)))
    assert f"{STATE}.query: nierozpoznane zapytanie JSONata" in lint.check(working_copy)


@pytest.mark.parametrize("operator", ["and", "or"])
def test_jsonata_keyword_cannot_join_repeating_answer_property(working_copy: dict, operator: str) -> None:
    option = {"id": "wariant-1", "name": "Opcja"}
    query = _add_choice_page(working_copy, "Strona testowa", option, member="id", repeating=True)
    _show(working_copy, f"{query}{operator} {query}")
    assert lint.check(working_copy) == [f"{STATE}.query: nierozpoznane zapytanie JSONata"]


def test_jsonata_crlf_within_one_reference(working_copy: dict) -> None:
    query = _choice_query(working_copy)
    query = re.sub(r"\s*([.\[\]]|\bin\b)\s*", r"\r\n\1\r\n", query)
    assert "\r\n.\r\n" in query and "\r\nin\r\n" in query
    _show(working_copy, query)
    assert lint.check(working_copy) == []


def test_jsonata_repeating_reference_to_regular_section(working_copy: dict) -> None:
    _show(working_copy, _choice_query(working_copy, repeating=True))
    assert f"{STATE}.query: ścieżka JSONata nie pasuje do typu wskazanej sekcji" in lint.check(working_copy)


def test_jsonata_reference_to_nonchoice_field(working_copy: dict) -> None:
    section = _at(working_copy, FIRST_SECTION)
    field = _at(working_copy, FIRST_FIELD)
    _show(working_copy, _atom("dowolna", working_copy["tabs"][0]["title"], section["techName"], field["techName"]))
    assert f"{STATE}.query: wskazane pole nie jest polem wyboru" in lint.check(working_copy)


def test_jsonata_path_cannot_find_a_field_in_another_section(working_copy: dict) -> None:
    other_field = _at(working_copy, FIRST_FIELD)["techName"]
    _show(working_copy, _choice_query(working_copy, field=other_field))
    assert f"{STATE}.query: nie ma pola {other_field!r} we wskazanej sekcji" in lint.check(working_copy)


def test_jsonata_path_cannot_find_a_section_on_another_page(working_copy: dict) -> None:
    other_page = working_copy["tabs"][1]["title"]
    section = _at(working_copy, CHOICE_SECTION)["techName"]
    _show(working_copy, _choice_query(working_copy, page=other_page))
    assert f"{STATE}.query: nie ma sekcji {section!r} na wskazanej stronie" in lint.check(working_copy)


def test_errors_follow_input_traversal_order(working_copy: dict) -> None:
    _show(working_copy, _choice_query(working_copy, option="nieznane"))
    _change(working_copy, "title", "")
    _change(working_copy, "tabs[1].questions[0].y", False)
    _change(working_copy, f"{FINISH_FIELD}.validation", ["REQUIRED"])
    _change(working_copy, "flow.links[1].id", _at(working_copy, "flow.links[0].id"))
    expected = [
        "title: wymagany niepusty tekst",
        f"{STATE}.query: nie ma opcji 'nieznane' we wskazanym polu",
        "tabs[1].questions[0].y: oczekiwano liczby",
        f"{FINISH_FIELD}.validation: pole informacyjne nie może mieć walidatorów",
        f"flow.links[1].id: powtórzony {_at(working_copy, 'flow.links[0].id')!r}",
    ]
    before = deepcopy(working_copy)
    assert lint.check(working_copy) == expected
    assert lint.check(_reverse_keys(working_copy)) == expected
    assert working_copy == before


@pytest.mark.parametrize("value", [None, [], "", 3])
def test_non_object_form(value: object) -> None:
    assert lint.check(value) == ["$: oczekiwano obiektu"]


def test_empty_form_has_all_required_keys_reported() -> None:
    assert lint.check({}) == [
        "title: brak wymaganego klucza",
        "tabs: brak wymaganego klucza",
        "flow: brak wymaganego klucza",
    ]


@pytest.mark.parametrize(("path", "value", "error_path", "message"), [
    ("tabs", {}, "tabs", "oczekiwano tablicy"),
    ("tabs[0]", [], "tabs[0]", "oczekiwano obiektu"),
    ("tabs[0]", {}, "tabs[0].id", "brak wymaganego klucza"),
    (FIRST_QUESTION, {}, f"{FIRST_QUESTION}.field", "brak wymaganego klucza"),
    (FIRST_SECTION, [], FIRST_SECTION, "oczekiwano obiektu"),
    (f"{FIRST_SECTION}.repeatingSectionGrid", DELETE, f"{FIRST_SECTION}.repeatingSectionGrid", "brak wymaganego klucza"),
    (f"{FIRST_FIELD}.type", [], f"{FIRST_FIELD}.type", "oczekiwano tekstu"),
    (f"{FIRST_FIELD}.id", {}, f"{FIRST_FIELD}.id", "oczekiwano tekstu"),
    (FIRST_FIELD, None, FIRST_FIELD, "oczekiwano obiektu"),
    (f"{FIRST_FIELD}.states", {}, f"{FIRST_FIELD}.states", "oczekiwano tablicy"),
    (f"{FIRST_FIELD}.states", [None], STATE, "oczekiwano obiektu"),
    (f"{FIRST_FIELD}.states", [{}], f"{STATE}.query", "brak wymaganego klucza"),
    (f"{FIRST_FIELD}.states", [{"type": [], "query": []}], f"{STATE}.type", "oczekiwano tekstu"),
    (f"{CHOICE_FIELD}.options[0]", {}, f"{CHOICE_FIELD}.options[0].id", "brak wymaganego klucza"),
    (CONSENTS, [], CONSENTS, "oczekiwano obiektu"),
    (f"{CONSENTS}.consents[0]", [], f"{CONSENTS}.consents[0]", "oczekiwano obiektu"),
    ("flow", {}, "flow.links", "brak wymaganego klucza"),
    ("flow", [], "flow", "oczekiwano obiektu"),
    ("flow.links", {}, "flow.links", "oczekiwano tablicy"),
    ("flow.links[0]", {}, "flow.links[0].source", "brak wymaganego klucza"),
    ("flow.links[0]", [], "flow.links[0]", "oczekiwano obiektu"),
])
def test_malformed_levels(working_copy: dict, path: str, value: object, error_path: str, message: str) -> None:
    _change(working_copy, path, value)
    assert f"{error_path}: {message}" in lint.check(working_copy)
