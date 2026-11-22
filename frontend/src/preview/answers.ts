import { INITIAL_DATA } from '../data/demo.ts'
import type { CoiField, CoiForm, CoiTab } from '../types.ts'

/** Tekst dla pól jednej wartości. Tablica dla SELECT, CHECKBOX i zgód (indeksy zaznaczonych). */
export type Answer = string | string[]
/** Odpowiedzi po `field.id`. */
export type Answers = Readonly<Record<string, Answer>>

const LIST_TYPES = new Set(['SELECT', 'CHECKBOX', 'CONSENT_SECTION'])
const NO_ANSWER_TYPES = new Set(['SECTION', 'TEXT_BLOCK', 'INFO_SECTION'])

export function takesAnswer(field: CoiField): boolean {
  return !NO_ANSWER_TYPES.has(field.type)
}

export function isEmptyAnswer(answer: Answer | undefined): boolean {
  if (answer === undefined) return true
  return typeof answer === 'string' ? answer.trim() === '' : answer.length === 0
}

function initialAnswer(field: CoiField): Answer {
  const list = LIST_TYPES.has(field.type)
  const raw = field.defaultValue
  if (raw === undefined) return list ? [] : ''
  if (field.defaultValueType === 'EXTERNAL_SYSTEM') {
    const value = typeof raw === 'string' ? (INITIAL_DATA[raw] ?? '') : ''
    return list ? (value ? [value] : []) : value
  }
  if (list) return Array.isArray(raw) ? [...raw] : raw ? [raw] : []
  return Array.isArray(raw) ? (raw[0] ?? '') : raw
}

export function isSection(field: CoiField): boolean {
  return field.type === 'SECTION'
}

/** Pola strony, które przyjmują odpowiedź albo ją pokazują: pola sekcji i pola poza sekcją. */
export function fieldsOf(tab: CoiTab): CoiField[] {
  return tab.questions.flatMap(({ field }) => (isSection(field) ? field.repeatingSectionGrid.map((cell) => cell.field) : [field]))
}

/** Stan początkowy podglądu: `defaultValue`, a dla danych z rejestru wartość z atrapy. */
export function initialAnswers(form: CoiForm): Answers {
  const answers: Record<string, Answer> = {}
  for (const tab of form.tabs) {
    for (const field of fieldsOf(tab)) {
      if (takesAnswer(field)) answers[field.id] = initialAnswer(field)
    }
  }
  return answers
}

function withAnswer(field: CoiField, answers: Answers, skipped: ReadonlySet<string>): CoiField {
  const copy: CoiField = {
    ...field,
    repeatingSectionGrid: field.repeatingSectionGrid.map((cell) => ({ ...cell, field: withAnswer(cell.field, answers, skipped) })),
  }
  const answer = answers[field.id]
  if (!isEmptyAnswer(answer) && !skipped.has(field.id)) copy.__userAnswer = answer
  return copy
}

/**
 * Kopia formularza z `__userAnswer` przy polach: na niej liczone są warunki SHOW.
 * Pola z `skipped` nie dostają odpowiedzi, choć stan podglądu dalej ją pamięta.
 */
export function withAnswers(form: CoiForm, answers: Answers, skipped: ReadonlySet<string> = new Set()): CoiForm {
  return {
    ...form,
    tabs: form.tabs.map((tab) => ({
      ...tab,
      questions: tab.questions.map((cell) => ({ ...cell, field: withAnswer(cell.field, answers, skipped) })),
    })),
  }
}
