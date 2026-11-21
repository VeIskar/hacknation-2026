import type { CoiField, CoiForm } from './types.ts'

/** "42 s" albo "2 min 05 s". Sekundy obcinamy w dół: licznik nie wyprzedza zegara. */
export function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000))
  const minutes = Math.floor(total / 60)
  const seconds = total % 60
  if (minutes === 0) return `${seconds} s`
  return `${minutes} min ${String(seconds).padStart(2, '0')} s`
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} kB`
  return `${(bytes / (1024 * 1024)).toFixed(1).replace('.', ',')} MB`
}

/** Nazwa pobieranego pliku: tytuł formularza bez polskich znaków i znaków niedozwolonych w nazwach. */
export function jsonFileName(title: string): string {
  const slug = title
    .toLowerCase()
    // NFD nie rozkłada "ł", więc zamieniamy je osobno.
    .replaceAll('ł', 'l')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80)
    .replace(/-+$/, '')
  return `${slug || 'formularz'}.json`
}

export interface FormStats {
  pages: number
  sections: number
  fields: number
  validators: number
  dictionaries: number
  initialData: number
  conditions: number
}

function hasValidators(field: CoiField): boolean {
  return Array.isArray(field.validation) && field.validation.length > 0
}

/** Liczby do karty formularza. Wszystkie pochodzą z JSON-a, żadna z modelu. */
export function formStats(form: CoiForm): FormStats {
  const stats: FormStats = {
    pages: form.tabs.length,
    sections: 0,
    fields: 0,
    validators: 0,
    dictionaries: 0,
    initialData: 0,
    conditions: 0,
  }
  for (const tab of form.tabs) {
    for (const { field: section } of tab.questions) {
      stats.sections += 1
      if (section.states.length > 0) stats.conditions += 1
      for (const { field } of section.repeatingSectionGrid) {
        stats.fields += 1
        if (hasValidators(field)) stats.validators += 1
        if (field.dictionaryName) stats.dictionaries += 1
        if (field.defaultValueType === 'EXTERNAL_SYSTEM') stats.initialData += 1
        if (field.states.length > 0) stats.conditions += 1
      }
    }
  }
  return stats
}
