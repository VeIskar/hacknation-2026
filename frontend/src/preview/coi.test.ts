import { describe, expect, it } from 'vitest'
import { formStats } from '../format.ts'
import type { CoiForm } from '../types.ts'
import { initialAnswers } from './answers.ts'
import { hiddenIds } from './conditions.ts'
import { normalizeForm } from './normalize.ts'
import { pageErrors } from './validators.ts'

// Wzorce COI z folderów 1 i 5 leżą poza gitem (D5). Bez materialy/ glob jest pusty i test pomijany.
// Vite czyta je przy uruchomieniu testu, więc do repozytorium nic nie trafia.
const files = import.meta.glob('../../../materialy/[15]. */*.json', { eager: true, query: '?raw', import: 'default' }) as Record<string, string>
const references = Object.keys(files)

describe.skipIf(references.length === 0)('wzorce COI w podglądzie', () => {
  it.each(references)('%s: liczby, warunki i walidacja bez wyjątku', async (path: string) => {
    const form = normalizeForm(JSON.parse(files[path]) as CoiForm)
    const stats = formStats(form)
    expect(stats.pages).toBeGreaterThanOrEqual(2)
    expect(stats.fields).toBeGreaterThan(0)
    const answers = initialAnswers(form)
    const hidden = await hiddenIds(form, answers)
    // Wzorce nie mają warunków niemożliwych: przy starcie widać co najmniej jedną sekcję na stronę.
    for (const tab of form.tabs) {
      expect(tab.questions.some(({ field }) => !hidden.has(field.id)), tab.title).toBe(true)
      expect(() => pageErrors(tab, answers, hidden)).not.toThrow()
    }
  })
})
