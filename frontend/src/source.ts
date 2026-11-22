/** Co da się pokazać jako papier: PDF przez pdfjs, obraz natywnie, reszta wcale. */
export type SourceKind = 'pdf' | 'image' | 'other'

export function sourceKind(file: File): SourceKind {
  const name = file.name.toLowerCase()
  if (name.endsWith('.pdf')) return 'pdf'
  if (/\.(jpe?g|jpe|png)$/.test(name)) return 'image'
  return 'other'
}
