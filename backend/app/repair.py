"""Naprawy odpowiedzi modelu przed walidacją FormAnalysis."""

from collections import defaultdict
from collections.abc import Iterator
from copy import deepcopy
from typing import Any

from pydantic import TypeAdapter, ValidationError

from app.models import CHOICE_TYPES, ShowIf, SubjectPosition, Text

Node = dict[str, Any]
LocatedNode = tuple[SubjectPosition, Node]
Sources = dict[str, list[LocatedNode]]
_TEXT = TypeAdapter(Text)


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return _TEXT.validate_python(value)
    except ValidationError:
        return None


def _label(target: Node) -> str:
    return _text(target.get("label", target.get("title"))) or "bez etykiety"


def _objects(items: object) -> Iterator[tuple[int, Node]]:
    if isinstance(items, list):
        for index, item in enumerate(items):
            if isinstance(item, dict):
                yield index, item


def _subject_targets(data: Node) -> Iterator[LocatedNode]:
    for page_index, page in _objects(data.get("subject_pages")):
        for section_index, section in _objects(page.get("sections")):
            yield (page_index, section_index, -1), section
            for field_index, field in _objects(section.get("fields")):
                yield (page_index, section_index, field_index), field


def _conditions(target: Node) -> Iterator[tuple[str, Node]]:
    condition = target.get("show_if")
    if isinstance(condition, dict):
        yield "show_if", condition
    for index, condition in _objects(target.get("show_if_all")):
        yield f"show_if_all[{index}]", condition


def _deduplicate_conditions(target: Node, notes: list[str]) -> None:
    for key, condition in _conditions(target):
        alternatives = condition.get("any_of")
        equals = _text(condition.get("equals"))
        if not isinstance(alternatives, list) or equals is None or _text(condition.get("field")) is None:
            continue
        normalized = [_text(option) for option in alternatives]
        if None in normalized:
            continue
        seen = {equals}
        kept = []
        for option, value in zip(alternatives, normalized, strict=True):
            if value not in seen:
                kept.append(option)
                seen.add(value)
        if len(kept) != len(alternatives):
            condition["any_of"] = kept
            notes.append(f"N1 {_label(target)!r}, {key}: usunięto powtórzone opcje warunku")


def _repair_identifier_choice(applicant: Node, notes: list[str]) -> None:
    identifiers = applicant.get("entity_ids")
    if (applicant.get("entity_ids_one_of") is True and isinstance(identifiers, list)
            and len(identifiers) < 2 and all(isinstance(item, str) for item in identifiers)):
        applicant["entity_ids_one_of"] = False
        notes.append("N2 wnioskodawca: wyłączono wybór jednego identyfikatora przy mniej niż dwóch identyfikatorach")


def _set_checkbox_option(field: Node, notes: list[str]) -> None:
    if field.get("type") == "CHECKBOX" and field.get("options") in (None, []) and _text(field.get("label")) is not None:
        field["options"] = ["Tak"]
        notes.append(f"N3 {_label(field)!r}: uzupełniono opcję CHECKBOX")


def _source_index(targets: list[LocatedNode]) -> Sources:
    sources: Sources = defaultdict(list)
    for position, node in targets:
        if position[2] >= 0 and (label := _text(node.get("label"))) is not None:
            sources[label].append((position, node))
    return sources


def _parse_condition(value: object) -> ShowIf | None:
    if not isinstance(value, dict):
        return None
    try:
        return ShowIf.model_validate(value)
    except ValidationError:
        return None


def _convert_empty_choices(targets: list[LocatedNode], sources: Sources, notes: list[str]) -> None:
    converted: set[SubjectPosition] = set()
    for position, field in targets:
        if (position[2] >= 0 and field.get("type") in ("RADIO", "SELECT") and field.get("options") in (None, [])
                and _text(field.get("label")) is not None):
            field.update(type="CHECKBOX", options=["Tak"])
            converted.add(position)
            notes.append(f"S1 {_label(field)!r}: zmieniono pole wyboru bez opcji na CHECKBOX")
    if not converted:
        return

    for _, target in targets:
        for key, condition in _conditions(target):
            parsed = _parse_condition(condition)
            matches = sources.get(parsed.field, []) if parsed is not None else []
            if len(matches) != 1 or matches[0][0] not in converted:
                continue
            if condition.get("equals") != "Tak" or condition.get("any_of") != []:
                condition.update(equals="Tak", any_of=[])
                notes.append(f"S1 {_label(target)!r}, {key}: dostosowano warunek do zmienionego pola wyboru")


def _condition_source(
    label: str, position: SubjectPosition, sources: Sources, *, in_subject: bool,
) -> tuple[Node | None, str]:
    candidates = sources.get(label, [])
    if not candidates:
        return None, "brak pola źródłowego"
    if len(candidates) > 1:
        return None, "niejednoznaczna etykieta źródła"
    source_position, source = candidates[0]
    if source_position == position:
        return None, "samoodwołanie"
    if in_subject and position[2] == -1 and source_position[:2] == position[:2]:
        return None, "źródło wewnątrz ukrywanej sekcji"
    if in_subject and source_position >= position:
        return None, "źródło po elemencie zależnym"
    return source, ""


def _repair_condition(
    raw: object, position: SubjectPosition, sources: Sources, *, in_subject: bool,
) -> tuple[bool, str]:
    """Określa, czy zachować warunek. Nie zmienia warunków o niepoprawnej strukturze."""
    condition = _parse_condition(raw)
    if condition is None or not isinstance(raw, dict):
        return True, ""
    source, reason = _condition_source(condition.field, position, sources, in_subject=in_subject)
    if source is None:
        return False, f"usunięto warunek ({reason})"
    kind = source.get("type")
    if not isinstance(kind, str):
        return True, ""
    if kind not in CHOICE_TYPES:
        return False, "usunięto warunek (źródło nie jest polem wyboru)"
    options = source.get("options")
    if not isinstance(options, list):
        return True, ""
    available = {_text(option) for option in options}
    if None in available:
        return True, ""
    if condition.equals not in available:
        return False, "usunięto warunek (opcja equals spoza źródła)"
    if not condition.any_of:
        return True, ""
    if not in_subject:
        del raw["any_of"]
        return True, "usunięto alternatywy z warunku w dodatkowych danych wnioskodawcy"
    kept = [option for option, normalized in zip(raw["any_of"], condition.any_of, strict=True) if normalized in available]
    if len(kept) != len(condition.any_of):
        raw["any_of"] = kept
        return True, "usunięto alternatywy spoza opcji źródła"
    return True, ""


def _prune_conditions(
    targets: list[LocatedNode], sources: Sources, notes: list[str], *, in_subject: bool,
) -> None:
    for position, target in targets:
        prefix = f"S2 {_label(target)!r}"
        keep, description = _repair_condition(target.get("show_if"), position, sources, in_subject=in_subject)
        if not keep:
            del target["show_if"]
        if description:
            notes.append(f"{prefix}, show_if: {description}")

        conditions = target.get("show_if_all")
        if not isinstance(conditions, list) or not conditions:
            continue
        if not in_subject:
            if all(_parse_condition(condition) is not None for condition in conditions):
                del target["show_if_all"]
                notes.append(f"{prefix}: usunięto show_if_all z dodatkowych danych wnioskodawcy")
            continue

        kept = []
        for index, raw in enumerate(conditions):
            keep, description = _repair_condition(raw, position, sources, in_subject=True)
            if keep:
                kept.append(raw)
            if description:
                notes.append(f"{prefix}, show_if_all[{index}]: {description}")
        if len(kept) != len(conditions):
            target["show_if_all"] = kept


def repair_analysis(data: Any, *, last_chance: bool) -> tuple[Any, list[str]]:
    """Zwraca poprawioną kopię analizy i notatki dla wprowadzonych zmian."""
    try:
        repaired = deepcopy(data)
    except RecursionError:
        # Nadużyta głębokość JSON-a pozostaje błędem walidacji.
        return data, []
    if not isinstance(repaired, dict):
        return repaired, []

    applicant = repaired.get("applicant")
    if not isinstance(applicant, dict):
        applicant = {}
    subject = list(_subject_targets(repaired))
    extra = [((0, 0, index), field) for index, field in _objects(applicant.get("applicant_extra_fields"))]
    targets = [*subject, *extra]
    notes: list[str] = []
    for _, target in targets:
        _deduplicate_conditions(target, notes)
    _repair_identifier_choice(applicant, notes)
    for position, field in targets:
        if position[2] >= 0:
            _set_checkbox_option(field, notes)
    if last_chance:
        subject_sources, extra_sources = _source_index(subject), _source_index(extra)
        _convert_empty_choices(subject, subject_sources, notes)
        _convert_empty_choices(extra, extra_sources, notes)
        _prune_conditions(subject, subject_sources, notes, in_subject=True)
        _prune_conditions(extra, extra_sources, notes, in_subject=False)
    return repaired, notes
