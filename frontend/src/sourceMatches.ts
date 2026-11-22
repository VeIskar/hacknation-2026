import { isSection } from './preview/answers.ts'
import type { CoiForm } from './types.ts'

/** Współrzędne rzeczywistego tekstu, jako ułamek szerokości i wysokości strony PDF. */
export interface SourceRect {
  left: number
  top: number
  width: number
  height: number
}

export interface SourceText {
  text: string
  rects: readonly SourceRect[]
}

export interface SourceTextPage {
  lines: readonly SourceText[]
  /** Sąsiednie wiersze o wspólnym wcięciu, które mogą być złamaną etykietą. */
  wrapped: readonly SourceText[]
  hasText: boolean
}

export interface SourceMatch extends SourceText {
  id: string
  title: string
  number: number
  page: number
  tabIndex: number
  parentId?: string
}

export interface SourceMatches {
  byId: ReadonlyMap<string, SourceMatch>
  fieldCount: number
  hasText: boolean
}

function label(text: string): string {
  return text
    .normalize('NFKD')
    .toLowerCase()
    .replace(/\p{M}|\u00ad/gu, '')
    .replaceAll('ł', 'l')
    .replace(/^[\s\p{S}]*\d+(?:\.\d+)*[.)]\s+/u, '')
    .replace(/\(\s*opcjonalnie\s*\)/g, '')
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim()
    .replace(/^numer (pesel|nip|regon)$/, '$1')
}

/** Cała etykieta musi wskazać jeden fragment PDF i jeden element eUsługi. */
export function matchSources(form: CoiForm, pages: readonly SourceTextPage[]): SourceMatches {
  const candidates = new Map<string, { page: number; fragment: SourceText }[]>()
  pages.forEach(({ lines, wrapped }, index) => {
    for (const fragment of [...lines, ...wrapped]) {
      const key = label(fragment.text)
      if (!key) continue
      const found = candidates.get(key) ?? []
      found.push({ page: index + 1, fragment })
      candidates.set(key, found)
    }
  })

  const elements = form.tabs.flatMap((tab, tabIndex) =>
    tab.questions.flatMap(({ field }) => {
      const section = isSection(field)
      const top = { field, section, tabIndex, parentId: undefined }
      return section
        ? [top, ...field.repeatingSectionGrid.map(({ field: child }) => ({ field: child, section: false, tabIndex, parentId: field.id }))]
        : [top]
    }),
  )
  const seen = new Set<string>()
  const repeated = new Set<string>()
  for (const { field } of elements) {
    const key = label(field.title)
    if (seen.has(key)) repeated.add(key)
    seen.add(key)
  }

  const proposed = elements.flatMap(({ field, section, tabIndex, parentId }) => {
    const key = label(field.title)
    const found = candidates.get(key)
    if (!key || repeated.has(key) || found?.length !== 1) return []
    const [{ page, fragment }] = found
    return [{ id: field.id, title: field.title, tabIndex, parentId, section, page, ...fragment }]
  })
  // Dwa dopasowania mogą współdzielić element tekstowy, gdy jedno obejmuje złamany wiersz.
  const used = new Set<SourceRect>()
  const shared = new Set<SourceRect>()
  for (const { rects } of proposed) {
    for (const rect of rects) {
      if (used.has(rect)) shared.add(rect)
      used.add(rect)
    }
  }
  const byId = new Map<string, SourceMatch>()
  let fieldCount = 0
  for (const { section, ...match } of proposed) {
    if (!match.rects.length || match.rects.some((rect) => shared.has(rect))) continue
    byId.set(match.id, { ...match, number: byId.size + 1 })
    if (!section) fieldCount++
  }
  return { byId, fieldCount, hasText: pages.some((page) => page.hasText) }
}
