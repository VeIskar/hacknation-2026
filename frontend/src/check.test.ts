import { describe, expect, it } from 'vitest'
import { statsSentences, structureProblems, technicalProblems } from './check.ts'
import { makeField, makeForm, makeSection, makeTab } from './preview/testForm.ts'
import type { CoiForm } from './types.ts'

function linked(form: CoiForm): CoiForm {
  const links = form.tabs.slice(1).map((tab, i) => ({ id: `l${i}`, source: form.tabs[i].id, target: tab.id }))
  return { ...form, flow: { links } }
}

const good = linked(
  makeForm([
    makeTab('Dane', [makeSection('dane', [makeField({ techName: 'imie' })])]),
    makeTab('Koniec', [makeSection('koniec', [makeField({ techName: 'tekst', type: 'TEXT_BLOCK' })])], 'FINISH'),
  ]),
)

describe('technicalProblems', () => {
  it('poprawny formularz nie ma problemów', () => {
    expect(technicalProblems(good)).toEqual([])
  })

  it('wykrywa brak strony końcowej i za mało stron', () => {
    const one = linked(makeForm([makeTab('Dane', [makeSection('dane', [])])]))
    expect(technicalProblems(one)).toEqual(['Formularz ma mniej niż 2 strony.', 'Ostatnia strona nie jest stroną końcową.'])
  })

  it('wykrywa pole poza sekcją, zagnieżdżenie i pole na stronie końcowej', () => {
    const nested = makeField({ techName: 'grupa', repeatingSectionGrid: [{ x: 0, y: 0, rows: 1, cols: 3, field: makeField({ techName: 'w_srodku' }) }] })
    const form = linked(
      makeForm([
        makeTab('Dane', [makeField({ techName: 'luzne', title: 'Luźne' }), makeSection('dane', [nested])]),
        makeTab('Koniec', [makeSection('koniec', [makeField({ techName: 'imie_koniec', title: 'Imię' })])], 'FINISH'),
      ]),
    )
    expect(technicalProblems(form)).toEqual([
      'Pole „Luźne” leży poza sekcją.',
      'Pole „grupa” ma zagnieżdżone pola.',
      'Strona końcowa ma pole do wypełnienia: „Imię”.',
    ])
  })

  it('wykrywa powtórzone identyfikatory i stronę, do której nie prowadzi przepływ', () => {
    const copy = structuredClone(good)
    copy.tabs[1].questions[0].field.id = copy.tabs[0].questions[0].field.id
    copy.flow.links = []
    expect(technicalProblems(copy)).toEqual(['1 identyfikator powtarza się.', 'Przepływ nie prowadzi do 1 strony.'])
    copy.flow.links = [{ id: 'x', source: 'tab-Dane', target: 'nie-ma' }]
    expect(technicalProblems(copy)).toContain('Przepływ wskazuje stronę, której nie ma.')
  })
})

describe('statsSentences', () => {
  it('odmienia liczby i mieści się w 15 słowach na zdanie', () => {
    const sentences = statsSentences({ pages: 4, sections: 18, fields: 57, conditions: 31, validators: 22, dictionaries: 6, initialData: 1 })
    expect(sentences).toEqual([
      '4 kroki, 18 sekcji i 57 pól.',
      '31 warunków pokazywania, 22 pola z kontrolą poprawności.',
      '6 pól ze słownikiem, 1 pole z danymi z rejestru.',
    ])
    for (const sentence of sentences) expect(sentence.split(/\s+/).length).toBeLessThanOrEqual(15)
  })
})

describe('structureProblems', () => {
  it('poprawny plik i pominięte states nie są błędem', () => {
    const copy = structuredClone(good) as unknown as { tabs: { questions: { field: Record<string, unknown> }[] }[] }
    delete copy.tabs[0].questions[0].field.states
    expect(structureProblems(good)).toEqual([])
    expect(structureProblems(copy)).toEqual([])
  })

  it('liczy braki, które podgląd uzupełnia na kopii', () => {
    const copy = structuredClone(good) as unknown as { tabs: Record<string, unknown>[] }
    const fields = (copy.tabs[0].questions as { field: Record<string, unknown> }[])[0].field.repeatingSectionGrid as Record<string, unknown>[]
    delete (fields[0].field as Record<string, unknown>).id
    fields.push({ x: 0, y: 1 })
    delete copy.tabs[1].questions
    expect(structureProblems(copy)).toEqual([
      '1 strona nie ma identyfikatora, typu albo listy sekcji.',
      '1 komórka nie ma pola.',
      '1 pole nie ma identyfikatora albo typu.',
    ])
  })
})
