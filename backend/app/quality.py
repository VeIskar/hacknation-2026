"""Sprawdza przesłanki w formularzu i reguły jakości wyjścia COI."""

import re
import unicodedata
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass

from app import lint
from app.models import (
    CHOICE_TYPES,
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
_NON_COUNTRY_OPTIONS = frozenset({"tak", "nie", "inny", "inne"})
_CORRECTION_PREFIX = "Korekta. "
# Etykieta duplikatu -> decyzja, po której szablon pokazuje te dane (None: szablon pokazuje je zawsze).
_APPLICANT_LABELS: dict[str, tuple[str, str | None] | None] = {
    "imie": None, "nazwisko": None, "imie i nazwisko": None, "nazwisko i imie": None,
    "nazwa wnioskodawcy": None, "imie i nazwisko wnioskodawcy": None,
    "pesel": ("applicant_pesel", None), "numer pesel": ("applicant_pesel", None),
    "nip": ("entity_ids", "NIP"), "regon": ("entity_ids", "REGON"),
    "krs": ("entity_ids", "KRS"), "numer krs": ("entity_ids", "KRS"),
    "adres zamieszkania": ("person_address", None), "adres siedziby": ("entity_address", None),
    "adres do korespondencji": ("correspondence_address", None),
    "telefon": ("contact", "PHONE"), "numer telefonu": ("contact", "PHONE"), "telefon kontaktowy": ("contact", "PHONE"),
    "e-mail": ("contact", "EMAIL"), "adres e-mail": ("contact", "EMAIL"),
    "adres poczty elektronicznej": ("contact", "EMAIL"),
}
_DESIGNATION_TITLE = re.compile(r"^\s*zalacznik\b|\b(do|nr)\s+(zarzadzenia|uchwaly|rozporzadzenia)\b")
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


def should_use_country_dictionary(label: str, kind: str, options: Sequence[str], *, is_show_source: bool) -> bool:
    if is_show_source or not is_country_label(label):
        return False
    if kind == "TEXT_FIELD":
        return True
    return kind in ("SELECT", "RADIO") and len(options) >= 5 and not any(
        normalize_text(option).strip() in _NON_COUNTRY_OPTIONS for option in options
    )


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


def _covered_by_template(label: str, applicant: dict) -> bool:
    """Czy szablon danych wnioskodawcy pokaże te dane po decyzjach z groundingu."""
    key = normalize_text(label).strip()
    if key not in _APPLICANT_LABELS:
        return False
    decision = _APPLICANT_LABELS[key]
    if decision is None:
        return True
    name, value = decision
    return bool(applicant[name]) if value is None else value in applicant[name]


def _prune_applicant_duplicates(
    pages: list[dict], sources: set[str], applicant: dict,
) -> tuple[list[dict], list[str], list[str]]:
    """Usuwa tylko duplikaty, które pokaże szablon. Pozostałe zostają, żeby dane z papieru nie zniknęły.

    Pole z warunkiem SHOW (własnym albo sekcji) to dane innej osoby lub ścieżki, np. imię trenera,
    a nie bezwarunkowe dane wnioskodawcy z szablonu.
    """
    retained, removed, kept = [], [], []
    for page in pages:
        sections = []
        for section in page["sections"]:
            fields = []
            section_conditioned = bool(section.get("show_if") or section.get("show_if_all"))
            for field in section["fields"]:
                label = field["label"]
                conditioned = section_conditioned or bool(field.get("show_if") or field.get("show_if_all"))
                if conditioned or label in sources or normalize_text(label).strip() not in _APPLICANT_LABELS:
                    fields.append(field)
                elif _covered_by_template(label, applicant):
                    removed.append(label)
                else:
                    kept.append(label)
                    fields.append(field)
            if fields:
                sections.append({**section, "fields": fields})
        if sections:
            retained.append({**page, "sections": sections})
    return retained, removed, kept


def _ungrounded_choices(analysis: FormAnalysis, words: set[str]) -> list[str]:
    labels = []
    for page in analysis.subject_pages:
        for section in page.sections:
            for field in section.fields:
                if field.type not in CHOICE_TYPES:
                    continue
                # Krótkie słowa (Tak, Nie) nie mają przedrostków do porównania i nie są sygnałem.
                option_words = [_prefixes(normalize_text(option)) for option in field.options]
                if any(option_words) and not any(words & prefixes for prefixes in option_words):
                    labels.append(field.label)
    return labels


def _semantic_notes(analysis: FormAnalysis, words: set[str]) -> list[str]:
    """Sygnały błędów modelu, których walidacja nie łapie. Bez cytowania dokumentu."""
    notes = []
    if _DESIGNATION_TITLE.search(normalize_text(analysis.title)):
        notes.append("Tytuł wygląda na oznaczenie załącznika lub aktu, a nie na nazwę wniosku.")
    notes.extend(f"Żadna opcja pola „{label}” nie występuje w tekście." for label in _ungrounded_choices(analysis, words))
    return notes


def ground(analysis: FormAnalysis, doc: ExtractedDocument) -> GroundingResult:
    """Stosuje korekty wnioskodawcy i duplikatów, a resztę przesłanek opisuje w notatkach."""
    text = normalize_text(doc.text).strip()
    if len(text) < 200:
        return GroundingResult(analysis, ["za mało tekstu"])

    data = analysis.model_dump(mode="json")
    corrections = []
    _ground_applicant(data["applicant"], text, corrections)
    pages, removed, kept = _prune_applicant_duplicates(
        data["subject_pages"], subject_show_source_labels(analysis.subject_pages), data["applicant"],
    )
    notes = [f"Zachowano „{label}” w przedmiocie. Szablon wnioskodawcy nie zbiera tych danych." for label in kept]
    if pages:
        data["subject_pages"] = pages
        corrections.extend(f"Usunięto duplikat danych wnioskodawcy „{label}” z przedmiotu." for label in removed)
    else:
        notes.append("Zachowano przedmiot. Usunięcie duplikatów opróżniłoby wszystkie strony.")

    grounded = FormAnalysis.model_validate(data)
    words = _prefixes(text)
    notes.extend(_semantic_notes(grounded, words))
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


def _coi_show_source_ids(form: dict, fields: Iterable[dict]) -> set[int]:
    index = lint._index(form.get("tabs"))
    sources = set()
    for field in fields:
        for state in _objects(field.get("states")):
            query = state.get("query")
            if state.get("type") != "SHOW" or not isinstance(query, str):
                continue
            for answer in lint._parse_query(query) or ():
                section = index.get(answer.page, {}).get(answer.section)
                if section is not None and (source := section[1].get(answer.field)) is not None:
                    sources.add(id(source))
    return sources


def dictionary_issues(form: dict) -> list[str]:
    """Sprawdza słowniki COI i stosuje tę samą regułę kraju co generator."""
    if not isinstance(form, dict):
        return []
    fields = list(_fields(form))
    show_sources = _coi_show_source_ids(form, fields)
    issues = []
    for field in fields:
        dictionary = field.get("dictionaryName")
        name = field.get("techName") or field.get("title")
        if "dictionaryName" in field and (not isinstance(dictionary, str) or dictionary not in COI_DICTIONARIES):
            issues.append(f"Pole {name!r} używa słownika {dictionary!r} spoza listy COI.")
        title = field.get("title")
        if not isinstance(title, str) or dictionary == COUNTRY_DICTIONARY:
            continue
        options = [
            option["name"] for option in _objects(field.get("options")) if isinstance(option.get("name"), str)
        ]
        if should_use_country_dictionary(title, field.get("type", ""), options, is_show_source=id(field) in show_sources):
            issues.append(f"Pole {name!r} powinno używać słownika {COUNTRY_DICTIONARY}.")
    return issues
