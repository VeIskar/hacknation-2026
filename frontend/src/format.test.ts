import { describe, expect, it } from 'vitest'
import { PAGES, formStats, formatBytes, formatElapsed, jsonFileName, plural } from './format.ts'
import type { CoiCell, CoiField, CoiForm } from './types.ts'

function field(techName: string, extra: Partial<CoiField> = {}): CoiField {
  return {
    id: techName,
    type: 'TEXT_FIELD',
    techName,
    title: techName,
    description: '',
    options: [],
    validation: [],
    readOnly: false,
    repeatingSectionGrid: [],
    states: [],
    questionOrder: 0,
    tooltipMessage: '',
    ...extra,
  }
}

function cell(value: CoiField): CoiCell {
  return { x: 0, y: 0, rows: 1, cols: 3, field: value }
}

const show = [{ type: 'SHOW', query: '("Innej osoby" in tabs.questions.field.__userAnswer)' }]

const form: CoiForm = {
  title: 'Wniosek o stwierdzenie nadpłaty podatku',
  tabs: [
    {
      id: 'dane',
      title: 'Dane',
      type: 'MAIN',
      questions: [
        cell(
          field('twoje_dane', {
            type: 'SECTION',
            repeatingSectionGrid: [
              cell(field('numer_pesel', { defaultValue: 'MLPZ.pesel', defaultValueType: 'EXTERNAL_SYSTEM', readOnly: true })),
              cell(field('kraj', { type: 'SELECT', dictionaryName: 'Kraje', defaultValue: ['Polska'] })),
            ],
          }),
        ),
        cell(
          field('dane_innej_osoby', {
            type: 'SECTION',
            states: show,
            repeatingSectionGrid: [
              cell(field('kod_pocztowy_inna_osoba', { validation: ['REQUIRED', 'ZIP_CODE'], states: show })),
              cell(field('ulica_inna_osoba', { validation: {} })),
            ],
          }),
        ),
      ],
    },
    { id: 'koniec', title: 'Strona końcowa', type: 'FINISH', questions: [] },
  ],
  flow: { links: [{ id: 'l1', source: 'dane', target: 'koniec' }] },
}

describe('formatElapsed', () => {
  it('pokazuje same sekundy poniżej minuty i obcina w dół', () => {
    expect(formatElapsed(0)).toBe('0 s')
    expect(formatElapsed(999)).toBe('0 s')
    expect(formatElapsed(59_999)).toBe('59 s')
  })

  it('od minuty pokazuje minuty i sekundy dwucyfrowo', () => {
    expect(formatElapsed(60_000)).toBe('1 min 00 s')
    expect(formatElapsed(161_400)).toBe('2 min 41 s')
  })

  it('nie pokazuje ujemnego czasu', () => {
    expect(formatElapsed(-500)).toBe('0 s')
  })
})

describe('formatBytes', () => {
  it('dobiera jednostkę i używa przecinka dziesiętnego', () => {
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(131_072)).toBe('128 kB')
    expect(formatBytes(1_572_864)).toBe('1,5 MB')
  })
})

describe('jsonFileName', () => {
  it('robi z tytułu nazwę pliku bez polskich znaków', () => {
    expect(jsonFileName('Wniosek o stwierdzenie nadpłaty podatku')).toBe('wniosek-o-stwierdzenie-nadplaty-podatku.json')
    expect(jsonFileName('Zażółć gęślą jaźń: ŁÓDŹ / 2026')).toBe('zazolc-gesla-jazn-lodz-2026.json')
  })

  it('ma nazwę zastępczą dla tytułu bez liter i cyfr', () => {
    expect(jsonFileName(' ; : ')).toBe('formularz.json')
  })

  it('skraca długi tytuł i nie kończy nazwy myślnikiem', () => {
    const name = jsonFileName(`${'a'.repeat(79)} b ${'c'.repeat(40)}`)
    expect(name).toBe(`${'a'.repeat(79)}.json`)
  })
})

describe('formStats', () => {
  it('liczy strony, sekcje, pola, walidatory, słowniki, dane inicjalne i warunki', () => {
    expect(formStats(form)).toEqual({
      pages: 2,
      sections: 2,
      fields: 4,
      validators: 1,
      dictionaries: 1,
      initialData: 1,
      conditions: 2,
    })
  })
})

describe('plural', () => {
  it('odmienia liczebnik jak w polszczyźnie', () => {
    const cases: [number, string][] = [
      [0, '0 stron'],
      [1, '1 strona'],
      [2, '2 strony'],
      [4, '4 strony'],
      [5, '5 stron'],
      [11, '11 stron'],
      [12, '12 stron'],
      [14, '14 stron'],
      [21, '21 stron'],
      [22, '22 strony'],
      [104, '104 strony'],
      [112, '112 stron'],
    ]
    for (const [count, expected] of cases) expect(plural(count, PAGES)).toBe(expected)
  })
})
