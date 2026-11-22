import type { CoiField, CoiTab } from '../types.ts'
import { isEmptyAnswer, isSection } from './answers.ts'
import type { Answer, Answers } from './answers.ts'

function digits(value: string): number[] | null {
  return /^\d+$/.test(value) ? [...value].map(Number) : null
}

function weightedSum(numbers: number[], weights: number[]): number {
  return weights.reduce((sum, weight, i) => sum + weight * numbers[i], 0)
}

function separatorsRemoved(value: string): string {
  return value.replace(/[\s-]/g, '')
}

export function isPesel(value: string): boolean {
  const d = digits(value)
  if (!d || d.length !== 11) return false
  return (10 - (weightedSum(d, [1, 3, 7, 9, 1, 3, 7, 9, 1, 3]) % 10)) % 10 === d[10]
}

export function isNip(value: string): boolean {
  const d = digits(value)
  if (!d || d.length !== 10) return false
  // Reszta 10 nie ma cyfry kontrolnej, więc taki numer nie istnieje.
  return weightedSum(d, [6, 5, 7, 2, 3, 4, 5, 6, 7]) % 11 === d[9]
}

export function isRegon(value: string): boolean {
  const d = digits(value)
  if (!d || (d.length !== 9 && d.length !== 14)) return false
  const control = (weights: number[]) => (weightedSum(d, weights) % 11) % 10
  if (control([8, 9, 2, 3, 4, 5, 6, 7]) !== d[8]) return false
  return d.length === 9 || control([2, 4, 8, 5, 0, 9, 7, 3, 6, 1, 2, 4, 8]) === d[13]
}

// Seria i numer dowodu osobistego: 3 litery i 6 cyfr. Pierwsza cyfra jest kontrolna, wagi 7, 3, 1.
const ID_CARD_WEIGHTS = [7, 3, 1, 0, 7, 3, 1, 7, 3]

export function isIdCard(value: string): boolean {
  const card = value.toUpperCase()
  if (!/^[A-Z]{3}\d{6}$/.test(card)) return false
  const values = [...card].map((char) => (/\d/.test(char) ? Number(char) : char.charCodeAt(0) - 55))
  return weightedSum(values, ID_CARD_WEIGHTS) % 10 === values[3]
}

// Adres do e-Doręczeń (ADE): AE:PL-XXXXX-XXXXX-YYYYY-ZZ, gdzie X to cyfra, Y litera, ZZ cyfry.
// Instrukcje e-Doręczeń na gov.pl podają wzór, ale nie algorytm sumy ZZ, więc sprawdzamy kształt.
export function isAde(value: string): boolean {
  return /^AE:PL-\d{5}-\d{5}-[A-Z]{5}-\d{2}$/.test(value.toUpperCase())
}

// Elektroniczna Skrzynka Podawcza ePUAP: /identyfikator-podmiotu/skrytka, np. /rdos-wroclaw/skrytka
// albo /PAAtom/SkrytkaESP (adresy w BIP urzędów). Bez spacji i bez innych ukośników.
export function isEpuap(value: string): boolean {
  return /^\/[A-Za-z0-9._-]+\/[A-Za-z0-9._-]+$/.test(value)
}

export function isZipCode(value: string): boolean {
  return /^\d{2}-\d{3}$/.test(value)
}

export function isEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(value)
}

function requiredMessage(field: CoiField): string {
  const name = `„${field.title}”`
  switch (field.type) {
    case 'RADIO':
    case 'SELECT':
      return `Wybierz odpowiedź w polu ${name}`
    case 'CHECKBOX':
      return `Zaznacz co najmniej jedną odpowiedź w polu ${name}`
    case 'FILE_UPLOADER':
      return `Dodaj plik w polu ${name}`
    case 'DATEPICKER':
      return `Wybierz datę w polu ${name}`
    default:
      return `Uzupełnij pole ${name}`
  }
}

// Kolejność jak w `validation`. Każdy komunikat mówi, jak poprawić (DESIGN.md "Forms").
const FORMAT_CHECKS: Record<string, (value: string) => string | null> = {
  PESEL: (value) => {
    if (!/^\d{11}$/.test(value)) return 'Wpisz 11 cyfr numeru PESEL'
    return isPesel(value) ? null : 'Sprawdź numer PESEL, bo jedna z cyfr jest błędna'
  },
  NIP: (value) => {
    const nip = separatorsRemoved(value)
    if (!/^\d{10}$/.test(nip)) return 'Wpisz 10 cyfr numeru NIP'
    return isNip(nip) ? null : 'Sprawdź numer NIP, bo jedna z cyfr jest błędna'
  },
  REGON: (value) => {
    const regon = separatorsRemoved(value)
    if (!/^(\d{9}|\d{14})$/.test(regon)) return 'Wpisz 9 albo 14 cyfr numeru REGON'
    return isRegon(regon) ? null : 'Sprawdź numer REGON, bo jedna z cyfr jest błędna'
  },
  ZIP_CODE: (value) => (isZipCode(value) ? null : 'Wpisz kod pocztowy w formacie 00-000'),
  EMAIL: (value) => (isEmail(value) ? null : 'Wpisz adres e-mail w formacie nazwa@domena.pl'),
  SERIAL_NUMBER_ID_CARD: (value) => {
    const card = value.replace(/\s/g, '')
    if (!/^[A-Za-z]{3}\d{6}$/.test(card)) return 'Wpisz 3 litery i 6 cyfr numeru dowodu osobistego'
    return isIdCard(card) ? null : 'Sprawdź numer dowodu osobistego, bo jeden znak jest błędny'
  },
  EPUAP: (value) => (isEpuap(value) ? null : 'Wpisz adres skrzynki ePUAP w formacie /identyfikator/skrytka'),
  ADE: (value) => (isAde(value.replace(/\s/g, '')) ? null : 'Wpisz adres do e-Doręczeń w formacie AE:PL-12345-67890-ABCDE-12'),
}

/** Dziewięć nazw z Reguł technicznych COI. REQUIRED sprawdza pustą odpowiedź, reszta format. */
export const KNOWN_VALIDATORS: readonly string[] = ['REQUIRED', ...Object.keys(FORMAT_CHECKS)]

export function validatorNames(field: CoiField): string[] {
  return Array.isArray(field.validation) ? field.validation : []
}

export function isRequired(field: CoiField): boolean {
  return validatorNames(field).includes('REQUIRED')
}

/** Indeks pierwszej wymaganej zgody bez zaznaczenia albo -1. */
export function firstMissingConsent(field: CoiField, answer: Answer | undefined): number {
  const checked = Array.isArray(answer) ? answer : []
  const consents = field.consentSectionConfig?.consents ?? []
  return consents.findIndex((consent, i) => consent.required && !checked.includes(String(i)))
}

/** Komunikat pierwszego niespełnionego walidatora albo `null`. Nieznane nazwy pomija, a zgłasza je check.ts. */
export function validateField(field: CoiField, answer: Answer | undefined): string | null {
  if (field.type === 'CONSENT_SECTION') {
    return firstMissingConsent(field, answer) >= 0 ? 'Zaznacz zgodę, bo jest wymagana' : null
  }
  const names = validatorNames(field)
  if (isEmptyAnswer(answer)) return names.includes('REQUIRED') ? requiredMessage(field) : null
  if (typeof answer !== 'string') return null
  for (const name of names) {
    const message = FORMAT_CHECKS[name]?.(answer.trim())
    if (message) return message
  }
  return null
}

export interface FieldError {
  fieldId: string
  sectionTitle: string
  message: string
}

/** Błędy widocznych pól jednej strony, w kolejności pól. Pola readOnly użytkownik nie poprawi. */
export function pageErrors(tab: CoiTab, answers: Answers, hidden: ReadonlySet<string>): FieldError[] {
  const errors: FieldError[] = []
  for (const { field: section } of tab.questions) {
    if (hidden.has(section.id)) continue
    // Pole poza sekcją (Reguły techniczne go nie dopuszczają, ale plik może przyjść skądinąd).
    const fields = isSection(section) ? section.repeatingSectionGrid.map((cell) => cell.field) : [section]
    const sectionTitle = isSection(section) ? section.title : tab.title
    for (const field of fields) {
      if (hidden.has(field.id) || field.readOnly) continue
      const message = validateField(field, answers[field.id])
      if (message) errors.push({ fieldId: field.id, sectionTitle, message })
    }
  }
  return errors
}
