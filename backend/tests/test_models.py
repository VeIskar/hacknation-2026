"""P0: wspólne modele i fixtures są spójne. Te testy pilnują umowy między modułami."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.errors import AppError, ExtractionError, LLMUnavailable, UploadError
from app.models import ExtractedDocument, FieldType, FormAnalysis

FIXTURES = Path(__file__).parent / "fixtures"
COI_EXPECTED = ["expected_nadplata.json", "expected_numer_porzadkowy.json"]
CHOICE_TYPES = {FieldType.RADIO, FieldType.CHECKBOX, FieldType.SELECT}


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_fixture_fields_is_valid_form_analysis() -> None:
    analysis = FormAnalysis.model_validate(load("fields.json"))
    assert analysis.title == "Wniosek o stwierdzenie nadpłaty podatku"
    assert [page.title for page in analysis.subject_pages] == ["Informacje o nadpłacie"]


def test_fixture_show_if_points_to_existing_choice_field_and_option() -> None:
    analysis = FormAnalysis.model_validate(load("fields.json"))
    for page in analysis.subject_pages:
        fields = {f.label: f for s in page.sections for f in s.fields}
        for field in fields.values():
            if field.show_if is None:
                continue
            source = fields[field.show_if.field]
            assert source.type in CHOICE_TYPES
            assert field.show_if.equals in source.options


def test_form_analysis_rejects_page_without_sections() -> None:
    data = load("fields.json")
    data["subject_pages"][0]["sections"] = []
    with pytest.raises(ValidationError):
        FormAnalysis.model_validate(data)


def test_form_analysis_schema_is_json_for_the_model() -> None:
    schema = FormAnalysis.model_json_schema()
    json.dumps(schema)
    assert {"title", "addressee", "subject_pages"} <= set(schema["required"])


def test_extracted_document_minimal() -> None:
    doc = ExtractedDocument(source_format="pdf", text="WNIOSEK")
    assert doc.ocr_used is False and doc.images == [] and doc.warnings == []


@pytest.mark.parametrize("name", COI_EXPECTED)
def test_coi_reference_shape(name: str) -> None:
    form = load(name)
    assert form["tabs"][0]["title"] == "Dane"
    assert form["tabs"][-1]["type"] == "FINISH"
    assert len(form["flow"]["links"]) == len(form["tabs"]) - 1
    for tab in form["tabs"]:
        for question in tab["questions"]:
            assert "repeatingSectionGrid" in question["field"]


def test_errors_carry_http_status() -> None:
    assert UploadError("x").status_code == 400
    assert UploadError("x", 415).status_code == 415
    assert ExtractionError("x").status_code == 422
    assert LLMUnavailable("x").status_code == 503
    assert isinstance(UploadError("x"), AppError)
