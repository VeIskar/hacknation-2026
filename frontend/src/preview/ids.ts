import type { CoiField } from '../types.ts'
import type { Answer } from './answers.ts'
import { firstMissingConsent } from './validators.ts'

export function fieldDomId(field: CoiField): string {
  return `eu-${field.id}`
}

/**
 * Element, na który trafia fokus z podsumowania błędów. W grupie to pierwsza opcja,
 * a w zgodach pierwsza wymagana zgoda bez zaznaczenia.
 */
export function fieldFocusId(field: CoiField, answer: Answer | undefined): string {
  if (field.type === 'CONSENT_SECTION') return `${fieldDomId(field)}-${Math.max(0, firstMissingConsent(field, answer))}`
  const grouped = field.type === 'RADIO' || field.type === 'CHECKBOX'
  return grouped ? `${fieldDomId(field)}-0` : fieldDomId(field)
}
