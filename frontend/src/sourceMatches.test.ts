import { describe, expect, it } from 'vitest'
import { textPage } from './pdf.ts'
import { makeField, makeForm, makeSection, makeTab } from './preview/testForm.ts'
import { matchSources } from './sourceMatches.ts'
import type { SourceText, SourceTextPage } from './sourceMatches.ts'

function line(text: string): SourceText {
  return { text, rects: [{ left: 0.1, top: 0.3, width: 0.2, height: 0.01 }] }
}

function page(...labels: string[]): SourceTextPage {
  return { lines: labels.map(line), wrapped: [], hasText: labels.length > 0 }
}

function formWith(...titles: string[]) {
  const fields = titles.map((title, index) => makeField({ techName: String(index), title }))
  return makeForm([makeTab('Dane', [makeSection('sekcja', fields, { title: 'Dane sportowca' })])])
}

describe('źródła PDF', () => {
  it('łączy drobne różnice zapisu i liczy pola bez sekcji', () => {
    const pdf = page('2. Dane sportowca', 'Uzasadnienie: ……', 'PESEL * ....', 'Wielkość–świadczenia (opcjonalnie)')
    const result = matchSources(formWith('Uzasadnienie', 'Numer PESEL', 'Wielkosc świadczenia'), [page(), pdf])
    expect(result.fieldCount).toBe(3)
    expect(result.byId.get('id-sekcja')).toMatchObject({ page: 2, number: 1 })
    expect(result.byId.get('id-0')).toMatchObject({ page: 2, number: 2, parentId: 'id-sekcja', rects: pdf.lines[1].rects })
    expect(result.byId.size).toBe(4)
  })

  it('pomija powtórzenie etykiety w PDF, nawet jeśli drugi fragment nie ma współrzędnych', () => {
    const result = matchSources(formWith('Imię', 'Korekta deklaracji'), [
      page('Imię', 'Korekta deklaracji'),
      { ...page(), lines: [{ text: 'Imie', rects: [] }], hasText: true },
    ])
    expect([...result.byId.keys()]).toEqual(['id-1'])
  })

  it('pomija wspólną etykietę dwóch pól i nie bierze fragmentu zdania za etykietę', () => {
    const result = matchSources(formWith('Nazwisko', 'nazwisko:', 'Data', 'Uzasadnienie'), [
      page('Nazwisko', 'Data sporządzenia wniosku', 'Dołącz uzasadnienie', 'Uzasadnienie drugiego wniosku'),
    ])
    expect(result.byId.size).toBe(0)
    expect(result.hasText).toBe(true)
  })

  it('łączy złamany wiersz i zachowuje oba prostokąty', () => {
    const first = line('Inna')
    const second = line('dyscyplina')
    const result = matchSources(formWith('Inna dyscyplina'), [{
      lines: [first, second],
      wrapped: [{ text: 'Inna dyscyplina', rects: [...first.rects, ...second.rects] }],
      hasText: true,
    }])
    expect(result.byId.get('id-0')?.rects).toEqual([...first.rects, ...second.rects])
  })

  it('odrzuca dwa dopasowania próbujące użyć tej samej części tekstu', () => {
    const first = line('Inna')
    const second = line('dyscyplina')
    const result = matchSources(formWith('Inna', 'Inna dyscyplina'), [{
      lines: [first, second],
      wrapped: [{ text: 'Inna dyscyplina', rects: [...first.rects, ...second.rects] }],
      hasText: true,
    }])
    expect(result.byId.size).toBe(0)
  })

  it('nie skleja sąsiednich etykiet przy takim samym wcięciu', () => {
    const viewport = { transform: [1, 0, 0, -1, 0, 800], width: 600, height: 800 }
    const read = (...words: string[]) => textPage(viewport, {
      lang: null,
      styles: { font: { ascent: 0.8, descent: -0.2, vertical: false, fontFamily: 'sans-serif' } },
      items: words.map((str, index) => ({
        str, dir: 'ltr', transform: [12, 0, 0, 12, 36, 560 - index * 14], width: 48,
        height: 12, fontName: 'font', hasEOL: true,
      })),
    })
    expect(matchSources(formWith('Data podpis'), [read('Data', 'Podpis')]).byId.size).toBe(0)
    expect(matchSources(formWith('Inna dyscyplina'), [read('Inna', 'dyscyplina')]).fieldCount).toBe(1)
  })

  it('nie tworzy zakładek dla skanu ani samej etykiety bez prostokąta', () => {
    const form = formWith('Data')
    expect(matchSources(form, [page()])).toEqual({ byId: new Map(), fieldCount: 0, hasText: false })
    expect(matchSources(form, [{ lines: [{ text: 'Data', rects: [] }], wrapped: [], hasText: true }]).fieldCount).toBe(0)
  })
})
