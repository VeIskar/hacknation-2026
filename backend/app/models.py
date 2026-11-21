"""Wspólne modele danych przepływu: plik -> ExtractedDocument -> FormAnalysis -> JSON COI.

Umowa między modułami (DELEGACJA.md, rozdz. 2). Zmiana pola = decyzja lidera w DECISIONS.md.
- ExtractedDocument tworzy app/extract (odczyt pliku).
- FormAnalysis tworzy app/analysis (lokalny model), czyta app/generator.
Opisy pól (description) trafiają do schematu JSON, który dostaje model, więc są po polsku
i mówią modelowi, co ma wpisać. Przykłady w opisach są zmyślone albo pochodzą ze zbioru
roboczego (folder 5). Zbiór kontrolny (folder 1) nie może się w nich pojawić: pilnuje tego
tests/test_models.py.
"""

from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

MAX_IMAGES = 20
# 4 x domyślny limit pliku (MAX_FILE_SIZE_MB=10): strona skanu po zapisaniu jako PNG bywa
# kilka razy większa od źródłowego JPG. Największy skan w materiałach COI ma 6,7 MB.
MAX_IMAGES_BYTES = 40 * 1024 * 1024

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceFormat(StrEnum):
    PDF = "pdf"
    DOC = "doc"
    DOCX = "docx"
    ODS = "ods"
    XLSX = "xlsx"
    JPG = "jpg"
    PNG = "png"


class ExtractedDocument(StrictModel):
    """Treść odczytana z pliku formularza. Obiekt wewnętrzny: nie wychodzi poza proces API."""

    # hide_input_in_errors: komunikat błędu walidacji nie cytuje tekstu ani bajtów dokumentu.
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    source_format: SourceFormat = Field(description="Rozszerzenie zwrócone przez files.validate_upload")
    text: str = Field(description="Cały tekst w kolejności czytania; strony rozdzielone znakiem \\f")
    ocr_used: bool = False
    # exclude: model_dump i model_dump_json pomijają obrazy, więc nie trafią do logu ani odpowiedzi.
    # Limity sprawdza się przy tworzeniu obiektu; extract ma przyciąć nadmiar i dodać ostrzeżenie.
    images: list[bytes] = Field(
        default_factory=list,
        max_length=MAX_IMAGES,
        exclude=True,
        repr=False,
        description="Obrazy stron (PNG) dla skanów; model z wejściem obrazowym może czytać je zamiast OCR",
    )
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _images_fit_memory_budget(self) -> Self:
        total = sum(len(image) for image in self.images)
        if total > MAX_IMAGES_BYTES:
            raise ValueError(f"obrazy zajmują {total} bajtów, limit to {MAX_IMAGES_BYTES}")
        return self


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


CHOICE_TYPES = frozenset({FieldType.RADIO, FieldType.CHECKBOX, FieldType.SELECT})


class ShowIf(StrictModel):
    """Pole jest widoczne tylko po wybraniu konkretnej opcji w innym polu tej samej strony."""

    field: Text = Field(description="Etykieta pola wyboru (RADIO, CHECKBOX, SELECT), od którego to zależy")
    equals: Text = Field(description="Nazwa opcji, po której wybraniu pole się pokazuje")


class SubjectField(StrictModel):
    label: Text = Field(description="Etykieta pola prostym językiem, np. 'Numer rachunku'")
    type: FieldType = Field(
        description=(
            "TEXT_FIELD krótki tekst; TEXTAREA uzasadnienie lub opis; NUMBER kwota lub liczba; "
            "DATEPICKER data; RADIO jeden wybór; CHECKBOX wiele wyborów; SELECT ponad 5 opcji; "
            "FILE_UPLOADER załącznik; TEXT_BLOCK sam tekst informacyjny bez wpisywania"
        )
    )
    required: bool = Field(default=True, description="Czy pole jest obowiązkowe")
    description: str = Field(default="", description="Krótka podpowiedź pod etykietą; pusta, gdy zbędna")
    options: list[Text] = Field(
        default_factory=list, description="Opcje dla RADIO, CHECKBOX i SELECT; dla innych typów pusta lista"
    )
    show_if: ShowIf | None = Field(default=None, description="Warunek widoczności; brak, gdy pole widać zawsze")

    @model_validator(mode="after")
    def _options_match_type(self) -> Self:
        if self.type in CHOICE_TYPES:
            if not self.options:
                raise ValueError(f"pole '{self.label}' typu {self.type} wymaga co najmniej jednej opcji")
            # Nazwa opcji staje się jej id w JSON-ie COI (SZABLONY_SEKCJI.md, rozdz. 0).
            if len(set(self.options)) != len(self.options):
                raise ValueError(f"pole '{self.label}' ma powtórzone opcje")
        elif self.options:
            raise ValueError(f"pole '{self.label}' typu {self.type} nie przyjmuje opcji")
        return self


class SubjectSection(StrictModel):
    title: Text = Field(description="Tytuł sekcji tematycznej, np. 'Rozliczenie nadpłaty'")
    description: str = Field(default="", description="Krótki opis sekcji; pusty, gdy zbędny")
    fields: list[SubjectField] = Field(min_length=1)


class SubjectPage(StrictModel):
    title: Text = Field(description="Tytuł strony, np. 'Informacje o nadpłacie'")
    sections: list[SubjectSection] = Field(min_length=1)

    @model_validator(mode="after")
    def _show_if_points_to_one_choice_field(self) -> Self:
        """Etykiety mogą się powtarzać, ale etykieta wskazana w show_if musi być na stronie jedna."""
        fields = [field for section in self.sections for field in section.fields]
        for field in fields:
            condition = field.show_if
            if condition is None:
                continue
            sources = [candidate for candidate in fields if candidate.label == condition.field]
            if not sources:
                raise ValueError(f"show_if pola '{field.label}': na stronie nie ma pola '{condition.field}'")
            if len(sources) > 1:
                raise ValueError(
                    f"show_if pola '{field.label}': etykieta '{condition.field}' jest niejednoznaczna, "
                    f"ma ją {len(sources)} pól na stronie"
                )
            source = sources[0]
            if source is field:
                raise ValueError(f"show_if pola '{field.label}' wskazuje to samo pole")
            if source.type not in CHOICE_TYPES:
                raise ValueError(f"show_if pola '{field.label}': '{source.label}' nie jest polem wyboru")
            if condition.equals not in source.options:
                raise ValueError(
                    f"show_if pola '{field.label}': pole '{source.label}' nie ma opcji '{condition.equals}'"
                )
        return self


class Addressee(StrictModel):
    type: AddresseeType = Field(description="URZAD gdy adresatem jest urząd; ORGAN gdy wójt, burmistrz, prezydent, starosta")
    name: Text = Field(description="Nazwa adresata bez adresu, np. 'Urząd Gminy Ulan-Majorat' albo 'Burmistrz Miasta Lipowo'")


class FormAnalysis(StrictModel):
    """Co jest w papierowym wniosku. Wszystko inne (UUID, układ, sekcje standardowe) dokłada generator.

    model_validate odrzuca niespójną analizę, więc generator dostaje tylko poprawne dane.
    """

    title: Text = Field(max_length=255, description="Tytuł usługi, np. 'Wniosek o stwierdzenie nadpłaty podatku'")
    addressee: Addressee
    applicants: Applicants = Field(
        default=Applicants.BOTH,
        description=(
            "PERSON tylko osoba fizyczna; ENTITY tylko firma lub instytucja; "
            "BOTH gdy wniosek może złożyć i osoba, i firma"
        ),
    )
    signature: bool = Field(default=True, description="Czy wniosek wymaga podpisu")
    subject_pages: list[SubjectPage] = Field(
        min_length=1,
        description="Strony z treścią wniosku. Bez danych wnioskodawcy, adresu, kontaktu, podpisu i daty",
    )
    statements: list[Text] = Field(
        default_factory=list, description="Oświadczenia z wniosku ('Oświadczam, że…'), prostym językiem"
    )
