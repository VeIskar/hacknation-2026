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
from dataclasses import dataclass
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
from app.quality import (
    COUNTRY_DICTIONARY,
    normalize_text,
    should_use_country_dictionary,
)

# SZABLONY, rozdz. 5: walidatory to nasze rozszerzenie. False = validation [] wszędzie, jak we wzorcach.
ADD_VALIDATORS = True

# Stała przestrzeń nazw UUID5. Zmiana zmienia identyfikatory we wszystkich generowanych formularzach.
ID_NAMESPACE = uuid.UUID("7319e414-8854-44a5-ae2b-fdac98e7d0b9")

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
    sources: dict[str, _Source] = {}
    subject = [
        tab(title, _subject_sections(page.sections, title, names, sources))
        for page, title in zip(a.subject_pages, titles, strict=True)
    ]
    form = {"title": a.title, "tabs": [data, *subject, contact, finish], "flow": {"links": []}}
    _assign_ids(form, uuid.uuid5(ID_NAMESPACE, canonical_json(a)))
    if not ADD_VALIDATORS:
        for page in form["tabs"]:
            for item in iter_fields(page):
                item["validation"] = []
    return form


def canonical_json(a: FormAnalysis) -> str:
    """Treść analizy niezależna od kolejności pól w modelu; z niej pochodzą identyfikatory."""
    data = a.model_dump(mode="json")
    for page in data["subject_pages"]:
        for section_data in page["sections"]:
            _omit_empty_conditions(section_data)
            if section_data["show_if"] is None:
                del section_data["show_if"]
            for field_data in section_data["fields"]:
                _omit_empty_conditions(field_data)
    for field_data in data["applicant"]["applicant_extra_fields"]:
        _omit_empty_conditions(field_data)
    return json.dumps(data, sort_keys=True, ensure_ascii=False)


def _omit_empty_conditions(item: dict) -> None:
    """Puste pola dodane w P1.4 nie zmieniają wejścia do UUID5."""
    for condition in (item["show_if"], *item["show_if_all"]):
        if condition is not None and not condition["any_of"]:
            del condition["any_of"]
    if not item["show_if_all"]:
        del item["show_if_all"]


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
    title = "Dodatkowe dane wnioskodawcy"
    section_name = names.claim(title, "sekcja")
    field_names = [names.claim(applicant_field.label, "pole") for applicant_field in fields]
    located = {}
    for applicant_field, field_name in zip(fields, field_names, strict=True):
        located.setdefault(applicant_field.label, field_name)

    items = []
    for applicant_field, field_name in zip(fields, field_names, strict=True):
        states = []
        if condition := applicant_field.show_if:
            states = show(answer_is(condition.equals, page["title"], section_name, located[condition.field]))
        items.append(_subject_field(applicant_field, field_name, states))
    extra = section(section_name, title, items)
    sections = [question["field"] for question in page["questions"]]
    index = next(
        (index for index, item in enumerate(sections) if item["techName"] == template.POWER_OF_ATTORNEY),
        len(sections),
    )
    sections.insert(index, extra)
    return tab(page["title"], sections)


@dataclass(frozen=True)
class _Source:
    page: str
    section: str
    field: str
    guards: tuple[str, ...]


def _show_conditions(
    item: SubjectField | SubjectSection, sources: dict[str, _Source],
) -> tuple[str, ...]:
    conditions = ([item.show_if] if item.show_if is not None else []) + item.show_if_all
    direct, inherited = [], []
    for condition in conditions:
        source = sources[condition.field]
        alternatives = [
            answer_is(option, source.page, source.section, source.field)
            for option in (condition.equals, *condition.any_of)
        ]
        direct.append(f"({' or '.join(alternatives)})" if len(alternatives) > 1 else alternatives[0])
        inherited.extend(source.guards)
    return tuple(dict.fromkeys((*direct, *inherited)))


def _subject_sections(
    source_sections: list[SubjectSection], title: str, names: Names, sources: dict[str, _Source],
) -> list[dict]:
    """Źródła z wcześniejszych pól są już dostępne wraz z warunkami ich widoczności."""
    sections = []
    for subject_section in source_sections:
        section_name = names.claim(subject_section.title, "sekcja")
        section_guards = _show_conditions(subject_section, sources)
        fields = []
        for subject_field in subject_section.fields:
            field_name = names.claim(subject_field.label, "pole")
            field_guards = _show_conditions(subject_field, sources)
            fields.append(_subject_field(subject_field, field_name, show(" and ".join(field_guards))))
            sources.setdefault(subject_field.label, _Source(title, section_name, field_name, section_guards + field_guards))
        sections.append(section(
            section_name, subject_section.title, fields,
            body=paragraphs(subject_section.description), states=show(" and ".join(section_guards)),
        ))
    return sections


def _validator_from_label(label: str) -> str | None:
    """Zwraca walidator typu dla jednej kategorii w etykiecie pojedynczej danej."""
    normalized = normalize_text(label)
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
    validation = [template.REQUIRED] if subject_field.required else []
    if should_use_country_dictionary(subject_field.label, subject_field.type.value):
        return field(
            "SELECT", tech_name, subject_field.label,
            description=field_description(subject_field.description),
            validation=validation, states=states, dictionaryName=COUNTRY_DICTIONARY, searchEnabled=True,
        )
    if subject_field.type is FieldType.TEXT_BLOCK:
        # Jak TEXT_BLOCK we wzorcach: pusty tytuł, cała treść w opisie. Bez REQUIRED, bo nic się nie wpisuje.
        details = paragraphs(subject_field.description)
        heading = html.escape(subject_field.label, quote=False)
        body = f"<p><strong>{heading}</strong></p>{details}" if details else paragraphs(subject_field.label)
        return field("TEXT_BLOCK", tech_name, description=html_document(body), states=states)
    if (
        subject_field.type is FieldType.TEXT_FIELD
        and (validator := _validator_from_label(subject_field.label)) is not None
        and (validator != "ZIP_CODE" or "zagranica" not in tech_name)
    ):
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
