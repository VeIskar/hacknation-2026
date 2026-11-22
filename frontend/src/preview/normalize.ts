import type { CoiCell, CoiField, CoiForm, CoiTab } from '../types.ts'

// Podgląd dostaje dowolny poprawny JSON COI, nie tylko wynik naszego generatora. Wzorce COI
// pomijają czasem klucze (wzorzec z folderu 1 ma sekcję bez `states`, a `validation` bywa
// obiektem). Podgląd pracuje więc na kopii z uzupełnionymi brakami. Plik do pobrania zostaje
// bez zmian: to odpowiedź API (App.tsx, `raw`).

function text(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function list<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : []
}

function normalizeField(raw: Partial<CoiField> | undefined, path: string): CoiField {
  const field = raw ?? {}
  return {
    ...field,
    id: text(field.id) || path,
    type: text(field.type) || 'TEXT_FIELD',
    techName: text(field.techName),
    title: text(field.title),
    description: text(field.description),
    options: list<CoiField['options'][number]>(field.options).filter((option) => option && typeof option.name === 'string'),
    validation: Array.isArray(field.validation) ? field.validation.filter((name) => typeof name === 'string') : [],
    readOnly: field.readOnly === true,
    repeatingSectionGrid: list<CoiCell>(field.repeatingSectionGrid).map((cell, i) => normalizeCell(cell, `${path}-${i}`)),
    states: list<CoiField['states'][number]>(field.states).filter((state) => state && typeof state.query === 'string'),
    questionOrder: typeof field.questionOrder === 'number' ? field.questionOrder : 0,
    tooltipMessage: text(field.tooltipMessage),
  }
}

function normalizeCell(raw: Partial<CoiCell> | undefined, path: string): CoiCell {
  const cell = raw ?? {}
  return {
    x: typeof cell.x === 'number' ? cell.x : 0,
    y: typeof cell.y === 'number' ? cell.y : 0,
    rows: typeof cell.rows === 'number' ? cell.rows : 1,
    cols: typeof cell.cols === 'number' ? cell.cols : 3,
    field: normalizeField(cell.field, path),
  }
}

function normalizeTab(raw: Partial<CoiTab>, index: number): CoiTab {
  return {
    ...raw,
    id: text(raw.id) || `strona-${index}`,
    title: text(raw.title),
    type: text(raw.type) || 'MAIN',
    questions: list<CoiCell>(raw.questions).map((cell, i) => normalizeCell(cell, `strona-${index}-${i}`)),
  }
}

/** Kopia formularza z wszystkimi kluczami, których podgląd potrzebuje. Wejścia nie zmienia. */
export function normalizeForm(raw: CoiForm): CoiForm {
  return {
    ...raw,
    title: text(raw.title),
    tabs: list<Partial<CoiTab>>(raw.tabs).map(normalizeTab),
    flow: { links: list<CoiForm['flow']['links'][number]>(raw.flow?.links) },
  }
}
