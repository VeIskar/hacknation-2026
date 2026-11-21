"""Błędy przepływu: argumenty tylko nazwane, kod HTTP z zamkniętego zbioru (DECISIONS.md, D1 i D2)."""

import copy
import pickle

import pytest

from app.errors import AppError, ExtractionError, LLMUnavailable, UploadError


def test_errors_carry_detail_and_default_status() -> None:
    assert AppError(detail="x").status_code == 500
    assert UploadError(detail="x").status_code == 400
    assert ExtractionError(detail="x").status_code == 400
    assert LLMUnavailable(detail="x").status_code == 503
    error = UploadError(detail="Plik jest za duży.", status_code=413)
    assert (error.detail, error.status_code, str(error)) == ("Plik jest za duży.", 413, "Plik jest za duży.")
    assert isinstance(error, AppError)


def test_positional_arguments_are_rejected() -> None:
    with pytest.raises(TypeError):
        UploadError("x")
    # Kolejność sprzed P0.1 (status, detail) nie może przejść po cichu.
    with pytest.raises(TypeError):
        UploadError(415, "Zawartość pliku nie pasuje do rozszerzenia .pdf.")
    with pytest.raises(TypeError):
        LLMUnavailable("Model AI nie odpowiada.")


@pytest.mark.parametrize("detail", [415, None, b"x", ["x"]])
def test_detail_must_be_text(detail: object) -> None:
    with pytest.raises(TypeError, match="detail"):
        AppError(detail=detail)


@pytest.mark.parametrize("detail", ["", "   "])
def test_detail_must_not_be_empty(detail: str) -> None:
    with pytest.raises(ValueError, match="detail"):
        AppError(detail=detail)


@pytest.mark.parametrize("status_code", ["415", 415.0, True])
def test_status_code_must_be_an_integer(status_code: object) -> None:
    with pytest.raises(TypeError, match="status_code"):
        AppError(detail="x", status_code=status_code)


@pytest.mark.parametrize("status_code", [200, 399, 600])
def test_app_error_accepts_only_http_error_codes(status_code: int) -> None:
    with pytest.raises(ValueError, match="kodu HTTP"):
        AppError(detail="x", status_code=status_code)


@pytest.mark.parametrize("status_code", [400, 599])
def test_app_error_accepts_the_edges_of_the_error_range(status_code: int) -> None:
    assert AppError(detail="x", status_code=status_code).status_code == status_code


@pytest.mark.parametrize("clone", [copy.copy, copy.deepcopy, lambda error: pickle.loads(pickle.dumps(error))])
def test_errors_survive_copy_and_pickle(clone) -> None:
    error = clone(UploadError(detail="Plik jest za duży.", status_code=413))
    assert (type(error), error.detail, error.status_code) == (UploadError, "Plik jest za duży.", 413)


@pytest.mark.parametrize("status_code", [400, 413, 415])
def test_upload_error_accepts_its_three_codes(status_code: int) -> None:
    assert UploadError(detail="x", status_code=status_code).status_code == status_code


@pytest.mark.parametrize(
    ("error", "status_code"),
    [(UploadError, 422), (UploadError, 503), (ExtractionError, 422), (ExtractionError, 415), (LLMUnavailable, 500)],
)
def test_subclasses_reject_codes_outside_the_api_contract(error: type[AppError], status_code: int) -> None:
    with pytest.raises(ValueError, match="kodu HTTP"):
        error(detail="x", status_code=status_code)
