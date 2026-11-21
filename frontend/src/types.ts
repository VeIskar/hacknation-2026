// Format COI z SPEC.md "Field contract" i SZABLONY_SEKCJI.md rozdz. 0.
export interface CoiOption {
  id: string
  name: string
  techName?: string
}

export interface CoiState {
  type: string
  query: string
}

export interface CoiField {
  id: string
  type: string
  techName: string
  title: string
  description: string
  options: CoiOption[]
  // Wzorce COI mają też pusty obiekt zamiast tablicy.
  validation: string[] | Record<string, never>
  readOnly: boolean
  repeatingSectionGrid: CoiCell[]
  states: CoiState[]
  questionOrder: number
  tooltipMessage: string
  defaultValue?: string | string[]
  defaultValueType?: string
  dictionaryName?: string
}

export interface CoiCell {
  x: number
  y: number
  rows: number
  cols: number
  field: CoiField
}

export interface CoiTab {
  id: string
  title: string
  type: string
  questions: CoiCell[]
}

export interface CoiForm {
  title: string
  tabs: CoiTab[]
  flow: { links: { id: string; source: string; target: string }[] }
}
