import { describe, expect, it } from 'vitest'
import { formStats } from '../format.ts'
import type { CoiForm } from '../types.ts'
import { initialAnswers } from './answers.ts'
import { hiddenIds } from './conditions.ts'
import { normalizeForm } from './normalize.ts'
import { pageErrors } from './validators.ts'

// Kształt z wzorca COI z folderu 1: sekcja bez `states`, `validation` jako pusty obiekt.
const sparse = {
  title: 'Wniosek z braków',
  tabs: [
    {
      id: 't1',
      title: 'Dane',
      type: 'MAIN',
      questions: [
        {
          x: 0,
          y: 0,
          rows: 1,
          cols: 3,
          field: {
            id: 's1',
            type: 'SECTION',
            techName: 'sekcja',
            title: 'Sekcja',
            repeatingSectionGrid: [{ x: 0, y: 0, rows: 1, cols: 3, field: { id: 'f1', type: 'TEXT_FIELD', techName: 'pole', title: 'Pole', validation: {} } }],
          },
        },
      ],
    },
    { id: 't2', title: 'Koniec', type: 'FINISH', questions: [] },
  ],
} as unknown as CoiForm

describe('normalizeForm', () => {
  it('uzupełnia brakujące klucze, więc warunki, odpowiedzi i liczby nie wybuchają', async () => {
    expect(() => formStats(sparse)).toThrow()
    const form = normalizeForm(sparse)
    const section = form.tabs[0].questions[0].field
    expect(section.states).toEqual([])
    expect(section.repeatingSectionGrid[0].field.validation).toEqual([])
    expect(form.flow.links).toEqual([])
    expect(formStats(form)).toMatchObject({ pages: 2, sections: 1, fields: 1, conditions: 0 })
    const answers = initialAnswers(form)
    expect(answers).toEqual({ f1: '' })
    expect([...(await hiddenIds(form, answers))]).toEqual([])
    expect(pageErrors(form.tabs[0], answers, new Set())).toEqual([])
  })

  it('nie zmienia wejścia: plik do pobrania zostaje taki, jak przyszedł', () => {
    const before = JSON.stringify(sparse)
    normalizeForm(sparse)
    expect(JSON.stringify(sparse)).toBe(before)
  })

  it('zachowuje klucze spoza listy, np. dictionaryName i defaultValue', () => {
    const withExtra = structuredClone(sparse) as unknown as { tabs: { questions: { field: { repeatingSectionGrid: { field: Record<string, unknown> }[] } }[] }[] }
    withExtra.tabs[0].questions[0].field.repeatingSectionGrid[0].field.dictionaryName = 'Kraje'
    const form = normalizeForm(withExtra as unknown as CoiForm)
    expect(form.tabs[0].questions[0].field.repeatingSectionGrid[0].field.dictionaryName).toBe('Kraje')
  })
})
