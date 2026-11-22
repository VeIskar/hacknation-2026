import { formStats, formatElapsed } from '../format.ts'
import { Preview } from '../preview/Preview.tsx'
import type { CoiForm } from '../types.ts'

interface Props {
  form: CoiForm
  json: string
  elapsedMs: number
  jsonShown: boolean
  jsonRegionId: string
}

export function ResultPanel({ form, json, elapsedMs, jsonShown, jsonRegionId }: Props) {
  const stats = formStats(form)
  return (
    <div>
      <h2 className="tytul-wniosku">{form.title}</h2>
      <dl className="karta">
        <div>
          <dt>Strony</dt>
          <dd>{stats.pages}</dd>
        </div>
        <div>
          <dt>Sekcje</dt>
          <dd>{stats.sections}</dd>
        </div>
        <div>
          <dt>Pola</dt>
          <dd>{stats.fields}</dd>
        </div>
        <div>
          <dt>Czas analizy</dt>
          <dd>{formatElapsed(elapsedMs)}</dd>
        </div>
      </dl>
      {/* Zwykły tekst w jednym elemencie: test akceptacyjny szuka w nim "techName": "twoje_dane". */}
      {jsonShown && (
        <pre className="json" id={jsonRegionId} role="region" aria-label="JSON formularza" tabIndex={0}>
          {json}
        </pre>
      )}
      <Preview form={form} />
    </div>
  )
}
