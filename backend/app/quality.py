"""Sprawdza przesłanki w formularzu i reguły jakości wyjścia COI."""

import re
import unicodedata
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from app.models import (
    ExtractedDocument,
    FormAnalysis,
    SubjectField,
    SubjectPage,
    SubjectSection,
)

COUNTRY_DICTIONARY = "Kraje"
COI_DICTIONARIES = frozenset({
    "Województwo", "Powiat", "Gmina", "Miejscowość", COUNTRY_DICTIONARY, "Numery kierunkowe",
    "TERYT_4G_DOWODOWY", "TERYT_DOWODOWY",
})

_POLISH_LETTERS = str.maketrans("ąćęłńóśźż", "acelnoszz")
_WORD = re.compile(r"[^\W\d_]+")
_COUNTRY_LABEL = re.compile(r"^(kraj|panstwo)\b|\bobywatelstw")
_SINGLE_COUNTRY_LABEL = re.compile(
    r"^(?:(?:kraj|panstwo)(?:\s*/\s*(?:kraj|panstwo))?|(?:posiadane\s+)?obywatelstwo)\b"
)
_COMPOUND_COUNTRY_LABEL = re.compile(
    r"[,;/]|\b(?:i|oraz)\b|\b(?:lub|albo)\b(?!\s*(?:zamieszkania|zameldowania|pobytu)\b)"
)
_CORRECTION_PREFIX = "Korekta. "
_APPLICANT_LABELS = frozenset({
    "imie", "nazwisko", "imie i nazwisko", "nazwisko i imie", "pesel", "numer pesel",
    "nip", "regon", "krs", "numer krs", "adres zamieszkania", "adres siedziby",
    "adres do korespondencji", "telefon", "numer telefonu", "telefon kontaktowy",
    "e-mail", "adres e-mail", "adres poczty elektronicznej", "nazwa wnioskodawcy",
    "imie i nazwisko wnioskodawcy",
})
_APPLICANT_RULES = {
    "applicant_pesel": ("PESEL wnioskodawcy", r"pesel"),
    "proxy": ("pełnomocnictwo", r"pelnomocn"),
    "representative_proof": ("potwierdzenie reprezentacji", r"krs|rejestr|odpis|pelnomocnictw|reprezent"),
    "correspondence_address": ("adres do korespondencji", r"korespondenc"),
    "person_address": ("adres zamieszkania", r"zamieszk|zameldow|adres"),
    "entity_address": ("adres siedziby", r"siedzib|adres"),
}
_APPLICANT_LIST_RULES = {
    "entity_ids": {
        "NIP": ("NIP", r"\bnip\b"),
        "REGON": ("REGON", r"regon"),
        "KRS": ("KRS", r"\bkrs\b"),
    },
    "contact": {
        "PHONE": ("telefon", r"telefon|\btel\b"),
        "EMAIL": ("e-mail", r"e-?mail|poczt\w*\s+elektron"),
    },
}
_TYPE_VALIDATORS = {
    "PESEL": r"\bpesel\b",
    "NIP": r"\bnip\b",
    "REGON": r"\bregon\b",
    "ZIP_CODE": r"\bkod\s+pocztowy\b",
    "EMAIL": r"\be-?mail\b|\bpoczty\s+elektronicznej\b",
    "SERIAL_NUMBER_ID_CARD": r"\bdowod",
    "EPUAP": r"\bepuap\b",
    "ADE": r"dorecze",
}
_EXPECTED_VALIDATOR = {
    "pesel": "PESEL", "numer pesel": "PESEL", "kod pocztowy": "ZIP_CODE", "adres e-mail": "EMAIL",
}


def normalize_text(text: str) -> str:
    """NFC, casefold i zapis bez polskich znaków."""
    return unicodedata.normalize("NFC", text).casefold().translate(_POLISH_LETTERS)


def is_country_label(label: str) -> bool:
    return _COUNTRY_LABEL.search(normalize_text(label).strip()) is not None


def should_use_country_dictionary(label: str, kind: str) -> bool:
    if kind != "TEXT_FIELD":
        return False
    label = normalize_text(label).strip()
    match = _SINGLE_COUNTRY_LABEL.match(label)
    return match is not None and _COMPOUND_COUNTRY_LABEL.search(label, match.end()) is None


def show_source_labels(items: Iterable[SubjectField | SubjectSection]) -> set[str]:
    return {
        condition.field
        for item in items
        for condition in (item.show_if, *item.show_if_all)
        if condition is not None
    }


def subject_show_source_labels(pages: Iterable[SubjectPage]) -> set[str]:
    return show_source_labels(item for page in pages for section in page.sections for item in (section, *section.fields))


def _prefixes(text: str) -> set[str]:
    return {word[:5] for word in _WORD.findall(text) if len(word) >= 4 and word.isalpha()}


@dataclass(frozen=True)
class GroundingResult:
    analysis: FormAnalysis
    notes: list[str]

    @property
    def correction_count(self) -> int:
        return sum(note.startswith(_CORRECTION_PREFIX) for note in self.notes)


def _ground_applicant(applicant: dict, text: str, corrections: list[str]) -> None:
    for key, (label, pattern) in _APPLICANT_RULES.items():
        if applicant[key] and not re.search(pattern, text):
            applicant[key] = False
            corrections.append(f"Wyłączono decyzję o polu „{label}” z braku przesłanki w tekście.")

    for key, rules in _APPLICANT_LIST_RULES.items():
        supported = []
        for value in applicant[key]:
            label, pattern = rules[value]
            if re.search(pattern, text):
                supported.append(value)
            else:
                corrections.append(f"Usunięto „{label}” z danych wnioskodawcy z braku przesłanki w tekście.")
        applicant[key] = supported

    if applicant["entity_ids_one_of"] and len(applicant["entity_ids"]) < 2:
        applicant["entity_ids_one_of"] = False
        corrections.append("Wyłączono wybór identyfikatora. Zostało mniej niż dwa identyfikatory.")


def _prune_applicant_duplicates(pages: list[dict], sources: set[str]) -> tuple[list[dict], list[str]]:
    retained, removed = [], []
    for page in pages:
        sections = []
        for section in page["sections"]:
            fields = []
            for field in section["fields"]:
                label = field["label"]
                if normalize_text(label) in _APPLICANT_LABELS and label not in sources:
                    removed.append(label)
                else:
                    fields.append(field)
            if fields:
                sections.append({**section, "fields": fields})
        if sections:
            retained.append({**page, "sections": sections})
    return retained, removed


def ground(analysis: FormAnalysis, doc: ExtractedDocument) -> GroundingResult:
    """Stosuje korekty wnioskodawcy i duplikatów, a resztę przesłanek opisuje w notatkach."""
    text = normalize_text(doc.text).strip()
    if len(text) < 200:
        return GroundingResult(analysis, ["za mało tekstu"])

    data = analysis.model_dump(mode="json")
    corrections = []
    _ground_applicant(data["applicant"], text, corrections)
    pages, removed = _prune_applicant_duplicates(data["subject_pages"], subject_show_source_labels(analysis.subject_pages))
    notes = []
    if pages:
        data["subject_pages"] = pages
        corrections.extend(f"Usunięto duplikat danych wnioskodawcy „{label}” z przedmiotu." for label in removed)
    else:
        notes.append("Zachowano przedmiot. Usunięcie duplikatów opróżniłoby wszystkie strony.")

    grounded = FormAnalysis.model_validate(data)
    words = _prefixes(text)
    for page in grounded.subject_pages:
        for section in page.sections:
            for field in section.fields:
                if not any(words & _prefixes(normalize_text(value)) for value in (field.label, *field.options)):
                    notes.append(f"Brak oparcia w tekście dla pola „{field.label}”.")
    return GroundingResult(grounded, [_CORRECTION_PREFIX + change for change in corrections] + notes)


def _objects(value: object) -> Iterator[dict]:
    if isinstance(value, list):
        yield from (item for item in value if isinstance(item, dict))


def _fields(form: dict) -> Iterator[dict]:
    if not isinstance(form, dict):
        return
    for tab in _objects(form.get("tabs")):
        for question in _objects(tab.get("questions")):
            if isinstance(section := question.get("field"), dict):
                yield section
                for entry in _objects(section.get("repeatingSectionGrid")):
                    if isinstance(field := entry.get("field"), dict):
                        yield field


def validator_issues(form: dict) -> list[str]:
    """Wskazuje błędne lub brakujące walidatory COI.

    P1 zezwala na brak walidatora na polach tylko do odczytu (readOnly: true).
    Kontrola błędnie przypisanych walidatorów obejmuje także te pola.
    """
    issues = []
    for field in _fields(form):
        kind = field.get("type")
        title = normalize_text(field["title"]).strip() if isinstance(field.get("title"), str) else ""
        tech_name = field.get("techName")
        name = tech_name or field.get("title")
        foreign = isinstance(tech_name, str) and "zagranica" in tech_name.casefold()
        validation = field["validation"] if isinstance(field.get("validation"), list) else []
        typed = [rule for rule in validation if isinstance(rule, str) and rule in _TYPE_VALIDATORS]

        if len(typed) > 1:
            issues.append(f"Pole {name!r} ma więcej niż jeden walidator typu.")
        if kind in ("SECTION", "TEXT_BLOCK", "INFO_SECTION") and "REQUIRED" in validation:
            issues.append(f"Pole {name!r} typu {kind} nie może mieć REQUIRED.")
        for rule in typed:
            if kind != "TEXT_FIELD":
                issues.append(f"Pole {name!r} może mieć {rule} tylko jako TEXT_FIELD.")
            elif rule == "ZIP_CODE" and foreign:
                issues.append(f"Pole {name!r} zawiera zagranica w techName i nie może mieć ZIP_CODE.")
            elif not re.search(_TYPE_VALIDATORS[rule], title):
                issues.append(f"Pole {name!r} ma walidator {rule} niepasujący do etykiety.")

        expected = _EXPECTED_VALIDATOR.get(title)
        if (
            kind == "TEXT_FIELD" and field.get("readOnly") is not True
            and expected is not None and expected not in validation
            and not (expected == "ZIP_CODE" and foreign)
        ):
            issues.append(f"Pole {name!r} nie ma walidatora {expected}.")
    return issues


def dictionary_issues(form: dict) -> list[str]:
    """Sprawdza słowniki COI i stosuje tę samą regułę kraju co generator."""
    if not isinstance(form, dict):
        return []
    issues = []
    for field in _fields(form):
        dictionary = field.get("dictionaryName")
        name = field.get("techName") or field.get("title")
        if "dictionaryName" in field and (not isinstance(dictionary, str) or dictionary not in COI_DICTIONARIES):
            issues.append(f"Pole {name!r} używa słownika {dictionary!r} spoza listy COI.")
        title = field.get("title")
        if not isinstance(title, str) or dictionary == COUNTRY_DICTIONARY:
            continue
        if should_use_country_dictionary(title, field.get("type", "")):
            issues.append(f"Pole {name!r} powinno używać słownika {COUNTRY_DICTIONARY}.")
    return issues
