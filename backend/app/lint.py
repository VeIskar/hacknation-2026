"""Sprawdza konfigurację COI zgodnie z decyzją P2 w DECISIONS.md."""

import json
import re
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

_SECTIONS = {"SECTION", "REPEATING_SECTION"}
_CHOICES = {"SELECT", "RADIO", "CHECKBOX"}
_INFORMATION = {"TEXT_BLOCK", "INFO_SECTION"}
_FIELDS = _CHOICES | _INFORMATION | {
    "TEXT_FIELD", "NUMBER", "CONSENT_SECTION", "TEXTAREA", "FILE_UPLOADER", "DATEPICKER",
}
_VALIDATORS = {
    "REQUIRED", "EMAIL", "PESEL", "NIP", "REGON", "ZIP_CODE", "EPUAP", "ADE", "SERIAL_NUMBER_ID_CARD",
}

_TYPE_NAMES = {
    (dict,): "obiektu",
    (list,): "tablicy",
    (str,): "tekstu",
    (bool,): "flagi logicznej",
    (int, float): "liczby",
    (str, list): "tekstu lub tablicy",
}
_OPTIONAL_FIELD_TYPES = {
    "defaultValue": (str, list),
    "defaultValueType": (str,),
    "readOnly": (bool,),
    "questionOrder": (int, float),
    "tooltipMessage": (str,),
}
_MISSING = object()

# Obie postacie odwołań z Reguł technicznych (ak. 165 i 168).
_ESCAPE = r'\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4})'
_LITERAL = rf"""(?:"(?:[^"\\]|{_ESCAPE})*"|'(?:[^'\\]|{_ESCAPE})*')"""
_ATOM = re.compile(
    rf"(?P<option>{_LITERAL})\s*in\s+tabs\s*\[\s*(?P<page>{_LITERAL})\s*in\s+title\s*\]"
    rf"\s*\.\s*questions\s*\[\s*(?P<section>{_LITERAL})\s*in\s+field\s*\.\s*techName\s*\]"
    rf"\s*\.\s*field\s*\.\s*(?:"
    rf"repeatingSectionGrid\s*\[\s*(?P<field>{_LITERAL})\s*in\s+field\s*\.\s*techName\s*\]"
    rf"\s*\.\s*field\s*\.\s*__userAnswer\b|"
    rf"__userAnswer\s*\[\s*\$repeatingSectionIndex\s*\]\s*\[\s*(?P<repeated>{_LITERAL})"
    rf"\s*in\s+fieldTechName\s*\]\s*\.\s*answers\b)"
)
_QUERY_TOKEN = re.compile(r"\$not(?=\s*\()|\(|\)|and\b|or\b")
_WHITESPACE = re.compile(r"\s*")
_SINGLE_QUOTED_BODY = re.compile(r'\\.|"')


@dataclass(frozen=True)
class _Answer:
    option: str
    page: str
    section: str
    field: str
    repeating: bool


def _decode(literal: str) -> str | None:
    if literal[0] == "'":
        body = _SINGLE_QUOTED_BODY.sub(lambda match: r'\"' if match[0] == '"' else match[0], literal[1:-1])
        literal = '"' + body + '"'
    try:
        return json.loads(literal, strict=False)
    except ValueError:
        return None


def _parse_query(query: str) -> list[_Answer] | None:
    """Czyta całe wyrażenie. Licznik nawiasów pozwala ominąć rekurencję."""
    answers = []
    position, depth, need_operand = 0, 0, True
    query = query.strip()
    while position < len(query):
        position = _WHITESPACE.match(query, position).end()
        if need_operand and (atom := _ATOM.match(query, position)):
            repeated = atom["repeated"]
            option = _decode(atom["option"])
            page = _decode(atom["page"])
            section = _decode(atom["section"])
            field = _decode(atom["field"] if repeated is None else repeated)
            if option is None or page is None or section is None or field is None:
                return None
            answers.append(_Answer(option, page, section, field, repeated is not None))
            position, need_operand = atom.end(), False
            continue
        token = _QUERY_TOKEN.match(query, position)
        if token is None:
            return None
        symbol = token[0]
        position = token.end()
        if need_operand:
            if symbol == "(":
                depth += 1
            elif symbol != "$not":
                return None
        elif symbol in {"and", "or"}:
            need_operand = True
        elif symbol == ")" and depth > 0:
            depth -= 1
        else:
            return None
    return answers if not need_operand and depth == 0 else None


def _objects(items: object) -> Iterator[dict]:
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                yield item


def _field_objects(grid: object) -> Iterator[dict]:
    for item in _objects(grid):
        if isinstance(field := item.get("field"), dict):
            yield field


def _index(tabs: object) -> dict[str, dict[str, tuple[str, dict[str, dict]]]]:
    """Indeks powstaje przed kontrolą, żeby rozwiązywać odwołania w kolejności stanów."""
    index = {}
    for tab in _objects(tabs):
        if not isinstance(title := tab.get("title"), str):
            continue
        sections = index.setdefault(title, {})
        for section in _field_objects(tab.get("questions")):
            kind, name = section.get("type"), section.get("techName")
            if not isinstance(kind, str) or kind not in _SECTIONS or not isinstance(name, str):
                continue
            fields = {}
            for field in _field_objects(section.get("repeatingSectionGrid")):
                if isinstance(field_name := field.get("techName"), str):
                    fields.setdefault(field_name, field)
            sections.setdefault(name, (kind, fields))
    return index


def _reachable(edges: dict[str, list[str]], start: str) -> set[str]:
    reached = {start}
    pending = [start]
    while pending:
        for target in edges.get(pending.pop(), ()):
            if target not in reached:
                reached.add(target)
                pending.append(target)
    return reached


class _Check:
    def __init__(self, tabs: object):
        self.errors: list[str] = []
        self.ids: set[str] = set()
        self.tech_names: set[str] = set()
        self.index = _index(tabs)

    def error(self, path: str, message: str) -> None:
        self.errors.append(f"{path}: {message}")

    def typed(self, value: Any, path: str, expected: tuple[type, ...]) -> Any:
        if not isinstance(value, expected) or (isinstance(value, bool) and bool not in expected):
            self.error(path, f"oczekiwano {_TYPE_NAMES[expected]}")
            return None
        return value

    def get(
        self, data: dict, path: str, key: str, expected: tuple[type, ...],
        *, required: bool = False, nonempty: bool = False,
    ) -> Any:
        value = data.get(key, _MISSING)
        key_path = f"{path}.{key}" if path else key
        if value is _MISSING:
            if required:
                self.error(key_path, "brak wymaganego klucza")
            return None
        value = self.typed(value, key_path, expected)
        if nonempty and value is not None and not value.strip():
            self.error(key_path, "wymagany niepusty tekst")
            return None
        return value

    def unique(self, value: str | None, path: str, seen: set[str]) -> None:
        if value is not None:
            if value in seen:
                self.error(path, f"powtórzony {value!r}")
            seen.add(value)

    def form(self, form: dict) -> None:
        title = self.get(form, "", "title", (str,), required=True, nonempty=True)
        if title is not None and len(title) > 255:
            self.error("title", "maksymalnie 255 znaków")
        tabs = self.get(form, "", "tabs", (list,), required=True)
        pages = []
        if tabs is not None:
            if len(tabs) < 2:
                self.error("tabs", "wymagane co najmniej dwie strony")
            for index, page in enumerate(tabs):
                path = f"tabs[{index}]"
                if self.typed(page, path, (dict,)) is not None:
                    page_id, kind = self.tab(page, path, last=index == len(tabs) - 1)
                    if page_id is not None:
                        pages.append((index, page_id, kind))
        flow = self.get(form, "", "flow", (dict,), required=True)
        if flow is not None:
            self.flow(flow, pages, len(tabs) - 1 if tabs is not None else -1)

    def tab(self, tab: dict, path: str, *, last: bool) -> tuple[str | None, str | None]:
        page_id = self.get(tab, path, "id", (str,), required=True, nonempty=True)
        self.unique(page_id, f"{path}.id", self.ids)
        self.get(tab, path, "title", (str,), required=True, nonempty=True)
        kind = self.get(tab, path, "type", (str,), required=True)
        expected = "FINISH" if last else "MAIN"
        if kind is not None and kind != expected:
            self.error(f"{path}.type", f"oczekiwano {expected}")
        questions = self.get(tab, path, "questions", (list,), required=True)
        if questions is not None:
            has_fields = False
            for index, question in enumerate(questions):
                item_path = f"{path}.questions[{index}]"
                field = self.grid_item(question, item_path)
                if field is not None and self.field(field, f"{item_path}.field", top=True, finish=kind == "FINISH"):
                    has_fields = True
            if not has_fields:
                self.error(f"{path}.questions", "strona musi zawierać co najmniej jedno pole w sekcji")
        return page_id, kind

    def grid_item(self, item: object, path: str) -> dict | None:
        if self.typed(item, path, (dict,)) is None:
            return None
        for key in ("x", "y", "rows", "cols"):
            self.get(item, path, key, (int, float), required=True)
        return self.get(item, path, "field", (dict,), required=True)

    def field(self, field: dict, path: str, *, top: bool, finish: bool) -> bool:
        ident = self.get(field, path, "id", (str,), required=True, nonempty=True)
        self.unique(ident, f"{path}.id", self.ids)
        kind = self.get(field, path, "type", (str,), required=True, nonempty=True)
        is_section = kind in _SECTIONS
        if kind is not None:
            if top and not is_section:
                self.error(f"{path}.type", "na stronie wymagana jest sekcja")
            elif not top:
                if is_section:
                    self.error(f"{path}.type", "sekcja nie może zawierać sekcji")
                elif kind not in _FIELDS:
                    self.error(f"{path}.type", f"niedozwolony typ pola {kind!r}")
                elif finish and kind not in _INFORMATION:
                    self.error(f"{path}.type", "na stronie FINISH dozwolone są tylko TEXT_BLOCK i INFO_SECTION")

        name = self.get(field, path, "techName", (str,), required=True, nonempty=True)
        self.unique(name, f"{path}.techName", self.tech_names)
        self.get(field, path, "title", (str,), required=is_section, nonempty=is_section)
        is_info = kind == "INFO_SECTION"
        self.get(field, path, "description", (str,), required=is_info, nonempty=is_info)
        for key, expected in _OPTIONAL_FIELD_TYPES.items():
            self.get(field, path, key, expected)

        self.options(field, path, choice=kind in _CHOICES)
        self.validation(field, path, required=not top, informative=kind in _INFORMATION)
        self.consents(field, path, required=kind == "CONSENT_SECTION")
        self.states(field, path, section=is_section)

        grid = self.get(field, path, "repeatingSectionGrid", (list,), required=top and is_section)
        if grid is None:
            return False
        if not top or not is_section:
            if grid:
                self.error(f"{path}.repeatingSectionGrid", "tylko sekcja może zawierać pola")
            return False

        has_fields = False
        for index, item in enumerate(grid):
            item_path = f"{path}.repeatingSectionGrid[{index}]"
            child = self.grid_item(item, item_path)
            if child is not None:
                self.field(child, f"{item_path}.field", top=False, finish=finish)
                child_kind = child.get("type")
                if isinstance(child_kind, str) and child_kind in _FIELDS:
                    has_fields = True
        return has_fields

    def options(self, field: dict, path: str, *, choice: bool) -> None:
        options = self.get(field, path, "options", (list,), required=choice)
        dictionary_choice = choice and options == []
        self.get(field, path, "dictionaryName", (str,), required=dictionary_choice, nonempty=dictionary_choice)
        for index, option in enumerate(options or ()):
            item_path = f"{path}.options[{index}]"
            if self.typed(option, item_path, (dict,)) is not None:
                self.get(option, item_path, "id", (str,), required=choice)
                self.get(option, item_path, "name", (str,), required=choice)
                self.get(option, item_path, "techName", (str,))

    def validation(self, field: dict, path: str, *, required: bool, informative: bool) -> None:
        # Starszy eksport COI zapisuje brak walidatorów także jako pusty obiekt.
        legacy = field.get("validation")
        if isinstance(legacy, dict) and not legacy:
            return
        validators = self.get(field, path, "validation", (list,), required=required)
        if informative and validators:
            self.error(f"{path}.validation", "pole informacyjne nie może mieć walidatorów")
        for index, name in enumerate(validators or ()):
            item_path = f"{path}.validation[{index}]"
            if self.typed(name, item_path, (str,)) is not None and name not in _VALIDATORS:
                self.error(item_path, f"nieznany walidator {name!r}")

    def consents(self, field: dict, path: str, *, required: bool) -> None:
        config = self.get(field, path, "consentSectionConfig", (dict,), required=required)
        if config is None:
            return
        config_path = f"{path}.consentSectionConfig"
        consents = self.get(config, config_path, "consents", (list,), required=required)
        if required and consents == []:
            self.error(f"{config_path}.consents", "wymagana co najmniej jedna zgoda")
        for index, consent in enumerate(consents or ()):
            item_path = f"{config_path}.consents[{index}]"
            if self.typed(consent, item_path, (dict,)) is not None:
                self.get(consent, item_path, "description", (str,), required=True, nonempty=True)
                self.get(consent, item_path, "required", (bool,), required=True)
        self.get(config, config_path, "required", (bool,))
        self.get(config, config_path, "files", (list,))

    def states(self, field: dict, path: str, *, section: bool) -> None:
        states = self.get(field, path, "states", (list,))
        for index, state in enumerate(states or ()):
            item_path = f"{path}.states[{index}]"
            if self.typed(state, item_path, (dict,)) is None:
                continue
            kind = self.get(state, item_path, "type", (str,), required=True)
            if kind is not None:
                if section and kind != "SHOW":
                    self.error(f"{item_path}.type", "stan sekcji musi mieć typ SHOW")
                elif not section and kind not in {"SHOW", "READ_ONLY"}:
                    self.error(f"{item_path}.type", "stan pola musi mieć typ SHOW lub READ_ONLY")
            query = self.get(state, item_path, "query", (str,), required=True, nonempty=True)
            if query is not None:
                self.query(query, f"{item_path}.query")

    def query(self, query: str, path: str) -> None:
        answers = _parse_query(query)
        if answers is None:
            self.error(path, "nierozpoznane zapytanie JSONata")
            return
        for answer in answers:
            if message := self.answer_error(answer):
                self.error(path, message)

    def answer_error(self, answer: _Answer) -> str | None:
        sections = self.index.get(answer.page)
        if sections is None:
            return f"nie ma strony {answer.page!r}"
        section = sections.get(answer.section)
        if section is None:
            return f"nie ma sekcji {answer.section!r} na wskazanej stronie"
        kind, fields = section
        if answer.repeating != (kind == "REPEATING_SECTION"):
            return "ścieżka JSONata nie pasuje do typu wskazanej sekcji"
        field = fields.get(answer.field)
        if field is None:
            return f"nie ma pola {answer.field!r} we wskazanej sekcji"
        field_kind = field.get("type")
        if not isinstance(field_kind, str) or field_kind not in _CHOICES:
            return "wskazane pole nie jest polem wyboru"
        options, dictionary = field.get("options"), field.get("dictionaryName")
        if isinstance(options, list) and not options and isinstance(dictionary, str) and dictionary.strip():
            return None
        for option in _objects(options):
            for key in ("id", "name"):
                value = option.get(key)
                if isinstance(value, str) and value == answer.option:
                    return None
        return f"nie ma opcji {answer.option!r} we wskazanym polu"

    def flow(self, flow: dict, pages: list[tuple[int, str, str | None]], last_index: int) -> None:
        links = self.get(flow, "flow", "links", (list,), required=True)
        if links is None:
            return
        ids = {page_id for _, page_id, _ in pages}
        finishes = {page_id for _, page_id, kind in pages if kind == "FINISH"}
        forward, reverse = defaultdict(list), defaultdict(list)
        for index, link in enumerate(links):
            path = f"flow.links[{index}]"
            if self.typed(link, path, (dict,)) is None:
                continue
            link_id = self.get(link, path, "id", (str,), required=True, nonempty=True)
            self.unique(link_id, f"{path}.id", self.ids)
            source = self.get(link, path, "source", (str,), required=True, nonempty=True)
            if source is not None and source not in ids:
                self.error(f"{path}.source", f"nie ma strony o id {source!r}")
            if source in finishes:
                self.error(f"{path}.source", "link nie może wychodzić ze strony FINISH")
            target = self.get(link, path, "target", (str,), required=True, nonempty=True)
            if target is not None and target not in ids:
                self.error(f"{path}.target", f"nie ma strony o id {target!r}")
            if source in ids and source not in finishes and target in ids:
                forward[source].append(target)
                reverse[target].append(source)

        first_id = next((page_id for index, page_id, _ in pages if index == 0), None)
        finish_id = next((page_id for index, page_id, kind in pages if index == last_index and kind == "FINISH"), None)
        from_first = _reachable(forward, first_id) if first_id is not None else None
        to_finish = _reachable(reverse, finish_id) if finish_id is not None else None
        for index, page_id, kind in pages:
            if from_first is not None and page_id not in from_first:
                self.error(f"tabs[{index}].id", "strona nieosiągalna od pierwszej strony")
            if kind == "MAIN" and to_finish is not None and page_id not in to_finish:
                self.error(f"tabs[{index}].id", "ze strony MAIN nie można dojść do FINISH")


def check(form: dict) -> list[str]:
    """Zwraca błędy ze ścieżkami w kolejności przejścia po formularzu."""
    if not isinstance(form, dict):
        return ["$: oczekiwano obiektu"]
    audit = _Check(form.get("tabs"))
    audit.form(form)
    return audit.errors
