import { describe, expect, it } from 'vitest'
import { INITIAL_DATA } from '../data/demo.ts'
import { initialAnswers } from './answers.ts'
import { editableRegistryField, initialData, initialHint } from './initialData.ts'
import { makeField, makeForm, makeSection, makeTab } from './testForm.ts'
import { isPesel, isZipCode } from './validators.ts'

// Komplet atrybutów z materiału COI „Dane inicjalne” (16 + 18 + 17).
const COI_ATTRIBUTES = {
  PESEL: 'pesel name surname birthDate citizenship motherName birthPlace motherSurname sex fatherName secondName birthCountry foreignBirthUSC familyName fatherSurname maritalStatus',
  PESEL_ADDRESS: ['temporary', 'permanent']
    .flatMap((kind) => ['Voivodeship', 'District', 'Community', 'Place', 'StreetType', 'Street', 'HouseNumber', 'ApartmentNumber', 'PostalCode'].map((part) => `${kind}Address${part}`))
    .join(' '),
  MLPZ: 'name secondName surname pesel phoneNumber email country voivodeship district community place postCode street building apartment institutionName descriptiveOrganizationName',
}

const external = (defaultValue: string, readOnly: boolean) =>
  makeField({ techName: defaultValue.replace('.', '_'), defaultValue, defaultValueType: 'EXTERNAL_SYSTEM', readOnly })

describe('dane przykładowe', () => {
  it('mają dokładnie atrybuty z listy COI', () => {
    const expected = Object.entries(COI_ATTRIBUTES).flatMap(([source, list]) => list.split(' ').map((name) => `${source}.${name}`))
    expect(expected).toHaveLength(51)
    expect(Object.keys(INITIAL_DATA).sort()).toEqual(expected.sort())
  })

  it('opisują jedną spójną osobę', () => {
    const pesel = INITIAL_DATA['PESEL.pesel']
    expect(isPesel(pesel)).toBe(true)
    expect(INITIAL_DATA['MLPZ.pesel']).toBe(pesel)
    // PESEL: RRMMDD, a parzysta 10. cyfra to kobieta.
    expect(INITIAL_DATA['PESEL.birthDate']).toBe(`19${pesel.slice(0, 2)}-${pesel.slice(2, 4)}-${pesel.slice(4, 6)}`)
    expect(Number(pesel[9]) % 2 === 0 ? 'kobieta' : 'mężczyzna').toBe(INITIAL_DATA['PESEL.sex'])
    expect(INITIAL_DATA['MLPZ.name']).toBe(INITIAL_DATA['PESEL.name'])
    expect(INITIAL_DATA['MLPZ.surname']).toBe(INITIAL_DATA['PESEL.surname'])
    expect(isZipCode(INITIAL_DATA['PESEL_ADDRESS.permanentAddressPostalCode'])).toBe(true)
    expect(INITIAL_DATA['MLPZ.postCode']).toBe(INITIAL_DATA['PESEL_ADDRESS.permanentAddressPostalCode'])
  })
})

describe('readOnly i dane inicjalne', () => {
  it('readOnly pochodzi z JSON-a, nie ze źródła danych', () => {
    expect(initialHint(external('MLPZ.street', false))).toBe('Przykładowe dane z Twojego konta. Możesz je zmienić.')
    expect(initialHint(external('MLPZ.name', true))).toBe('Przykładowe dane z Twojego konta. Nie możesz ich zmienić.')
    expect(initialHint(external('PESEL.name', true))).toBe('Przykładowe dane z rejestru PESEL. Nie możesz ich zmienić.')
    expect(initialHint(external('PESEL_ADDRESS.permanentAddressStreet', true))).toBe('Przykładowe dane z danych zameldowania. Nie możesz ich zmienić.')
  })

  it('brak danych w źródle zostawia pole puste, a readOnly bez możliwości uzupełnienia', () => {
    const empty = external('PESEL_ADDRESS.temporaryAddressStreet', true)
    expect(initialHint(empty)).toBe('Brak tych danych w danych zameldowania. Tego pola nie uzupełnisz.')
    expect(initialHint(external('MLPZ.institutionName', false))).toBe('Brak tych danych na Twoim koncie. Uzupełnij pole.')
    const form = makeForm([makeTab('Dane', [makeSection('dane', [empty, external('PESEL.pesel', true)])])])
    expect(Object.values(initialAnswers(form))).toEqual(['', '85071201244'])
  })

  it('tylko pole z rejestru PESEL do zmiany narusza COI, a MLPZ do zmiany nie', () => {
    expect(editableRegistryField(external('PESEL.name', false))).toBe(true)
    expect(editableRegistryField(external('PESEL_ADDRESS.permanentAddressPlace', false))).toBe(true)
    expect(editableRegistryField(external('PESEL.name', true))).toBe(false)
    expect(editableRegistryField(external('MLPZ.street', false))).toBe(false)
  })

  it('nieznany atrybut nie dostaje atrapy ani podpowiedzi o danych przykładowych', () => {
    const unknown = external('MLPZ.city', false)
    expect(initialData(unknown)).toMatchObject({ known: false, value: '' })
    expect(initialHint(unknown)).toBeNull()
    expect(initialHint(makeField({ techName: 'zwykle', readOnly: true }))).toBe('Tego pola nie możesz zmienić.')
  })
})
