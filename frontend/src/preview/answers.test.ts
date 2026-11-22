import { describe, expect, it } from 'vitest'
import { INITIAL_DATA } from '../data/demo.ts'
import { initialAnswers, withAnswers } from './answers.ts'
import { makeField, makeForm, makeSection, makeTab } from './testForm.ts'

const form = makeForm([
  makeTab('Dane', [
    makeSection('twoje_dane', [
      makeField({ techName: 'pesel', defaultValue: 'MLPZ.pesel', defaultValueType: 'EXTERNAL_SYSTEM' }),
      makeField({ techName: 'nieznane', defaultValue: 'MLPZ.shoeSize', defaultValueType: 'EXTERNAL_SYSTEM' }),
      makeField({ techName: 'urzad', defaultValue: 'Urząd Gminy Ulan-Majorat' }),
      makeField({ techName: 'kraj', type: 'SELECT', defaultValue: ['Polska'] }),
      makeField({ techName: 'wojewodztwo', type: 'SELECT' }),
      makeField({ techName: 'imie' }),
      makeField({ techName: 'opis', type: 'TEXT_BLOCK' }),
    ]),
  ]),
])

describe('initialAnswers', () => {
  const answers = initialAnswers(form)

  it('dane z rejestru bierze z atrapy, a nieznany klucz zostawia pusty', () => {
    expect(answers['id-pesel']).toBe(INITIAL_DATA['MLPZ.pesel'])
    expect(answers['id-nieznane']).toBe('')
  })

  it('zwykłe defaultValue zostaje tekstem, a w polu wyboru tablicą', () => {
    expect(answers['id-urzad']).toBe('Urząd Gminy Ulan-Majorat')
    expect(answers['id-kraj']).toEqual(['Polska'])
    expect(answers['id-wojewodztwo']).toEqual([])
    expect(answers['id-imie']).toBe('')
  })

  it('sekcja i blok tekstu nie mają odpowiedzi', () => {
    expect('id-opis' in answers).toBe(false)
    expect('id-twoje_dane' in answers).toBe(false)
  })
})

describe('withAnswers', () => {
  it('dopisuje __userAnswer tylko niepustym odpowiedziom i nie zmienia formularza z API', () => {
    const copy = withAnswers(form, { 'id-imie': 'Anna', 'id-kraj': ['Polska'], 'id-urzad': '', 'id-wojewodztwo': [] })
    const byName = Object.fromEntries(copy.tabs[0].questions[0].field.repeatingSectionGrid.map(({ field }) => [field.techName, field]))
    expect(byName.imie.__userAnswer).toBe('Anna')
    expect(byName.kraj.__userAnswer).toEqual(['Polska'])
    expect('__userAnswer' in byName.urzad).toBe(false)
    expect('__userAnswer' in byName.wojewodztwo).toBe(false)
    expect(JSON.stringify(form)).not.toContain('__userAnswer')
  })
})
