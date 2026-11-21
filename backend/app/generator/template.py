"""Strony standardowe: „Dane”, „Kontakt i zgody”, „Strona końcowa” (SZABLONY_SEKCJI.md, rozdz. 3–4).

Z analizy biorą tylko parametry z rozdz. 1: tytuł, adresata, rodzaj wnioskodawcy, podpis
i oświadczenia. techName są stałe i mają pierwszeństwo przed nazwami z przedmiotu wniosku.
Walidatory z rozdz. 5 są zawsze wpisane; build_form czyści je, gdy ADD_VALIDATORS = False.
"""

import html
import re
import unicodedata
from collections.abc import Iterable

from app.generator.coi import (
    answer_is,
    answer_is_not,
    field,
    html_document,
    link,
    paragraphs,
    section,
    show,
    tab,
)
from app.models import AddresseeType, Applicants, FormAnalysis

DATA_PAGE = "Dane"
CONTACT_PAGE = "Kontakt i zgody"
FINISH_PAGE = "Strona końcowa"
TEMPLATE_PAGES = (DATA_PAGE, CONTACT_PAGE, FINISH_PAGE)

REQUIRED = "REQUIRED"

APPLICANT_SECTION = "podmiot_wniosku"
ON_BEHALF = "wybierz_w_czyim_imieniu_wnioskujesz"
ROLE = "wybierz_jako_kto_wnioskujesz"
OWN = "Swoim"
OTHER_PERSON = "Innej osoby"
LEGAL_ENTITY = "Osoby prawnej lub jednostki organizacyjnej"
ATTORNEY = "Pełnomocnik"
REPRESENTATIVE = "Reprezentant"
POLAND = "Polska"

# Skróty z SZABLONY, rozdz. 0: [INNA], [PRAWNA], [PEŁN], [REPR].
FOR_OTHER_PERSON = answer_is(OTHER_PERSON, DATA_PAGE, APPLICANT_SECTION, ON_BEHALF)
FOR_LEGAL_ENTITY = answer_is(LEGAL_ENTITY, DATA_PAGE, APPLICANT_SECTION, ON_BEHALF)
AS_ATTORNEY = answer_is(ATTORNEY, DATA_PAGE, APPLICANT_SECTION, ROLE)
AS_REPRESENTATIVE = answer_is(REPRESENTATIVE, DATA_PAGE, APPLICANT_SECTION, ROLE)

# Adres klauzuli informacyjnej urzędu. Pusty = zgoda bez linku (wzorce COI mają tu zepsuty adres).
PRIVACY_CLAUSE_URL = ""
FEE_EXEMPTION_URL = "https://www.biznes.gov.pl/pl/portal/0089#8"
FEE_DETAILS_URL = "https://www.biznes.gov.pl/pl/portal/0089#9"
FEE_ABROAD_URL = "https://warszawa19115.pl/-/oplata-skarbowa"

REPRESENTATIVE_INFO = (
    "Dołącz aktualny odpis danych z Krajowego Rejestru Sądowego lub innego rejestru. "
    "Odpis powinien potwierdzać, że jesteś reprezentantem podmiotu lub instytucji."
)
ATTORNEY_INFO = "Dodaj dokument potwierdzający, że jesteś pełnomocnikiem."
FEE_EXEMPTION_INFO = (
    "<p>Nie musisz płacić za złożenie pełnomocnictwa wystawionego przez najbliższą rodzinę: "
    "małżonka, dzieci, rodziców, dziadków, wnuków, rodzeństwo. Więcej informacji na stronie "
    f"{link(FEE_EXEMPTION_URL, 'biznes.gov.pl')}.</p>"
)
CONTACT_INFO = (
    "Wpisanie danych do kontaktu może przyspieszyć załatwienie sprawy. Urzędnik będzie mógł "
    "skontaktować się z Tobą w przypadku pytań lub wątpliwości.\n"
    "Jeśli widzisz uzupełnione dane, sprawdź, czy są poprawne. Możesz je zmienić lub usunąć."
)
PREVIEW_BEFORE_SIGNATURE = (
    "Zanim przejdziesz do wyboru sposobu podpisu, sprawdź dane na podglądzie. "
    "Jeśli zobaczysz błędy, wróć do edycji."
)
PREVIEW_BEFORE_SENDING = (
    "Zanim wyślesz wniosek, sprawdź uzupełnione dane na podglądzie. Jeśli zobaczysz błędy, wróć do edycji."
)


def _registry(key: str) -> dict:
    """Dane inicjalne z rejestru (Standardy: MLPZ.*)."""
    return {"defaultValue": f"MLPZ.{key}", "defaultValueType": "EXTERNAL_SYSTEM"}


def _text(tech_name: str, title: str, **kwargs: object) -> dict:
    return field("TEXT_FIELD", tech_name, title, **kwargs)


def _upload(tech_name: str, title: str, **kwargs: object) -> dict:
    return field("FILE_UPLOADER", tech_name, title, validation=[REQUIRED], **kwargs)


def _fee_info(title: str, payer: str) -> str:
    """Treść TEXT_BLOCK o opłacie skarbowej; tytuł wniosku pochodzi od modelu, więc jest escapowany."""
    abroad = link(FEE_ABROAD_URL, "Urzędu Miasta Stołecznego Warszawy – Centrum Obsługi Podatnika")
    return (
        "<p>Opłata skarbowa za pełnomocnictwo wynosi <strong>17 zł</strong>.</p>"
        f"<p>Przelej ją na konto urzędu miasta lub gminy właściwego dla adresu {payer}. "
        f"Jeśli adres nie jest w Polsce, opłatę przelej na konto {abroad}.</p>"
        f"<p>W tytule przelewu wpisz „{html.escape(title, quote=False)} – opłata skarbowa za pełnomocnictwo”.</p>"
    )


def _privacy_consent() -> str:
    """Zgoda bazowa; link tylko wtedy, gdy znamy adres klauzuli (czytany przy każdym wywołaniu)."""
    clause = link(PRIVACY_CLAUSE_URL, "klauzulą informacyjną") if PRIVACY_CLAUSE_URL else "klauzulą informacyjną"
    return f"<p>Wyrażam zgodę na przetwarzanie moich danych osobowych zgodnie z {clause}.</p>"


# SZABLONY, rozdz. 1: CZASOWNIK w etykietach zależy od rodzaju dokumentu.
VERBS = {"wniosek": "wnioskujesz", "zgłoszenie": "zgłaszasz", "deklaracja": "deklarujesz"}


def applicant_verb(title: str) -> str:
    """Pierwsze słowo tytułu: „Zgłoszenie …” -> „zgłaszasz”; nieznane słowo -> „wnioskujesz”."""
    first = re.match(r"\w+", unicodedata.normalize("NFC", title).strip())
    return VERBS.get(first.group().casefold() if first else "", "wnioskujesz")


# --- strona „Dane” --------------------------------------------------------------------------------


def _addressee(a: FormAnalysis) -> dict:
    """S1: nazwa urzędu albo organu tylko do odczytu, z wartością z analizy."""
    if a.addressee.type is AddresseeType.ORGAN:
        tech_name, title, label, tech_field = "organ_do_ktorego_jest_skladany_wniosek", "Organ", "Nazwa organu", "nazwa_organu"
    else:
        tech_name, title, label, tech_field = "urzad_do_ktorego_jest_skladany_wniosek", "Urząd", "Nazwa urzędu", "nazwa_urzedu"
    name = _text(tech_field, label, read_only=True, defaultValue=a.addressee.name)
    return section(tech_name, f"{title}, do którego jest składany wniosek", [name])


def _applicant(a: FormAnalysis) -> dict:
    """S2: radio „w czyim imieniu” z opcjami wg wariantu; radio „jako kto” tylko z osobą prawną.

    Czasownik zmienia tylko etykiety. techName zostają stałe, bo od nich zależą warunki SHOW.
    """
    verb = applicant_verb(a.title)
    options = {
        Applicants.PERSON: [OWN, OTHER_PERSON],
        Applicants.ENTITY: [LEGAL_ENTITY],
        Applicants.BOTH: [OWN, OTHER_PERSON, LEGAL_ENTITY],
    }[a.applicants]
    fields = [field("RADIO", ON_BEHALF, f"Wybierz, w czyim imieniu {verb}", options=options, validation=[REQUIRED])]
    if a.applicants is not Applicants.PERSON:
        fields.append(
            field(
                "RADIO",
                ROLE,
                f"Wybierz, jako kto {verb}",
                options=[ATTORNEY, REPRESENTATIVE],
                validation=[REQUIRED],
                states=show(FOR_LEGAL_ENTITY),
            )
        )
    return section(APPLICANT_SECTION, "Podmiot wniosku", fields)


def _your_data() -> dict:
    """S3: dane zalogowanej osoby z rejestru, tylko do odczytu, bez walidatorów (rozdz. 5)."""
    return section(
        "twoje_dane",
        "Twoje dane",
        [
            _text("imie", "Imię", read_only=True, **_registry("name")),
            _text("nazwisko", "Nazwisko", read_only=True, **_registry("surname")),
            _text("numer_pesel", "Numer PESEL", read_only=True, **_registry("pesel")),
        ],
    )


def _address(tech_name: str, title: str, suffix: str, *, prefilled: bool, states: Iterable[dict] = ()) -> dict:
    """Szablon adresu (9 pól). Dane inicjalne MLPZ.* tylko w adresie wnioskodawcy."""
    country = f"kraj{suffix}"
    in_poland = show(answer_is(POLAND, DATA_PAGE, tech_name, country))
    abroad = show(answer_is_not(POLAND, DATA_PAGE, tech_name, country))

    def registry(key: str) -> dict:
        return _registry(key) if prefilled else {}

    fields = [
        field("SELECT", country, "Kraj", dictionaryName="Kraje", defaultValue=[POLAND], searchEnabled=True),
        _text(f"miejscowosc{suffix}_zagranica", "Miejscowość", states=abroad),
        _text(f"kod_pocztowy{suffix}_zagranica", "Kod pocztowy", states=abroad),
        _text(f"ulica{suffix}_zagranica", "Ulica", states=abroad),
        field(
            "SELECT",
            f"wojewodztwo{suffix}",
            "Województwo",
            states=in_poland,
            dictionaryName="TERYT_4G_DOWODOWY",
            multiLevelTree=True,
            searchEnabled=True,
            defaultValue=[],
        ),
        _text(
            f"kod_pocztowy{suffix}",
            "Kod pocztowy",
            validation=[REQUIRED, "ZIP_CODE"],
            states=in_poland,
            **registry("postCode"),
        ),
        _text(f"ulica{suffix}", "Ulica", states=in_poland, **registry("street")),
        _text(f"numer_budynku{suffix}", "Numer budynku", **registry("building")),
        _text(f"numer_lokalu{suffix}", "Numer lokalu", **registry("apartment")),
    ]
    return section(tech_name, title, fields, states=states)


def _entity_data() -> dict:
    """S4: pełna wersja (Nazwa, NIP, REGON, KRS) – decyzja w SZABLONY, rozdz. 3."""
    return section(
        "dane_podmiotu",
        "Dane podmiotu",
        [
            _text("nazwa", "Nazwa"),
            _text("nip", "NIP", validation=[REQUIRED, "NIP"]),
            _text("regon", "REGON", validation=[REQUIRED, "REGON"]),
            _text("numer_krs", "Numer KRS"),
        ],
        states=show(FOR_LEGAL_ENTITY),
    )


def _representative() -> dict:
    """S8: odpis z rejestru, gdy osoba prawna i reprezentant."""
    return section(
        "potwierdzenie_ze_jestes_reprezentantem",
        "Potwierdzenie, że jesteś reprezentantem",
        [_upload("plik_z_odpisem_danych", "Plik z odpisem danych")],
        body=paragraphs(REPRESENTATIVE_INFO),
        states=show(f"{FOR_LEGAL_ENTITY} and {AS_REPRESENTATIVE}"),
    )


def _other_person() -> dict:
    """S6: dane osoby, w której imieniu się wnioskuje (oba wzorce: bez PESEL)."""
    return section(
        "dane_innej_osoby",
        "Dane innej osoby",
        [_text("imie_inna_osoba", "Imię"), _text("nazwisko_inna_osoba", "Nazwisko")],
        states=show(FOR_OTHER_PERSON),
    )


def _power_of_attorney(applicants: Applicants) -> dict:
    """S9: przy „Innej osoby” i przy osobie prawnej z pełnomocnikiem – o ile wariant ma te opcje."""
    entity_attorney = f"{FOR_LEGAL_ENTITY} and {AS_ATTORNEY}"
    query = {
        Applicants.PERSON: FOR_OTHER_PERSON,
        Applicants.ENTITY: entity_attorney,
        Applicants.BOTH: f"{FOR_OTHER_PERSON} or ({entity_attorney})",
    }[applicants]
    return section(
        "pelnomocnictwo",
        "Pełnomocnictwo",
        [_upload("plik_dokumentu_z_pelnomocnictwem", "Plik dokumentu z pełnomocnictwem")],
        body=paragraphs(ATTORNEY_INFO),
        states=show(query),
    )


def _person_fee(title: str) -> dict:
    """S10: opłata za pełnomocnictwo od osoby fizycznej, z pytaniem, czy jest wymagana."""
    tech_name, question = "oplata_skarbowa_pelnomocnictwo_1", "czy_zlozenie_pelnomocnictwa_wymaga_oplaty_skarbowej"
    when_paid = show(answer_is("Tak", DATA_PAGE, tech_name, question))
    fee = _fee_info(title, "zamieszkania osoby, która udzieliła pełnomocnictwa")
    return section(
        tech_name,
        "Opłata skarbowa",
        [
            field(
                "RADIO",
                question,
                "Czy złożenie pełnomocnictwa wymaga opłaty skarbowej?",
                options=["Tak", "Nie"],
                validation=[REQUIRED],  # Standardy COI: „walidacja: pole wymagane”
            ),
            field("TEXT_BLOCK", "oplata_info_1", description=html_document(fee), states=when_paid),
            _upload("plik_z_potwierdzeniem_przelewu", "Plik z potwierdzeniem przelewu", states=when_paid),
        ],
        body=FEE_EXEMPTION_INFO,
        states=show(FOR_OTHER_PERSON),
    )


def _entity_fee(title: str) -> dict:
    """S11: opłata za pełnomocnictwo udzielone przez podmiot (tytuł bez literówki ze wzorców)."""
    more = f"<p>Więcej informacji o opłacie skarbowej za pełnomocnictwo znajdziesz na stronie {link(FEE_DETAILS_URL, 'biznes.gov.pl')}.</p>"
    fee = _fee_info(title, "siedziby podmiotu, który udzielił pełnomocnictwa") + more
    return section(
        "oplata_skarbowa_pelnomocnictwo_2",
        "Opłata skarbowa za pełnomocnictwo",
        [
            field("TEXT_BLOCK", "oplata_info", description=html_document(fee)),
            _upload("plik_z_potwierdzeniem_przelewu_2", "Plik z potwierdzeniem przelewu"),
        ],
        states=show(f"{FOR_LEGAL_ENTITY} and {AS_ATTORNEY}"),
    )


def data_page(a: FormAnalysis) -> dict:
    """Strona „Dane”: S1, S2, S3, S4a, S4, S5, S8, S6, S7, S9, S10, S11 – bez sekcji spoza wariantu."""
    person = a.applicants in (Applicants.PERSON, Applicants.BOTH)
    entity = a.applicants in (Applicants.ENTITY, Applicants.BOTH)
    sections = [_addressee(a), _applicant(a), _your_data()]
    sections.append(_address("adres_zamieszkania", "Adres zamieszkania", "", prefilled=True))
    if entity:
        sections.append(_entity_data())
        sections.append(_address("adres_siedziby", "Adres siedziby", "_siedziba", prefilled=False, states=show(FOR_LEGAL_ENTITY)))
        sections.append(_representative())
    if person:
        sections.append(_other_person())
        sections.append(
            _address(
                "adres_zamieszkania_osoby_ktorej_jestes_pelnomocnikiem",
                "Adres zamieszkania innej osoby",
                "_inna_osoba",
                prefilled=False,
                states=show(FOR_OTHER_PERSON),
            )
        )
    sections.append(_power_of_attorney(a.applicants))
    if person:
        sections.append(_person_fee(a.title))
    if entity:
        sections.append(_entity_fee(a.title))
    return tab(DATA_PAGE, sections)


# --- strony końcowe -------------------------------------------------------------------------------


def contact_page(a: FormAnalysis) -> dict:
    """S12 kontakt z danymi inicjalnymi; S13 zgoda bazowa i oświadczenia z papieru, każde wymagane."""
    contact = section(
        "dane_do_kontaktu",
        "Dane do kontaktu",
        [
            _text("numer_telefonu", "Numer telefonu", **_registry("phoneNumber")),
            _text("adres_e_mail", "Adres e-mail", validation=["EMAIL"], **_registry("email")),
        ],
        body=paragraphs(CONTACT_INFO),
    )
    consents = [{"description": html_document(_privacy_consent()), "required": True}]
    consents += [{"description": html_document(paragraphs(text)), "required": True} for text in a.statements]
    consent = field("CONSENT_SECTION", "zgoda", consentSectionConfig={"consents": consents, "files": []})
    title = "Zgody i oświadczenia" if a.statements else "Zgoda"
    return tab(CONTACT_PAGE, [contact, section("zgoda_wyrazenie", title, [consent])])


def finish_page(a: FormAnalysis) -> dict:
    """S14: strona FINISH z samym TEXT_BLOCK; tekst zależy od tego, czy wniosek się podpisuje."""
    text = PREVIEW_BEFORE_SIGNATURE if a.signature else PREVIEW_BEFORE_SENDING
    preview = field("TEXT_BLOCK", "podglad_1", description=html_document(paragraphs(text)))
    return tab(FINISH_PAGE, [section("podglad_uzupelnionego_wniosku", "Podgląd uzupełnionego wniosku", [preview])], "FINISH")
