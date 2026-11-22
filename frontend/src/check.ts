import { plural } from './format.ts'
import type { FormStats } from './format.ts'
import { fieldsOf, isSection } from './preview/answers.ts'
import { editableRegistryField, initialData } from './preview/initialData.ts'
import { KNOWN_VALIDATORS, validatorNames } from './preview/validators.ts'
import type { CoiForm } from './types.ts'

// Kontrola techniczna w przeglądarce: podzbiór Reguł technicznych COI (DELEGACJA, zadanie P2).
// API sprawdza pełny zestaw linterem przed odpowiedzią 200, więc tu błąd znaczy zwykle plik
// spoza naszego API. Wynik mówi, co sprawdził front, a nie co sprawdził serwer.

const FINISH_TYPES = new Set(['TEXT_BLOCK', 'INFO_SECTION'])

type Loose = Record<string, unknown> | null | undefined

function missing(item: Loose, keys: string[]): boolean {
  return !item || keys.some((key) => item[key] === undefined || item[key] === '')
}

/**
 * Braki w pliku z API, zanim podgląd uzupełni je na kopii (preview/normalize.ts). Bez tego znak
 * „0 błędów” mówiłby o kopii, a nie o pliku do importu. `states` bywa pominięte we wzorcu COI
 * z folderu 1, więc go nie wymagamy.
 */
export function structureProblems(raw: unknown): string[] {
  let tabs = 0
  let cells = 0
  let fields = 0
  const form = raw as { tabs?: unknown }
  for (const tab of Array.isArray(form?.tabs) ? (form.tabs as Loose[]) : []) {
    if (missing(tab, ['id', 'type']) || !Array.isArray(tab?.questions)) tabs += 1
    const walk = (list: unknown) => {
      for (const cell of Array.isArray(list) ? (list as Loose[]) : []) {
        const field = cell?.field as Loose
        if (!field) {
          cells += 1
          continue
        }
        if (missing(field, ['id', 'type'])) fields += 1
        walk(field.repeatingSectionGrid)
      }
    }
    walk(tab?.questions)
  }
  const problems: string[] = []
  if (tabs > 0) problems.push(`${plural(tabs, ['strona nie ma', 'strony nie mają', 'stron nie ma'])} identyfikatora, typu albo listy sekcji.`)
  if (cells > 0) problems.push(`${plural(cells, ['komórka nie ma', 'komórki nie mają', 'komórek nie ma'])} pola.`)
  if (fields > 0) problems.push(`${plural(fields, ['pole nie ma', 'pola nie mają', 'pól nie ma'])} identyfikatora albo typu.`)
  return problems
}

/** Lista problemów po polsku. Pusta lista: formularz przeszedł kontrolę. */
export function technicalProblems(form: CoiForm): string[] {
  const problems: string[] = []
  const tabs = form.tabs
  if (tabs.length < 2) problems.push('Formularz ma mniej niż 2 strony.')
  if (tabs.length > 0 && tabs.at(-1)?.type !== 'FINISH') problems.push('Ostatnia strona nie jest stroną końcową.')

  const ids = new Map<string, number>()
  const count = (id: string) => ids.set(id, (ids.get(id) ?? 0) + 1)
  for (const tab of tabs) {
    count(tab.id)
    for (const { field: section } of tab.questions) {
      count(section.id)
      if (!isSection(section)) problems.push(`Pole „${section.title || section.techName}” leży poza sekcją.`)
      for (const { field } of section.repeatingSectionGrid) {
        count(field.id)
        if (field.repeatingSectionGrid.length > 0) problems.push(`Pole „${field.title || field.techName}” ma zagnieżdżone pola.`)
        if (tab.type === 'FINISH' && !FINISH_TYPES.has(field.type)) {
          problems.push(`Strona końcowa ma pole do wypełnienia: „${field.title || field.techName}”.`)
        }
      }
    }
  }
  for (const field of tabs.flatMap(fieldsOf)) {
    const name = `„${field.title || field.techName}”`
    for (const validator of validatorNames(field)) {
      if (!KNOWN_VALIDATORS.includes(validator)) problems.push(`Pole ${name} ma walidator spoza listy COI: ${validator}.`)
    }
    const initial = initialData(field)
    if (initial && !initial.known) problems.push(`Pole ${name} ma dane inicjalne spoza listy COI: ${initial.key || 'brak źródła'}.`)
    if (editableRegistryField(field)) problems.push(`Pole ${name} ma dane ${initial?.source?.from}, a można je zmienić.`)
  }
  const repeated = [...ids].filter(([, times]) => times > 1).length
  if (repeated > 0) problems.push(`${plural(repeated, ['identyfikator powtarza', 'identyfikatory powtarzają', 'identyfikatorów powtarza'])} się.`)

  // flow: każda strona osiągalna z pierwszej, linki tylko między istniejącymi stronami.
  const tabIds = new Set(tabs.map((tab) => tab.id))
  const links = form.flow.links
  if (links.some((link) => !tabIds.has(link.source) || !tabIds.has(link.target))) {
    problems.push('Przepływ wskazuje stronę, której nie ma.')
  }
  if (tabs.length > 0) {
    const reached = new Set([tabs[0].id])
    for (let grew = true; grew; ) {
      grew = false
      for (const link of links) {
        if (reached.has(link.source) && !reached.has(link.target)) {
          reached.add(link.target)
          grew = true
        }
      }
    }
    const lost = tabs.filter((tab) => !reached.has(tab.id)).length
    if (lost > 0) problems.push(`Przepływ nie prowadzi do ${plural(lost, ['strony', 'stron', 'stron'])}.`)
  }
  return problems
}

/** Zdania z liczbami do nagłówka wyniku, najwyżej 15 słów każde. */
export function statsSentences(stats: FormStats): string[] {
  return [
    `${plural(stats.pages, ['krok', 'kroki', 'kroków'])}, ${plural(stats.sections, ['sekcja', 'sekcje', 'sekcji'])} i ${plural(stats.fields, ['pole', 'pola', 'pól'])}.`,
    `${plural(stats.conditions, ['warunek pokazywania', 'warunki pokazywania', 'warunków pokazywania'])}, ${plural(stats.validators, ['pole z kontrolą poprawności', 'pola z kontrolą poprawności', 'pól z kontrolą poprawności'])}.`,
    `${plural(stats.dictionaries, ['pole ze słownikiem', 'pola ze słownikiem', 'pól ze słownikiem'])}, ${plural(stats.initialData, ['pole z danymi z rejestru', 'pola z danymi z rejestru', 'pól z danymi z rejestru'])}.`,
  ]
}
