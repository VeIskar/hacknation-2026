"""Wspólne modele danych przepływu: plik -> ExtractedDocument -> FormAnalysis -> JSON COI.

Umowa między modułami (DELEGACJA.md, rozdz. 2). Zmiana pola = zgoda całego zespołu.
- ExtractedDocument tworzy app/extract (odczyt pliku).
- FormAnalysis tworzy app/analysis (lokalny model), czyta app/generator.
Opisy pól (description) trafiają do schematu JSON, który dostaje model, więc są po polsku
i mówią modelowi, co ma wpisać.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class ExtractedDocument(BaseModel):
    """Treść odczytana z pliku formularza."""

    source_format: str = Field(description="pdf, doc, docx, ods, xlsx, jpg albo png")
    text: str = Field(description="Cały tekst w kolejności czytania; strony rozdzielone znakiem \\f")
    ocr_used: bool = False
    images: list[bytes] = Field(
        default_factory=list,
        description="Obrazy stron (PNG) dla skanów; model z wejściem obrazowym może czytać je zamiast OCR",
    )
    warnings: list[str] = Field(default_factory=list)


class AddresseeType(StrEnum):
    URZAD = "URZAD"
    ORGAN = "ORGAN"


class Applicants(StrEnum):
    PERSON = "PERSON"
    ENTITY = "ENTITY"
    BOTH = "BOTH"


class FieldType(StrEnum):
    TEXT_FIELD = "TEXT_FIELD"
    TEXTAREA = "TEXTAREA"
    NUMBER = "NUMBER"
    DATEPICKER = "DATEPICKER"
    RADIO = "RADIO"
    CHECKBOX = "CHECKBOX"
    SELECT = "SELECT"
    FILE_UPLOADER = "FILE_UPLOADER"
    TEXT_BLOCK = "TEXT_BLOCK"


class ShowIf(BaseModel):
    """Pole jest widoczne tylko po wybraniu konkretnej opcji w innym polu tej samej strony."""

    field: str = Field(description="Etykieta pola wyboru (RADIO, CHECKBOX, SELECT), od którego to zależy")
    equals: str = Field(description="Nazwa opcji, po której wybraniu pole się pokazuje")


class SubjectField(BaseModel):
    label: str = Field(description="Etykieta pola prostym językiem, np. 'Numer rachunku'")
    type: FieldType = Field(
        description=(
            "TEXT_FIELD krótki tekst; TEXTAREA uzasadnienie lub opis; NUMBER kwota lub liczba; "
            "DATEPICKER data; RADIO jeden wybór; CHECKBOX wiele wyborów; SELECT ponad 5 opcji; "
            "FILE_UPLOADER załącznik; TEXT_BLOCK sam tekst informacyjny bez wpisywania"
        )
    )
    required: bool = Field(default=True, description="Czy pole jest obowiązkowe")
    description: str = Field(default="", description="Krótka podpowiedź pod etykietą; pusta, gdy zbędna")
    options: list[str] = Field(
        default_factory=list, description="Opcje dla RADIO, CHECKBOX i SELECT; dla innych typów pusta lista"
    )
    show_if: ShowIf | None = Field(default=None, description="Warunek widoczności; brak, gdy pole widać zawsze")


class SubjectSection(BaseModel):
    title: str = Field(description="Tytuł sekcji tematycznej, np. 'Rozliczenie nadpłaty'")
    description: str = Field(default="", description="Krótki opis sekcji; pusty, gdy zbędny")
    fields: list[SubjectField] = Field(min_length=1)


class SubjectPage(BaseModel):
    title: str = Field(description="Tytuł strony, np. 'Informacje o nadpłacie'")
    sections: list[SubjectSection] = Field(min_length=1)


class Addressee(BaseModel):
    type: AddresseeType = Field(description="URZAD gdy adresatem jest urząd; ORGAN gdy wójt, burmistrz, prezydent, starosta")
    name: str = Field(description="Nazwa adresata bez adresu, np. 'Urząd Gminy Ulan-Majorat' albo 'Wójt Gminy Elbląg'")


class FormAnalysis(BaseModel):
    """Co jest w papierowym wniosku. Wszystko inne (UUID, układ, sekcje standardowe) dokłada generator."""

    title: str = Field(max_length=255, description="Tytuł usługi, np. 'Wniosek o stwierdzenie nadpłaty podatku'")
    addressee: Addressee
    applicants: Applicants = Field(
        default=Applicants.BOTH,
        description="PERSON tylko osoba fizyczna; ENTITY tylko firma lub instytucja; BOTH gdy oba (np. 'imię i nazwisko/nazwa')",
    )
    signature: bool = Field(default=True, description="Czy wniosek wymaga podpisu")
    subject_pages: list[SubjectPage] = Field(
        min_length=1,
        description="Strony z treścią wniosku. Bez danych wnioskodawcy, adresu, kontaktu, podpisu i daty",
    )
    statements: list[str] = Field(
        default_factory=list, description="Oświadczenia z wniosku ('Oświadczam, że…'), prostym językiem"
    )
