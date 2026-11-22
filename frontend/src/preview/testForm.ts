import type { CoiCell, CoiField, CoiForm, CoiTab } from '../types.ts'

// Budowa małych formularzy do testów, w kształcie SPEC.md "Field contract".

export function makeField(part: Partial<CoiField> & { techName: string }): CoiField {
  return {
    id: `id-${part.techName}`,
    type: 'TEXT_FIELD',
    title: part.techName,
    description: '',
    options: [],
    validation: [],
    readOnly: false,
    repeatingSectionGrid: [],
    states: [],
    questionOrder: 0,
    tooltipMessage: '',
    ...part,
  }
}

function cells(fields: CoiField[]): CoiCell[] {
  return fields.map((field, y) => ({ x: 0, y, rows: 1, cols: 3, field }))
}

export function makeSection(techName: string, fields: CoiField[], part: Partial<CoiField> = {}): CoiField {
  return makeField({ type: 'SECTION', techName, repeatingSectionGrid: cells(fields), ...part })
}

export function makeTab(title: string, sections: CoiField[], type = 'MAIN'): CoiTab {
  return { id: `tab-${title}`, title, type, questions: cells(sections) }
}

export function makeForm(tabs: CoiTab[]): CoiForm {
  return { title: 'Wniosek testowy', tabs, flow: { links: [] } }
}

export function options(...names: string[]) {
  return names.map((name) => ({ id: name, name, techName: name.toLowerCase().replaceAll(' ', '_') }))
}

/** Zapytanie w formacie generatora: opcja zaznaczona w polu wyboru danej sekcji i strony. */
export function chosen(option: string, tab: string, section: string, field: string): string {
  return `("${option}" in tabs['${tab}' in title].questions['${section}' in field.techName].field.repeatingSectionGrid['${field}' in field.techName].field.__userAnswer)`
}
