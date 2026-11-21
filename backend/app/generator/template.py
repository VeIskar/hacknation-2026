"""Strony standardowe: „Dane”, „Kontakt i zgody”, „Strona końcowa” (SZABLONY_SEKCJI.md, rozdz. 3–4).

Decyzje z ApplicantData wyznaczają sekcje i pola wnioskodawcy. techName szablonu są stałe
i mają pierwszeństwo przed nazwami z przedmiotu wniosku.
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
from app.models import (
    AddresseeType,
    ApplicantData,
    Applicants,
    ContactField,
    EntityId,
    FormAnalysis,
)

DATA_PAGE = "Dane"
CONTACT_PAGE = "Kontakt i zgody"
FINISH_PAGE = "Strona końcowa"
TEMPLATE_PAGES = (DATA_PAGE, CONTACT_PAGE, FINISH_PAGE)

REQUIRED = "REQUIRED"

APPLICANT_SECTION = "podmiot_wniosku"
POWER_OF_ATTORNEY = "pelnomocnictwo"
ON_BEHALF = "wybierz_w_czyim_imieniu_wnioskujesz"
ROLE = "wybierz_jako_kto_wnioskujesz"
OWN = "Swoim"
OTHER_PERSON = "Innej osoby"
LEGAL_ENTITY = "Osoby prawnej lub jednostki organizacyjnej"
ATTORNEY = "Pełnomocnik"
REPRESENTATIVE = "Reprezentant"
POLAND = "Polska"

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


def _applicant_answer(option: str, radio: str) -> str:
    return answer_is(option, DATA_PAGE, APPLICANT_SECTION, radio)


def _and(guard: str, query: str) -> str:
    return f"{guard} and {query}" if guard else query


def _applicant(title: str, options: list[str], *, has_role: bool, when_entity: str) -> dict | None:
    """S2: radia tylko tam, gdzie podpisujący ma wybór."""
    verb = applicant_verb(title)
    fields = []
    if options:
        fields.append(field("RADIO", ON_BEHALF, f"Wybierz, w czyim imieniu {verb}", options=options, validation=[REQUIRED]))
    if has_role:
        fields.append(
            field(
                "RADIO",
                ROLE,
                f"Wybierz, jako kto {verb}",
                options=[ATTORNEY, REPRESENTATIVE],
                validation=[REQUIRED],
                states=show(when_entity),
            )
        )
    return section(APPLICANT_SECTION, "Podmiot wniosku", fields) if fields else None


def _your_data(include_pesel: bool) -> dict:
    """S3: dane inicjalne do odczytu, z PESEL tylko gdy wymaga go formularz."""
    fields = [
        _text("imie", "Imię", read_only=True, **_registry("name")),
        _text("nazwisko", "Nazwisko", read_only=True, **_registry("surname")),
    ]
    if include_pesel:
        fields.append(_text("numer_pesel", "Numer PESEL", read_only=True, **_registry("pesel")))
    return section("twoje_dane", "Twoje dane", fields)


def _address_fields(tech_name: str, suffix: str, *, prefilled: bool, when: str = "") -> list[dict]:
    """Szablon adresu (9 pól). Dane inicjalne MLPZ.* tylko w adresie wnioskodawcy."""
    country = f"kraj{suffix}"
    visible = show(when)
    in_poland = show(_and(when, answer_is(POLAND, DATA_PAGE, tech_name, country)))
    abroad = show(_and(when, answer_is_not(POLAND, DATA_PAGE, tech_name, country)))

    def registry(key: str) -> dict:
        return _registry(key) if prefilled else {}

    return [
        field("SELECT", country, "Kraj", dictionaryName="Kraje", defaultValue=[POLAND], searchEnabled=True, states=visible),
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
        _text(f"numer_budynku{suffix}", "Numer budynku", states=visible, **registry("building")),
        _text(f"numer_lokalu{suffix}", "Numer lokalu", states=visible, **registry("apartment")),
    ]


def _address(tech_name: str, title: str, suffix: str, *, prefilled: bool, states: Iterable[dict] = ()) -> dict:
    fields = _address_fields(tech_name, suffix, prefilled=prefilled)
    return section(tech_name, title, fields, states=states)


def _correspondence_address() -> dict:
    tech_name = "adres_do_korespondencji"
    radio = field(
        "RADIO", "czy_adres_do_korespondencji_jest_inny", "Czy adres do korespondencji jest inny?",
        options=["Tak", "Nie"], validation=[REQUIRED],
    )
    when_different = answer_is("Tak", DATA_PAGE, tech_name, radio["techName"])
    address = _address_fields(tech_name, "_korespondencyjny", prefilled=False, when=when_different)
    return section(tech_name, "Adres do korespondencji", [radio, *address])


def _entity_data(applicant: ApplicantData, when_entity: str) -> dict:
    """S4: nazwa i wskazane identyfikatory w kolejności z szablonu."""
    fields = [_text("nazwa", "Nazwa")]
    identifiers = [identifier.value for identifier in EntityId if identifier in applicant.entity_ids]
    for identifier in identifiers:
        if identifier == "KRS":
            fields.append(_text("numer_krs", "Numer KRS"))
        else:
            validation = [identifier] if applicant.entity_ids_one_of else [REQUIRED, identifier]
            fields.append(_text(identifier.lower(), identifier, validation=validation))
    hint = f"Podaj jeden z: {', '.join(identifiers)}." if applicant.entity_ids_one_of else ""
    return section("dane_podmiotu", "Dane podmiotu", fields, body=paragraphs(hint), states=show(when_entity))


def _representative(when_representative: str) -> dict:
    """S8: odpis z rejestru, gdy osoba prawna i reprezentant."""
    return section(
        "potwierdzenie_ze_jestes_reprezentantem",
        "Potwierdzenie, że jesteś reprezentantem",
        [_upload("plik_z_odpisem_danych", "Plik z odpisem danych")],
        body=paragraphs(REPRESENTATIVE_INFO),
        states=show(when_representative),
    )


def _other_person(when_other: str) -> dict:
    """S6: dane osoby, w której imieniu się wnioskuje (oba wzorce: bez PESEL)."""
    return section(
        "dane_innej_osoby",
        "Dane innej osoby",
        [_text("imie_inna_osoba", "Imię"), _text("nazwisko_inna_osoba", "Nazwisko")],
        states=show(when_other),
    )


def _power_of_attorney(when_proxy: str) -> dict:
    """S9: dokument dla dostępnych ścieżek pełnomocnika."""
    return section(
        POWER_OF_ATTORNEY,
        "Pełnomocnictwo",
        [_upload("plik_dokumentu_z_pelnomocnictwem", "Plik dokumentu z pełnomocnictwem")],
        body=paragraphs(ATTORNEY_INFO),
        states=show(when_proxy),
    )


def _person_fee(title: str, when_other: str) -> dict:
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
        states=show(when_other),
    )


def _entity_fee(title: str, when_attorney: str) -> dict:
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
        states=show(when_attorney),
    )


def data_page(a: FormAnalysis) -> dict:
    """Ustala dostępne ścieżki przed zbudowaniem warunków SHOW i sekcji."""
    applicant = a.applicant
    own = a.applicants in (Applicants.PERSON, Applicants.BOTH)
    other = own and applicant.proxy
    entity = a.applicants in (Applicants.ENTITY, Applicants.BOTH)
    paths = [name for name, available in [(OWN, own), (OTHER_PERSON, other), (LEGAL_ENTITY, entity)] if available]
    on_behalf_options = paths if len(paths) > 1 else []
    has_role = entity and applicant.proxy

    # Przy jednej opcji ścieżka jest stała. Nie odwołujemy się wtedy do radia ON_BEHALF.
    when_entity = _applicant_answer(LEGAL_ENTITY, ON_BEHALF) if LEGAL_ENTITY in on_behalf_options else ""
    when_other = _applicant_answer(OTHER_PERSON, ON_BEHALF) if OTHER_PERSON in on_behalf_options else ""
    when_representative = when_entity
    when_attorney = ""
    if has_role:
        when_representative = _and(when_entity, _applicant_answer(REPRESENTATIVE, ROLE))
        when_attorney = _and(when_entity, _applicant_answer(ATTORNEY, ROLE))

    sections = [_addressee(a)]
    selection = _applicant(a.title, on_behalf_options, has_role=has_role, when_entity=when_entity)
    if selection is not None:
        sections.append(selection)
    sections.append(_your_data(applicant.applicant_pesel))
    if own and applicant.person_address:
        sections.append(_address("adres_zamieszkania", "Adres zamieszkania", "", prefilled=True))
    if entity:
        sections.append(_entity_data(applicant, when_entity))
        if applicant.entity_address:
            sections.append(_address("adres_siedziby", "Adres siedziby", "_siedziba", prefilled=False, states=show(when_entity)))
        if applicant.representative_proof:
            sections.append(_representative(when_representative))
    if other:
        sections.append(_other_person(when_other))
        if applicant.person_address:
            sections.append(
                _address(
                    "adres_zamieszkania_osoby_ktorej_jestes_pelnomocnikiem",
                    "Adres zamieszkania innej osoby",
                    "_inna_osoba",
                    prefilled=False,
                    states=show(when_other),
                )
            )
    if applicant.correspondence_address:
        sections.append(_correspondence_address())
    if applicant.proxy:
        when_proxy = f"{when_other} or ({when_attorney})" if other and has_role else when_other or when_attorney
        sections.append(_power_of_attorney(when_proxy))
        if other:
            sections.append(_person_fee(a.title, when_other))
        if has_role:
            sections.append(_entity_fee(a.title, when_attorney))
    return tab(DATA_PAGE, sections)


# --- strony końcowe -------------------------------------------------------------------------------


def contact_page(a: FormAnalysis) -> dict:
    """S12 według papieru, S13 ze zgodą bazową i oświadczeniami."""
    fields = []
    if ContactField.PHONE in a.applicant.contact:
        fields.append(_text("numer_telefonu", "Numer telefonu", **_registry("phoneNumber")))
    if ContactField.EMAIL in a.applicant.contact:
        fields.append(_text("adres_e_mail", "Adres e-mail", validation=["EMAIL"], **_registry("email")))

    sections = []
    if fields:
        sections.append(section("dane_do_kontaktu", "Dane do kontaktu", fields, body=paragraphs(CONTACT_INFO)))
    consents = [{"description": html_document(_privacy_consent()), "required": True}]
    consents += [{"description": html_document(paragraphs(text)), "required": True} for text in a.statements]
    consent = field("CONSENT_SECTION", "zgoda", consentSectionConfig={"consents": consents, "files": []})
    title = "Zgody i oświadczenia" if a.statements else "Zgoda"
    sections.append(section("zgoda_wyrazenie", title, [consent]))
    return tab(CONTACT_PAGE, sections)


def finish_page(a: FormAnalysis) -> dict:
    """S14: strona FINISH z samym TEXT_BLOCK; tekst zależy od tego, czy wniosek się podpisuje."""
    text = PREVIEW_BEFORE_SIGNATURE if a.signature else PREVIEW_BEFORE_SENDING
    preview = field("TEXT_BLOCK", "podglad_1", description=html_document(paragraphs(text)))
    return tab(FINISH_PAGE, [section("podglad_uzupelnionego_wniosku", "Podgląd uzupełnionego wniosku", [preview])], "FINISH")
