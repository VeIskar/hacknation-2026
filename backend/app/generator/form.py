"""build_form: FormAnalysis -> JSON COI (SZABLONY_SEKCJI.md, DELEGACJA.md rozdz. 2.2).

Wejście przeszło FormAnalysis.model_validate (D4), ale walidacja nie pilnuje wszystkiego.
Generator sam:
- nadaje techName unikalne w całym formularzu (szablon ma pierwszeństwo, kolizje dostają _2, _3),
- zmienia tytuł strony przedmiotu, który powtarza stronę standardową albo inną stronę,
- escapuje tekst od modelu w HTML-u i w literałach jsonaty,
- nie daje REQUIRED polom TEXT_BLOCK.
Ten sam FormAnalysis daje identyczny JSON: identyfikatory to UUID5, nie losowe UUID4.
"""

import html
import json
import re
import unicodedata
import uuid
from collections.abc import Iterable
from itertools import pairwise

from app.generator import template
from app.generator.coi import (
    Names,
    answer_is,
    field,
    field_description,
    html_document,
    iter_fields,
    paragraphs,
    section,
    show,
    tab,
)
from app.models import FieldType, FormAnalysis, SubjectField, SubjectSection

# SZABLONY, rozdz. 5: walidatory to nasze rozszerzenie. False = validation [] wszędzie, jak we wzorcach.
ADD_VALIDATORS = True

# Stała przestrzeń nazw UUID5. Zmiana zmienia identyfikatory we wszystkich generowanych formularzach.
ID_NAMESPACE = uuid.UUID("7319e414-8854-44a5-ae2b-fdac98e7d0b9")

_POLISH_LETTERS = str.maketrans("ąćęłńóśźż", "acelnoszz")
_LABEL_VALIDATORS = {
    "PESEL": re.compile(r"\bpesel\b"),
    "NIP": re.compile(r"\bnip\b"),
    "REGON": re.compile(r"\bregon\b"),
    "ZIP_CODE": re.compile(r"\bkod\s+pocztowy\b"),
    "EMAIL": re.compile(r"\b(?:e-mail|email|adres\s+poczty\s+elektronicznej)\b"),
    "SERIAL_NUMBER_ID_CARD": re.compile(r"\bseria\s+i\s+numer\s+dowodu\b"),
    "EPUAP": re.compile(r"\bepuap\b"),
    "ADE": re.compile(r"\b(?:e-doreczen|adres\s+do\s+doreczen\s+elektronicznych)\b"),
}
_COMPOUND_LABEL = re.compile(
    r"[,;/]|\b(?:i|oraz|lub|albo|telefon(?:u)?|tel|miejscowosc|ulica|imie|nazwisko|data|"
    r"paszport(?:u)?|dokument(?:u)?|domu|lokalu)\b"
)


def build_form(a: FormAnalysis) -> dict:
    """Gotowy JSON COI: „Dane”, strony przedmiotu, „Kontakt i zgody”, „Strona końcowa”, flow."""
    data, contact, finish = template.data_page(a), template.contact_page(a), template.finish_page(a)
    names = Names()
    for page in (data, contact, finish):
        for item in iter_fields(page):
            names.reserve(item["techName"])
    if a.applicant.applicant_extra_fields:
        data = _add_applicant_fields(data, a.applicant.applicant_extra_fields, names)
    titles = subject_page_titles(page.title for page in a.subject_pages)
    subject = [tab(title, _subject_sections(page.sections, title, names)) for page, title in zip(a.subject_pages, titles, strict=True)]
    form = {"title": a.title, "tabs": [data, *subject, contact, finish], "flow": {"links": []}}
    _assign_ids(form, uuid.uuid5(ID_NAMESPACE, canonical_json(a)))
    if not ADD_VALIDATORS:
        for page in form["tabs"]:
            for item in iter_fields(page):
                item["validation"] = []
    return form


def canonical_json(a: FormAnalysis) -> str:
    """Treść analizy niezależna od kolejności pól w modelu; z niej pochodzą identyfikatory."""
    return json.dumps(a.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)


def _title_key(title: str) -> str:
    return unicodedata.normalize("NFC", title).casefold()


def subject_page_titles(titles: Iterable[str]) -> list[str]:
    """Jsonata wybiera stronę po tytule, więc tytuły stron muszą być różne.

    Tytuł strony standardowej dostaje dopisek „wniosku”; kolejne powtórzenie – „ (2)”, „ (3)”.
    Porównanie po NFC i bez wielkości liter: „DANE” i „Dane” (albo ń zapisane na dwa sposoby)
    wyglądałyby na ekranie jak ta sama strona.
    """
    standard = {_title_key(title) for title in template.TEMPLATE_PAGES}
    used = set(standard)
    result = []
    for title in titles:
        base = f"{title} wniosku" if _title_key(title) in standard else title
        unique, number = base, 2
        while _title_key(unique) in used:
            unique, number = f"{base} ({number})", number + 1
        used.add(_title_key(unique))
        result.append(unique)
    return result


def _add_applicant_fields(page: dict, fields: list[SubjectField], names: Names) -> dict:
    subject = SubjectSection(title="Dodatkowe dane wnioskodawcy", fields=fields)
    [extra] = _subject_sections([subject], page["title"], names)
    sections = [question["field"] for question in page["questions"]]
    index = next(
        (index for index, item in enumerate(sections) if item["techName"] == template.POWER_OF_ATTORNEY),
        len(sections),
    )
    sections.insert(index, extra)
    return tab(page["title"], sections)


def _subject_sections(source_sections: list[SubjectSection], title: str, names: Names) -> list[dict]:
    """Najpierw nazwy sekcji i pól w przekazanym zakresie, potem warunki SHOW po etykiecie.

    Dla stron przedmiotu zakres to cała strona. Dodatkowe dane wnioskodawcy mają własną sekcję.
    """
    section_names, field_names, located = [], [], {}
    for subject_section in source_sections:
        section_name = names.claim(subject_section.title, "sekcja")
        names_in_section = [names.claim(subject_field.label, "pole") for subject_field in subject_section.fields]
        for subject_field, field_name in zip(subject_section.fields, names_in_section, strict=True):
            located.setdefault(subject_field.label, (section_name, field_name))
        section_names.append(section_name)
        field_names.append(names_in_section)

    sections = []
    for subject_section, section_name, names_in_section in zip(source_sections, section_names, field_names, strict=True):
        fields = []
        for subject_field, field_name in zip(subject_section.fields, names_in_section, strict=True):
            states = []
            if subject_field.show_if is not None:
                source_section, source_field = located[subject_field.show_if.field]
                states = show(answer_is(subject_field.show_if.equals, title, source_section, source_field))
            fields.append(_subject_field(subject_field, field_name, states))
        sections.append(section(section_name, subject_section.title, fields, body=paragraphs(subject_section.description)))
    return sections


def _validator_from_label(label: str) -> str | None:
    """Zwraca walidator typu dla jednej kategorii w etykiecie pojedynczej danej."""
    normalized = unicodedata.normalize("NFC", label).casefold().translate(_POLISH_LETTERS)
    matches = [
        (validator, match)
        for validator, pattern in _LABEL_VALIDATORS.items()
        if (match := pattern.search(normalized))
    ]
    if len(matches) != 1:
        return None

    [(validator, match)] = matches
    remainder = f"{normalized[:match.start()]} {normalized[match.end():]}"
    return None if _COMPOUND_LABEL.search(remainder) else validator


def _subject_field(subject_field: SubjectField, tech_name: str, states: list[dict]) -> dict:
    if subject_field.type is FieldType.TEXT_BLOCK:
        # Jak TEXT_BLOCK we wzorcach: pusty tytuł, cała treść w opisie. Bez REQUIRED, bo nic się nie wpisuje.
        details = paragraphs(subject_field.description)
        heading = html.escape(subject_field.label, quote=False)
        body = f"<p><strong>{heading}</strong></p>{details}" if details else paragraphs(subject_field.label)
        return field("TEXT_BLOCK", tech_name, description=html_document(body), states=states)
    validation = [template.REQUIRED] if subject_field.required else []
    if subject_field.type is FieldType.TEXT_FIELD and (validator := _validator_from_label(subject_field.label)) is not None:
        validation.append(validator)
    return field(
        subject_field.type.value,
        tech_name,
        subject_field.label,
        description=field_description(subject_field.description),
        options=subject_field.options,
        validation=validation,
        states=states,
    )


def _assign_ids(form: dict, namespace: uuid.UUID) -> None:
    """techName są unikalne w formularzu, więc wyznaczają też unikalne id pól i sekcji."""
    for index, page in enumerate(form["tabs"]):
        page["id"] = str(uuid.uuid5(namespace, f"tab/{index}"))
        for item in iter_fields(page):
            item["id"] = str(uuid.uuid5(namespace, f"field/{item['techName']}"))
    form["flow"]["links"] = [
        {"id": str(uuid.uuid5(namespace, f"link/{index}")), "source": source["id"], "target": target["id"]}
        for index, (source, target) in enumerate(pairwise(form["tabs"]))
    ]
