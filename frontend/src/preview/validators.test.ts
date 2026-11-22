import { describe, expect, it } from 'vitest'
import { DEMO_ENTITY, DEMO_ID_CARD, INITIAL_DATA } from '../data/demo.ts'
import { makeField, makeSection, makeTab } from './testForm.ts'
import { fieldFocusId } from './ids.ts'
import {
  KNOWN_VALIDATORS,
  firstMissingConsent,
  isAde,
  isEmail,
  isEpuap,
  isIdCard,
  isNip,
  isPesel,
  isRegon,
  isZipCode,
  pageErrors,
  validateField,
} from './validators.ts'

// Lista walidatorów API (`_VALIDATORS` w backend/app/lint.py), czytana tylko do porównania.
const lint = Object.values(import.meta.glob('../../../backend/app/lint.py', { eager: true, query: '?raw', import: 'default' }) as Record<string, string>)[0] ?? ''

describe('sumy kontrolne', () => {
  it('PESEL: 11 cyfr i zgodna cyfra kontrolna', () => {
    expect(isPesel('85071201244')).toBe(true)
    expect(isPesel('85071201245')).toBe(false)
    expect(isPesel('8507120124')).toBe(false)
    expect(isPesel('850712012440')).toBe(false)
    expect(isPesel('8507120124a')).toBe(false)
  })

  it('NIP: 10 cyfr, reszta 10 nie daje poprawnego numeru', () => {
    expect(isNip('1234563218')).toBe(true)
    expect(isNip('1234563219')).toBe(false)
    expect(isNip('1000000160')).toBe(false)
    expect(isNip('123456321')).toBe(false)
  })

  it('REGON: 9 albo 14 cyfr, reszta 10 daje cyfrę 0', () => {
    expect(isRegon('123456785')).toBe(true)
    expect(isRegon('123456786')).toBe(false)
    expect(isRegon('100000050')).toBe(true)
    expect(isRegon('12345678500002')).toBe(true)
    expect(isRegon('12345678500003')).toBe(false)
    expect(isRegon('12345678600002')).toBe(false)
    expect(isRegon('1234567850')).toBe(false)
  })

  it('dane demo przechodzą własne walidatory', () => {
    expect(isPesel(INITIAL_DATA['MLPZ.pesel'])).toBe(true)
    expect(isZipCode(INITIAL_DATA['MLPZ.postCode'])).toBe(true)
    expect(isEmail(INITIAL_DATA['MLPZ.email'])).toBe(true)
    expect(isNip(DEMO_ENTITY.nip)).toBe(true)
    expect(isRegon(DEMO_ENTITY.regon)).toBe(true)
  })
})

describe('validateField', () => {
  const zip = makeField({ techName: 'kod', title: 'Kod pocztowy', validation: ['REQUIRED', 'ZIP_CODE'] })

  it('ZIP_CODE mówi, jak poprawić', () => {
    expect(validateField(zip, '12345')).toBe('Wpisz kod pocztowy w formacie 00-000')
    expect(validateField(zip, '00-950')).toBeNull()
    expect(validateField(zip, ' 00-950 ')).toBeNull()
  })

  it('REQUIRED nie przepuszcza pustej wartości ani samych spacji', () => {
    expect(validateField(zip, '')).toBe('Uzupełnij pole „Kod pocztowy”')
    expect(validateField(zip, '   ')).toBe('Uzupełnij pole „Kod pocztowy”')
    expect(validateField(zip, undefined)).toBe('Uzupełnij pole „Kod pocztowy”')
  })

  it('komunikat REQUIRED zależy od typu pola', () => {
    const radio = makeField({ techName: 'r', title: 'W czyim imieniu', type: 'RADIO', validation: ['REQUIRED'] })
    const file = makeField({ techName: 'f', title: 'Plik', type: 'FILE_UPLOADER', validation: ['REQUIRED'] })
    const boxes = makeField({ techName: 'c', title: 'Dni', type: 'CHECKBOX', validation: ['REQUIRED'] })
    expect(validateField(radio, '')).toBe('Wybierz odpowiedź w polu „W czyim imieniu”')
    expect(validateField(file, '')).toBe('Dodaj plik w polu „Plik”')
    expect(validateField(boxes, [])).toBe('Zaznacz co najmniej jedną odpowiedź w polu „Dni”')
    expect(validateField(boxes, ['Poniedziałek'])).toBeNull()
  })

  it('pole bez REQUIRED może być puste, ale wpisana wartość ma mieć format', () => {
    const email = makeField({ techName: 'e', validation: ['EMAIL'] })
    expect(validateField(email, '')).toBeNull()
    expect(validateField(email, 'anna@')).toBe('Wpisz adres e-mail w formacie nazwa@domena.pl')
    expect(validateField(email, 'anna@example.com')).toBeNull()
  })

  it('PESEL, NIP i REGON: osobno długość, osobno cyfra kontrolna', () => {
    const pesel = makeField({ techName: 'p', validation: ['REQUIRED', 'PESEL'] })
    const nip = makeField({ techName: 'n', validation: ['NIP'] })
    const regon = makeField({ techName: 'g', validation: ['REGON'] })
    expect(validateField(pesel, '123')).toBe('Wpisz 11 cyfr numeru PESEL')
    expect(validateField(pesel, '85071201245')).toBe('Sprawdź numer PESEL, bo jedna z cyfr jest błędna')
    expect(validateField(pesel, '85071201244')).toBeNull()
    expect(validateField(nip, '123')).toBe('Wpisz 10 cyfr numeru NIP')
    expect(validateField(nip, '1234563219')).toBe('Sprawdź numer NIP, bo jedna z cyfr jest błędna')
    expect(validateField(nip, '123-456-32-18')).toBeNull()
    expect(validateField(regon, '12345')).toBe('Wpisz 9 albo 14 cyfr numeru REGON')
    expect(validateField(regon, '123456786')).toBe('Sprawdź numer REGON, bo jedna z cyfr jest błędna')
    expect(validateField(regon, '123456785')).toBeNull()
  })

  it('nieznany walidator i pusty obiekt zamiast tablicy niczego nie blokują', () => {
    expect(validateField(makeField({ techName: 'x', validation: ['NIEZNANY'] }), 'cokolwiek')).toBeNull()
    expect(validateField(makeField({ techName: 'y', validation: {} }), '')).toBeNull()
  })

  it('zgoda wymagana musi być zaznaczona, opcjonalna nie', () => {
    const consent = makeField({
      techName: 'zgoda',
      type: 'CONSENT_SECTION',
      consentSectionConfig: { consents: [{ description: 'Wymagana', required: true }, { description: 'Dodatkowa' }] },
    })
    expect(validateField(consent, [])).toBe('Zaznacz zgodę, bo jest wymagana')
    expect(validateField(consent, ['1'])).toBe('Zaznacz zgodę, bo jest wymagana')
    expect(validateField(consent, ['0'])).toBeNull()
  })

  it('przy kilku zgodach błąd i fokus wskazują pierwszą wymaganą bez zaznaczenia', () => {
    const consents = makeField({
      techName: 'zgody',
      type: 'CONSENT_SECTION',
      consentSectionConfig: {
        consents: [{ description: 'Pierwsza', required: true }, { description: 'Dodatkowa' }, { description: 'Trzecia', required: true }],
      },
    })
    expect(firstMissingConsent(consents, ['0'])).toBe(2)
    expect(fieldFocusId(consents, ['0'])).toBe('eu-id-zgody-2')
    expect(firstMissingConsent(consents, ['0', '2'])).toBe(-1)
    expect(fieldFocusId(consents, [])).toBe('eu-id-zgody-0')
    expect(fieldFocusId(makeField({ techName: 'radio', type: 'RADIO' }), '')).toBe('eu-id-radio-0')
    expect(fieldFocusId(makeField({ techName: 'tekst' }), '')).toBe('eu-id-tekst')
  })
})

describe('pageErrors', () => {
  const required = (techName: string, part = {}) => makeField({ techName, title: techName, validation: ['REQUIRED'], ...part })
  const tab = makeTab('Dane', [
    makeSection('pierwsza', [required('a'), required('b'), required('z_rejestru', { readOnly: true })], { title: 'Pierwsza' }),
    makeSection('druga', [required('c')], { title: 'Druga' }),
  ])

  it('zbiera błędy w kolejności pól, z tytułem sekcji', () => {
    expect(pageErrors(tab, { 'id-b': 'jest' }, new Set())).toEqual([
      { fieldId: 'id-a', sectionTitle: 'Pierwsza', message: 'Uzupełnij pole „a”' },
      { fieldId: 'id-c', sectionTitle: 'Druga', message: 'Uzupełnij pole „c”' },
    ])
  })

  it('pomija ukryte pole, pola ukrytej sekcji i pola tylko do odczytu', () => {
    expect(pageErrors(tab, {}, new Set(['id-a', 'id-druga'])).map((error) => error.fieldId)).toEqual(['id-b'])
  })
})

describe('SERIAL_NUMBER_ID_CARD', () => {
  const card = makeField({ techName: 'dowod', validation: ['SERIAL_NUMBER_ID_CARD'] })

  it('sprawdza cyfrę kontrolną dowodu osobistego', () => {
    expect(isIdCard(DEMO_ID_CARD)).toBe(true)
    expect(isIdCard('aba300000')).toBe(true)
    expect(isIdCard('ABA400000')).toBe(false)
    expect(isIdCard('AB1300000')).toBe(false)
  })

  it('mówi, jak poprawić format i błędny znak', () => {
    expect(validateField(card, 'ABA 300000')).toBeNull()
    expect(validateField(card, '123')).toBe('Wpisz 3 litery i 6 cyfr numeru dowodu osobistego')
    expect(validateField(card, 'ABA400000')).toBe('Sprawdź numer dowodu osobistego, bo jeden znak jest błędny')
  })
})

describe('pole poza sekcją', () => {
  it('ma walidację jak pole w sekcji, z tytułem strony zamiast sekcji', () => {
    const loose = makeField({ techName: 'luzne', validation: ['REQUIRED'] })
    const tab = makeTab('Dane', [loose])
    expect(pageErrors(tab, {}, new Set())).toEqual([{ fieldId: loose.id, sectionTitle: 'Dane', message: 'Uzupełnij pole „luzne”' }])
  })
})

describe('EPUAP, ADE i lista z API', () => {
  it('ePUAP: /identyfikator/skrytka jak w BIP urzędów', () => {
    expect(isEpuap('/rdos-wroclaw/skrytka')).toBe(true)
    expect(isEpuap('/PAAtom/SkrytkaESP')).toBe(true)
    expect(isEpuap('/gn9u55ai9v/SkrytkaESP')).toBe(true)
    expect(isEpuap('rdos-wroclaw/skrytka')).toBe(false)
    expect(isEpuap('/rdos wroclaw/skrytka')).toBe(false)
    expect(isEpuap('/rdos-wroclaw/')).toBe(false)
    expect(isEpuap('/a/b/c')).toBe(false)
    expect(isEpuap('anna@example.com')).toBe(false)
  })

  it('ADE: AE:PL-, dwie grupy 5 cyfr, 5 liter i 2 cyfry', () => {
    expect(isAde('AE:PL-12345-67890-ABCDE-12')).toBe(true)
    expect(isAde('ae:pl-12345-67890-abcde-12')).toBe(true)
    expect(isAde('AE:PL-12345-67890-ABCD1-12')).toBe(false)
    expect(isAde('AE:DE-12345-67890-ABCDE-12')).toBe(false)
    expect(isAde('AE:PL-1234-67890-ABCDE-12')).toBe(false)
    expect(isAde('anna@example.com')).toBe(false)
  })

  it('komunikaty mówią, jak poprawić, i przepuszczają spacje w ADE', () => {
    const epuap = makeField({ techName: 'skrzynka', validation: ['EPUAP'] })
    const ade = makeField({ techName: 'ade', validation: ['REQUIRED', 'ADE'] })
    expect(validateField(epuap, 'skrytka')).toBe('Wpisz adres skrzynki ePUAP w formacie /identyfikator/skrytka')
    expect(validateField(epuap, ' /rdos-wroclaw/skrytka ')).toBeNull()
    expect(validateField(epuap, '')).toBeNull()
    expect(validateField(ade, '')).toBe('Uzupełnij pole „ade”')
    expect(validateField(ade, 'AE:PL-12345-67890-ABCDE')).toBe('Wpisz adres do e-Doręczeń w formacie AE:PL-12345-67890-ABCDE-12')
    expect(validateField(ade, 'AE:PL- 12345-67890-ABCDE-12')).toBeNull()
  })

  it.skipIf(!lint)('front zna każdy walidator, który API przepuszcza', () => {
    const block = lint.match(/_VALIDATORS = \{([^}]*)\}/)?.[1] ?? ''
    const fromApi = [...block.matchAll(/"([A-Z_]+)"/g)].map((match) => match[1])
    expect(fromApi).toHaveLength(9)
    expect([...KNOWN_VALIDATORS].sort()).toEqual([...fromApi].sort())
  })
})
