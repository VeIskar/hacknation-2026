import jsonata from 'jsonata'
import type { CoiField, CoiForm } from '../types.ts'
import { withAnswers } from './answers.ts'
import type { Answers } from './answers.ts'

type Expression = ReturnType<typeof jsonata>

const compiled = new Map<string, Expression | null>()

function compile(query: string): Expression | null {
  let expression = compiled.get(query)
  if (expression === undefined) {
    try {
      expression = jsonata(query)
    } catch {
      expression = null
    }
    compiled.set(query, expression)
  }
  return expression
}

// Zapytanie, którego nie da się skompilować albo policzyć, nie chowa pola: urzędnik ma
// zobaczyć pole z wadliwym warunkiem, a nie formularz bez niego.
async function holds(query: string, data: CoiForm): Promise<boolean> {
  const expression = compile(query)
  if (!expression) return true
  try {
    return Boolean(await expression.evaluate(data))
  } catch {
    return true
  }
}

async function isShown(field: CoiField, data: CoiForm): Promise<boolean> {
  for (const state of field.states) {
    if (state.type === 'SHOW' && !(await holds(state.query, data))) return false
  }
  return true
}

async function hiddenFor(form: CoiForm, data: CoiForm): Promise<Set<string>> {
  const hidden = new Set<string>()
  for (const tab of form.tabs) {
    for (const { field: section } of tab.questions) {
      const sectionHidden = !(await isShown(section, data))
      if (sectionHidden) hidden.add(section.id)
      for (const { field } of section.repeatingSectionGrid) {
        if (sectionHidden || !(await isShown(field, data))) hidden.add(field.id)
      }
    }
  }
  return hidden
}

// Warunki zależne od siebie w kółko nie mają stanu ustalonego. Generator takich nie wypuszcza,
// ale plik może przyjść skądinąd, więc liczba obiegów jest ograniczona.
const MAX_ROUNDS = 8

/**
 * `id` sekcji i pól, których nie widać: z niespełnionym warunkiem SHOW albo w ukrytej sekcji.
 * Odpowiedź ukrytego pola nie steruje innymi warunkami: mieszkaniec jej nie widzi i nie może
 * jej zmienić. Dlatego liczymy w obiegach, aż zbiór przestanie się zmieniać.
 */
export async function hiddenIds(form: CoiForm, answers: Answers): Promise<Set<string>> {
  let hidden = new Set<string>()
  for (let round = 0; round < MAX_ROUNDS; round++) {
    const next = await hiddenFor(form, withAnswers(form, answers, hidden))
    const settled = next.size === hidden.size && [...next].every((id) => hidden.has(id))
    hidden = next
    if (settled) break
  }
  return hidden
}
