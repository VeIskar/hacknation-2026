"""Wspólne modele danych przepływu: plik -> ExtractedDocument -> FormAnalysis -> JSON COI.

Umowa między modułami (DELEGACJA.md, rozdz. 2). Zmiana pola = decyzja lidera w DECISIONS.md.
- ExtractedDocument tworzy app/extract (odczyt pliku).
- FormAnalysis opisuje papierowy formularz i trafia do app/generator.
Opisy pól (description) trafiają do schematu JSON, który dostaje model, więc są po polsku
i mówią modelowi, co ma wpisać. Przykłady w opisach są zmyślone albo pochodzą ze zbioru
roboczego (folder 5). Zbiór kontrolny (folder 1) nie może się w nich pojawić: pilnuje tego
tests/test_models.py.
"""

from enum import StrEnum
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

MAX_IMAGES = 20
# 4 x domyślny limit pliku (MAX_FILE_SIZE_MB=10): strona skanu po zapisaniu jako PNG bywa
# kilka razy większa od źródłowego JPG. Największy skan w materiałach COI ma 6,7 MB.
MAX_IMAGES_BYTES = 40 * 1024 * 1024


def _replace_lone_surrogates(value: object) -> object:
    if isinstance(value, str):
        # Dekoder scala poprawne pary surogatów, a samotne zastępuje znakiem U+FFFD.
        return value.encode("utf-16-le", errors="surrogatepass").decode("utf-16-le", errors="replace")
    return value


_NORMALIZE_UNICODE = BeforeValidator(_replace_lone_surrogates)
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1), _NORMALIZE_UNICODE]
DescriptionText = Annotated[str, _NORMALIZE_UNICODE]


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


class EntityId(StrEnum):
    NIP = "NIP"
    REGON = "REGON"
    KRS = "KRS"


class ContactField(StrEnum):
    PHONE = "PHONE"
    EMAIL = "EMAIL"


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
    description: DescriptionText = Field(default="", description="Krótka podpowiedź pod etykietą; pusta, gdy zbędna")
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


def _validate_show_if(fields: list[SubjectField], location: str) -> None:
    """Etykiety mogą się powtarzać, ale etykieta źródła musi wskazywać dokładnie jedno pole."""
    for field in fields:
        condition = field.show_if
        if condition is None:
            continue
        sources = [candidate for candidate in fields if candidate.label == condition.field]
        if not sources:
            raise ValueError(f"show_if pola '{field.label}': {location} nie ma pola '{condition.field}'")
        if len(sources) > 1:
            raise ValueError(
                f"show_if pola '{field.label}': etykieta '{condition.field}' jest niejednoznaczna, "
                f"ma ją {len(sources)} pól {location}"
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


class SubjectSection(StrictModel):
    title: Text = Field(description="Tytuł sekcji tematycznej, np. 'Rozliczenie nadpłaty'")
    description: DescriptionText = Field(default="", description="Krótki opis sekcji; pusty, gdy zbędny")
    fields: list[SubjectField] = Field(min_length=1)


class SubjectPage(StrictModel):
    title: Text = Field(description="Tytuł strony, np. 'Informacje o nadpłacie'")
    sections: list[SubjectSection] = Field(min_length=1)

    @model_validator(mode="after")
    def _show_if_points_to_one_choice_field(self) -> Self:
        fields = [field for section in self.sections for field in section.fields]
        _validate_show_if(fields, "na stronie")
        return self


class ApplicantData(StrictModel):
    """Decyzje o danych wnioskodawcy na podstawie papierowego formularza."""

    proxy: bool = Field(
        description=(
            "Czy papier przewiduje pełnomocnika lub działanie w czyimś imieniu? "
            "Szukaj danych pełnomocnika, pełnomocnictwa lub opłaty za pełnomocnictwo także w objaśnieniach i załącznikach. "
            "Decyzja obejmuje dokument i standardową opłatę skarbową we wszystkich ścieżkach wnioskodawcy."
        )
    )
    applicant_pesel: bool = Field(
        description="Czy papier pyta o PESEL wnioskodawcy? Dokument tożsamości zamiast PESEL zapisz w applicant_extra_fields."
    )
    person_address: bool = Field(description="Czy papier zbiera adres zamieszkania wnioskodawcy będącego osobą fizyczną?")
    entity_ids: list[EntityId] = Field(
        description=(
            "Identyfikatory podmiotu, które użytkownik wpisuje w pola NIP, REGON lub KRS. "
            "Odpis z KRS lub innego rejestru oznacz w representative_proof."
        )
    )
    entity_ids_one_of: bool = Field(description="Czy papier żąda jednego z identyfikatorów, np. NIP lub REGON?")
    entity_address: bool = Field(description="Czy papier zbiera adres siedziby podmiotu?")
    representative_proof: bool = Field(description="Czy papier wymaga odpisu z KRS lub innego rejestru jako dowodu reprezentacji?")
    correspondence_address: bool = Field(description="Czy papier pozwala podać inny adres do korespondencji wnioskodawcy?")
    contact: list[ContactField] = Field(
        description=(
            "PHONE dla pola telefonu i EMAIL dla pola e-mail wnioskodawcy. Pomiń adresy e-mail urzędu i inspektora danych. "
            "Wpisz pustą listę, gdy papier nie zbiera danych do kontaktu."
        )
    )
    applicant_extra_fields: list[SubjectField] = Field(
        description=(
            "Dane wnioskodawcy poza szablonem, np. data urodzenia, seria i numer dowodu, dokument zamiast PESEL lub adres ePUAP. "
            "Warunki show_if wskazują pole z tej samej listy. Wpisz pustą listę, gdy nie ma takich danych."
        )
    )

    @model_validator(mode="after")
    def _validate_decisions(self) -> Self:
        if len(set(self.entity_ids)) != len(self.entity_ids):
            raise ValueError("Identyfikatory podmiotu nie mogą się powtarzać.")
        if self.entity_ids_one_of and len(self.entity_ids) < 2:
            raise ValueError("Wybór jednego identyfikatora wymaga co najmniej dwóch identyfikatorów podmiotu.")
        if len(set(self.contact)) != len(self.contact):
            raise ValueError("Pola kontaktowe nie mogą się powtarzać.")
        _validate_show_if(self.applicant_extra_fields, "w dodatkowych danych wnioskodawcy")
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
        description=(
            "PERSON dla osoby fizycznej, gdy papier pyta o imię i nazwisko wnioskodawcy. "
            "ENTITY dla firmy lub instytucji, gdy papier pyta o nazwę podmiotu. "
            "BOTH gdy papier dopuszcza oba typy wnioskodawców."
        ),
    )
    applicant: ApplicantData = Field(description="Decyzje o sekcjach i dodatkowe dane wnioskodawcy z papieru.")
    signature: bool = Field(default=True, description="Czy wniosek wymaga podpisu")
    subject_pages: list[SubjectPage] = Field(
        min_length=1,
        description=(
            "Zachowaj wszystkie informacje potrzebne do załatwienia sprawy. "
            "Dane pokryte przez szablon zapisz w jego parametrach. "
            "Pozostałe dane wnioskodawcy zapisz w applicant_extra_fields. "
            "Tutaj zapisz resztę informacji z papieru, w tym dane innych osób, daty zdarzeń, załączniki, instrukcje, wybory i ich warunki. "
            "Adresata i podpis zapisz w przeznaczonych do tego polach. "
            "Do statements przenieś oświadczenia wymagane od tej samej osoby w każdej ścieżce. "
            "Zachowaj opcjonalne i warunkowe zgody przy danych, których dotyczą."
        ),
    )
    statements: list[Text] = Field(
        default_factory=list, description="Oświadczenia z wniosku ('Oświadczam, że…'), prostym językiem"
    )

    @model_validator(mode="after")
    def _applicant_matches_type(self) -> Self:
        applicant = self.applicant
        if self.applicants is Applicants.PERSON:
            if applicant.entity_ids_one_of:
                raise ValueError("Osoba fizyczna nie wybiera jednego identyfikatora podmiotu.")
            if applicant.entity_ids:
                raise ValueError("Wniosek osoby fizycznej nie zbiera identyfikatorów podmiotu.")
            if applicant.entity_address:
                raise ValueError("Wniosek osoby fizycznej nie zbiera adresu siedziby.")
            if applicant.representative_proof:
                raise ValueError("Wniosek osoby fizycznej nie wymaga odpisu z rejestru.")
        elif self.applicants is Applicants.ENTITY:
            if applicant.applicant_pesel:
                raise ValueError("Wniosek podmiotu nie zbiera numeru PESEL wnioskodawcy.")
            if applicant.person_address:
                raise ValueError("Wniosek podmiotu nie zbiera adresu zamieszkania wnioskodawcy.")
        return self
