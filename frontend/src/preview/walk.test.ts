import { describe, expect, it } from 'vitest'
import { DEMO_ENTITY, DEMO_ID_CARD, DICTIONARIES } from '../data/demo.ts'
import type { CoiField, CoiForm, CoiTab } from '../types.ts'
import { fieldsOf, initialAnswers, isEmptyAnswer, takesAnswer } from './answers.ts'
import type { Answer } from './answers.ts'
import { hiddenIds } from './conditions.ts'
import { normalizeForm } from './normalize.ts'
import { KNOWN_VALIDATORS, pageErrors, validatorNames } from './validators.ts'

// Przejście całego formularza z API tak, jak robi to „Dalej”: poprawne wartości przechodzą,
// błędne i puste blokują, a pola ukryte warunkiem SHOW nie blokują i nie zgłaszają błędów.
// Wyniki prawdziwego API (Eden AI, ../generated-forms-final, poza repozytorium); bez nich test jest pomijany.
const apiResults = import.meta.glob('../../../../generated-forms-final/F*.coi.json', { eager: true, query: '?raw', import: 'default' }) as Record<string, string>
// Walidatory, które generator API wpisuje (backend/app/generator), czytane tylko do porównania.
const generator = import.meta.glob('../../../backend/app/generator/*.py', { eager: true, query: '?raw', import: 'default' }) as Record<string, string>

const VALID: Record<string, string> = {
  PESEL: '44051401359',
  NIP: DEMO_ENTITY.nip,
  REGON: DEMO_ENTITY.regon,
  ZIP_CODE: '00-950',
  EMAIL: 'anna@example.com',
  SERIAL_NUMBER_ID_CARD: DEMO_ID_CARD,
  EPUAP: '/rdos-wroclaw/skrytka',
  ADE: 'AE:PL-12345-67890-ABCDE-12',
}
const INVALID: Record<string, string> = {
  PESEL: '44051401358',
  NIP: '1234563217',
  REGON: '123456784',
  ZIP_CODE: '12345',
  EMAIL: 'anna@',
  SERIAL_NUMBER_ID_CARD: 'ABA300001',
  EPUAP: 'skrytka',
  ADE: 'AE:PL-12345',
}

function formatOf(field: CoiField): string | undefined {
  return validatorNames(field).find((name) => name in VALID)
}

function validAnswer(field: CoiField): Answer {
  const choices = field.dictionaryName ? [...(DICTIONARIES[field.dictionaryName] ?? [])] : field.options.map((option) => option.name)
  switch (field.type) {
    case 'RADIO':
      return choices[0] ?? ''
    case 'SELECT':
    case 'CHECKBOX':
      return choices.slice(0, 1)
    case 'CONSENT_SECTION':
      return (field.consentSectionConfig?.consents ?? []).map((_, i) => String(i))
    case 'DATEPICKER':
      return '2026-01-15'
    case 'NUMBER':
      return '1'
    case 'FILE_UPLOADER':
      return 'zalacznik.pdf'
    default: {
      const format = formatOf(field)
      return format ? VALID[format] : 'Przykładowa odpowiedź'
    }
  }
}

function blank(field: CoiField): Answer {
  return ['SELECT', 'CHECKBOX', 'CONSENT_SECTION'].includes(field.type) ? [] : ''
}

/** Pola strony, które użytkownik wypełnia (bez pól tylko do odczytu). */
function editable(tab: CoiTab): CoiField[] {
  return fieldsOf(tab).filter((field) => takesAnswer(field) && !field.readOnly)
}

interface Walk {
  visibleChecks: Set<string>
  hiddenChecks: Set<string>
}

/** Idzie stronami do strony końcowej. Na każdej sprawdza poprawne, błędne i ukryte wartości. */
async function walk(raw: CoiForm): Promise<Walk> {
  const form = normalizeForm(raw)
  const answers: Record<string, Answer> = { ...initialAnswers(form) }
  const result: Walk = { visibleChecks: new Set(), hiddenChecks: new Set() }
  for (const tab of form.tabs) {
    // Wypełnij widoczne pola. Wybór może odsłonić kolejne sekcje, więc powtarzaj do stanu stałego.
    let hidden = await hiddenIds(form, answers)
    for (let round = 0; round < 10; round++) {
      const empty = editable(tab).filter((field) => !hidden.has(field.id) && isEmptyAnswer(answers[field.id]))
      if (empty.length === 0) break
      for (const field of empty) answers[field.id] = validAnswer(field)
      hidden = await hiddenIds(form, answers)
    }
    expect(pageErrors(tab, answers, hidden), `${tab.title}: poprawne wartości`).toEqual([])

    for (const field of editable(tab)) {
      if (hidden.has(field.id)) continue
      const keep = answers[field.id]
      const format = formatOf(field)
      if (format && typeof keep === 'string') {
        answers[field.id] = INVALID[format]
        const errors = pageErrors(tab, answers, await hiddenIds(form, answers))
        expect(errors.map((error) => error.fieldId), `${field.techName}: ${format}`).toContain(field.id)
        result.visibleChecks.add(format)
      }
      if (validatorNames(field).includes('REQUIRED')) {
        answers[field.id] = blank(field)
        const errors = pageErrors(tab, answers, await hiddenIds(form, answers))
        expect(errors.map((error) => error.fieldId), `${field.techName}: REQUIRED`).toContain(field.id)
        result.visibleChecks.add('REQUIRED')
      }
      answers[field.id] = keep
    }

    // Ukryte pola z walidatorami: puste albo błędne nie blokują „Dalej”.
    const hiddenValidated = editable(tab).filter((field) => hidden.has(field.id) && validatorNames(field).length > 0)
    const saved = hiddenValidated.map((field) => [field.id, answers[field.id]] as const)
    // Dwa przebiegi: błędny format (gdzie jest), potem pusta odpowiedź.
    for (const variant of ['format', 'pusta'] as const) {
      for (const field of hiddenValidated) {
        const format = formatOf(field)
        if (variant === 'format' && format) {
          answers[field.id] = INVALID[format]
          result.hiddenChecks.add(format)
        } else if (variant === 'pusta') {
          answers[field.id] = blank(field)
          if (validatorNames(field).includes('REQUIRED')) result.hiddenChecks.add('REQUIRED')
        }
      }
      const hiddenAfter = await hiddenIds(form, answers)
      expect(hiddenValidated.every((field) => hiddenAfter.has(field.id)), `${tab.title}: odpowiedź ukrytego pola nie odsłania pól`).toBe(true)
      expect(pageErrors(tab, answers, hiddenAfter), `${tab.title}: pola ukryte, ${variant}`).toEqual([])
    }
    for (const [id, value] of saved) answers[id] = value
  }
  return result
}

const pathOf = (name: string) => Object.keys(apiResults).find((path) => path.endsWith(`/${name}.coi.json`))
const paths = Object.keys(apiResults).sort()

describe.skipIf(paths.length === 0)('przejście formularzy z API przez „Dalej”', () => {
  it.each(paths)('%s: poprawne przechodzą, błędne i puste blokują, ukryte nie blokują', async (path: string) => {
    const result = await walk(JSON.parse(apiResults[path]) as CoiForm)
    expect(result.visibleChecks.has('REQUIRED')).toBe(true)
  })

  it.skipIf(!pathOf('F5'))('F5: kod pocztowy i pola wymagane blokują, ukryty adres nie', async () => {
    const result = await walk(JSON.parse(apiResults[pathOf('F5')!]) as CoiForm)
    expect([...result.visibleChecks].sort()).toEqual(['REQUIRED', 'ZIP_CODE'])
    expect([...result.hiddenChecks].sort()).toEqual(['REQUIRED', 'ZIP_CODE'])
  })

  it.skipIf(!pathOf('F9'))('F9: dowód osobisty i ePUAP pod warunkiem SHOW nie blokują, gdy są ukryte', async () => {
    const result = await walk(JSON.parse(apiResults[pathOf('F9')!]) as CoiForm)
    expect(result.visibleChecks.has('REQUIRED')).toBe(true)
    expect(result.visibleChecks.has('ZIP_CODE')).toBe(true)
    expect([...result.hiddenChecks]).toEqual(expect.arrayContaining(['REQUIRED', 'SERIAL_NUMBER_ID_CARD', 'EPUAP']))
  })

  it.skipIf(!pathOf('F9'))('F9: po odsłonięciu dowód osobisty i ePUAP blokują błędną wartość i przepuszczają poprawną', async () => {
    const form = normalizeForm(JSON.parse(apiResults[pathOf('F9')!]) as CoiForm)
    const all = form.tabs.flatMap((tab) => fieldsOf(tab).map((field) => ({ tab, field })))
    const byTech = (techName: string) => {
      const found = all.find(({ field }) => field.techName === techName)
      if (!found) throw new Error(`brak pola ${techName}`)
      return found
    }
    const answers: Record<string, Answer> = { ...initialAnswers(form) }
    answers[byTech('rodzaj_wnioskodawcy').field.id] = 'Wnioskodawca – Klub sportowy'
    answers[byTech('dane_pelnomocnika_klubu_sportowego').field.id] = ['Wypełnij dane pełnomocnika']
    answers[byTech('dane_klubu_sportowego').field.id] = ['Wypełnij dane klubu']
    answers[byTech('korespondencja_z_urzedem_wybierz_preferowany_sposob').field.id] = 'Skrzynka ePUAP'
    for (const [techName, format] of [['seria_i_numer_dowodu_osobistego_pelnomocnika', 'SERIAL_NUMBER_ID_CARD'], ['adres_skrzynki_epuap', 'EPUAP']] as const) {
      const { tab, field } = byTech(techName)
      expect(formatOf(field)).toBe(format)
      const ids = async () => pageErrors(tab, answers, await hiddenIds(form, answers)).map((error) => error.fieldId)
      answers[field.id] = INVALID[format]
      expect(await ids(), `${techName}: błędna`).toContain(field.id)
      answers[field.id] = VALID[format]
      expect(await ids(), `${techName}: poprawna`).not.toContain(field.id)
    }
  })
})

describe.skipIf(Object.keys(generator).length === 0)('generator API i podgląd', () => {
  it('każdy walidator, który wpisuje generator, ma regułę w podglądzie', () => {
    const source = Object.values(generator).join('\n')
    const labels = source.match(/_LABEL_VALIDATORS = \{([^}]*)\}/)?.[1] ?? ''
    const fromLabels = [...labels.matchAll(/"([A-Z_]+)":/g)].map((match) => match[1])
    expect(fromLabels.sort()).toEqual(['ADE', 'EMAIL', 'EPUAP', 'NIP', 'PESEL', 'REGON', 'SERIAL_NUMBER_ID_CARD', 'ZIP_CODE'])
    const literal = [...source.matchAll(/validation=\[[^\]]*\]/g)].flatMap((match) => [...match[0].matchAll(/"([A-Z_]+)"/g)].map((m) => m[1]))
    for (const name of [...fromLabels, ...literal, 'REQUIRED']) expect(KNOWN_VALIDATORS).toContain(name)
  })
})
