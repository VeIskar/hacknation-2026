import { Preview } from '../preview/Preview.tsx'
import type { SelectHow } from '../preview/Preview.tsx'
import type { SourceMatch } from '../sourceMatches.ts'
import type { CoiForm } from '../types.ts'

interface Props {
  /** Formularz po `normalizeForm`. */
  form: CoiForm
  selectedId: string | null
  onSelect: (id: string | null, how: SelectHow) => void
  sources?: ReadonlyMap<string, SourceMatch>
  focusSource: SourceMatch | null
  page: number
  onPage: (page: number) => void
  onHidden: (hidden: ReadonlySet<string>) => void
}

/** Środek ekranu wyniku: eUsługa na własnej kartce, tak jak zobaczy ją mieszkaniec. */
export function ResultPanel({ form, selectedId, onSelect, sources, focusSource, page, onPage, onHidden }: Props) {
  return (
    <section className="obywatel" aria-labelledby="obywatel-tytul">
      <h2 className="obywatel-tytul" id="obywatel-tytul">
        Tak zobaczy to obywatel
      </h2>
      <p className="obywatel-uwaga">Dane z rejestru i słowniki w podglądzie są przykładowe.</p>
      <div className="rama">
        <Preview form={form} selectedId={selectedId} onSelect={onSelect} sources={sources} focusSource={focusSource} page={page} onPage={onPage} onHidden={onHidden} />
      </div>
    </section>
  )
}
