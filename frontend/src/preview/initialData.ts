import { INITIAL_DATA } from '../data/demo.ts'
import type { CoiField } from '../types.ts'

// Źródła danych inicjalnych z materiału COI „Dane inicjalne”. COI każe oznaczyć pole z rejestru
// jako tylko do odczytu. Wzorce COI zostawiają jednak adres i kontakt z MLPZ (dane konta) do
// zmiany, a imię i nazwisko blokują. Podgląd bierze więc `readOnly` z JSON-a, a nie ze źródła.
// Bezwzględny wymóg stawiamy tylko rejestrom PESEL i PESEL_ADDRESS (check.ts).

interface Source {
  /** Rejestr państwowy: pole musi być tylko do odczytu. */
  registry: boolean
  /** „Przykładowe dane …” */
  from: string
  /** „Brak tych danych …” */
  where: string
}

const SOURCES: Record<string, Source> = {
  PESEL: { registry: true, from: 'z rejestru PESEL', where: 'w rejestrze PESEL' },
  PESEL_ADDRESS: { registry: true, from: 'z danych zameldowania', where: 'w danych zameldowania' },
  MLPZ: { registry: false, from: 'z Twojego konta', where: 'na Twoim koncie' },
}

export interface InitialData {
  /** `defaultValue`, np. `PESEL.name`. */
  key: string
  /** Źródło z listy COI albo `undefined` dla nieznanego. */
  source: Source | undefined
  /** Atrybut jest na liście COI dla tego źródła. */
  known: boolean
  /** Przykładowa wartość, pusta przy braku danych w źródle. */
  value: string
}

/** Opis danych inicjalnych pola albo `null`, gdy pole nie jest zasilane z systemu zewnętrznego. */
export function initialData(field: CoiField): InitialData | null {
  if (field.defaultValueType !== 'EXTERNAL_SYSTEM') return null
  const key = typeof field.defaultValue === 'string' ? field.defaultValue : ''
  const known = Object.hasOwn(INITIAL_DATA, key)
  return { key, source: SOURCES[key.split('.')[0]], known, value: known ? INITIAL_DATA[key] : '' }
}

/** Atrybut bez źródła, np. `email` z `MLPZ.email`. Dla pól bez danych inicjalnych pusty. */
export function attributeOf(field: CoiField): string {
  const data = initialData(field)
  return data ? (data.key.split('.')[1] ?? '') : ''
}

/** Podpowiedź pod etykietą: skąd dane, że są przykładowe i czy można je zmienić. */
export function initialHint(field: CoiField): string | null {
  const data = initialData(field)
  if (!data) return field.readOnly ? 'Tego pola nie możesz zmienić.' : null
  if (!data.source || !data.known) return field.readOnly ? 'Tego pola nie możesz zmienić.' : null
  if (!data.value) {
    return field.readOnly ? `Brak tych danych ${data.source.where}. Tego pola nie uzupełnisz.` : `Brak tych danych ${data.source.where}. Uzupełnij pole.`
  }
  return field.readOnly ? `Przykładowe dane ${data.source.from}. Nie możesz ich zmienić.` : `Przykładowe dane ${data.source.from}. Możesz je zmienić.`
}

/** Pole z rejestru PESEL lub PESEL_ADDRESS, które JSON pozwala zmieniać (narusza COI). */
export function editableRegistryField(field: CoiField): boolean {
  return !field.readOnly && initialData(field)?.source?.registry === true
}
