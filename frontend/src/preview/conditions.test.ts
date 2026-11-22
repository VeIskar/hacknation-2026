import { describe, expect, it } from 'vitest'
import { initialAnswers } from './answers.ts'
import { hiddenIds } from './conditions.ts'
import { chosen, makeField, makeForm, makeSection, makeTab, options } from './testForm.ts'

const who = (option: string) => chosen(option, 'Dane', 'podmiot_wniosku', 'w_czyim_imieniu')
const role = (option: string) => chosen(option, 'Dane', 'podmiot_wniosku', 'jako_kto')
const poland = chosen('Polska', 'Dane', 'adres', 'kraj')
const show = (query: string) => [{ type: 'SHOW', query }]

const form = makeForm([
  makeTab('Dane', [
    makeSection('podmiot_wniosku', [
      makeField({ techName: 'w_czyim_imieniu', type: 'RADIO', options: options('Swoim', 'Innej osoby', 'Osoby prawnej') }),
      makeField({ techName: 'jako_kto', type: 'RADIO', options: options('Pełnomocnik', 'Reprezentant'), states: show(who('Osoby prawnej')) }),
    ]),
    makeSection('adres', [
      makeField({ techName: 'kraj', type: 'SELECT', defaultValue: ['Polska'] }),
      makeField({ techName: 'kod_zagranica', states: show(`$not${poland}`) }),
      makeField({ techName: 'kod', states: show(poland) }),
    ]),
    makeSection('dane_innej_osoby', [makeField({ techName: 'imie_inna_osoba' })], { states: show(who('Innej osoby')) }),
    makeSection('pelnomocnictwo', [makeField({ techName: 'plik' })], {
      states: show(`${who('Innej osoby')} or (${who('Osoby prawnej')} and ${role('Pełnomocnik')})`),
    }),
    makeSection('wadliwe', [
      makeField({ techName: 'zly_warunek', states: show('tabs[') }),
      makeField({ techName: 'inny_stan', states: [{ type: 'READ_ONLY', query: 'false' }] }),
    ]),
  ]),
  makeTab('Druga', [makeSection('dalej', [makeField({ techName: 'z_innej_strony', states: show(who('Innej osoby')) })])]),
])

async function hiddenNames(change: Record<string, string | string[]> = {}) {
  const hidden = await hiddenIds(form, { ...initialAnswers(form), ...change })
  return [...hidden].map((id) => id.replace('id-', '')).sort()
}

describe('hiddenIds', () => {
  it('na starcie liczy warunki od defaultValue: kraj „Polska” chowa pola zagraniczne', async () => {
    expect(await hiddenNames()).toEqual([
      'dane_innej_osoby',
      'imie_inna_osoba',
      'jako_kto',
      'kod_zagranica',
      'pelnomocnictwo',
      'plik',
      'z_innej_strony',
    ])
  })

  it('zaznaczenie „Innej osoby” pokazuje sekcje, także na innej stronie', async () => {
    expect(await hiddenNames({ 'id-w_czyim_imieniu': 'Innej osoby' })).toEqual(['jako_kto', 'kod_zagranica'])
  })

  it('$not odwraca warunek po zmianie kraju', async () => {
    const hidden = await hiddenNames({ 'id-kraj': ['Niemcy'] })
    expect(hidden).toContain('kod')
    expect(hidden).not.toContain('kod_zagranica')
  })

  it('„or” i „and” łączą warunki z dwóch pól', async () => {
    const entity = { 'id-w_czyim_imieniu': 'Osoby prawnej' }
    expect(await hiddenNames({ ...entity, 'id-jako_kto': 'Reprezentant' })).toContain('pelnomocnictwo')
    expect(await hiddenNames({ ...entity, 'id-jako_kto': 'Pełnomocnik' })).not.toContain('pelnomocnictwo')
  })

  it('odpowiedź ukrytego pola nie steruje kolejnym warunkiem', async () => {
    const pick = (option: string, field: string) => chosen(option, 'Dane', 'lancuch', field)
    const chain = makeForm([
      makeTab('Dane', [
        makeSection('lancuch', [
          makeField({ techName: 'a', type: 'RADIO', options: options('Tak', 'Nie') }),
          makeField({ techName: 'b', type: 'RADIO', options: options('X', 'Y'), states: show(pick('Tak', 'a')) }),
          makeField({ techName: 'c', states: show(pick('X', 'b')) }),
          makeField({ techName: 'd', states: show(`$not${pick('X', 'b')}`) }),
        ]),
      ]),
    ])
    const hiddenWith = async (a: string) => [...(await hiddenIds(chain, { 'id-a': a, 'id-b': 'X' }))].sort()
    expect(await hiddenWith('Tak')).toEqual(['id-d'])
    expect(await hiddenWith('Nie')).toEqual(['id-b', 'id-c'])
  })

  it('wadliwe zapytanie i stan inny niż SHOW nie chowają pola', async () => {
    const hidden = await hiddenNames()
    expect(hidden).not.toContain('zly_warunek')
    expect(hidden).not.toContain('inny_stan')
  })
})
