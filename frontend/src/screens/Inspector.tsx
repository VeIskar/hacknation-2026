import { useRef } from 'react'
import type { KeyboardEvent } from 'react'
import { formStats, formatElapsed } from '../format.ts'
import type { CoiForm } from '../types.ts'

export type InspectorTab = 'karta' | 'json'

const TABS: { id: InspectorTab; label: string }[] = [
  { id: 'karta', label: 'Karta' },
  { id: 'json', label: 'JSON' },
]

interface Props {
  form: CoiForm
  json: string
  elapsedMs: number
  tab: InspectorTab
  onTabChange: (tab: InspectorTab) => void
  jsonPanelId: string
}

/** Panel boczny wyniku: liczby z JSON-a i sam JSON. Przewija się w środku, nie spycha formularza. */
export function Inspector({ form, json, elapsedMs, tab, onTabChange, jsonPanelId }: Props) {
  const stats = formStats(form)
  const tabRefs = useRef<Partial<Record<InspectorTab, HTMLButtonElement | null>>>({})
  const numbers = [
    ['Strony', stats.pages],
    ['Sekcje', stats.sections],
    ['Pola', stats.fields],
    ['Warunki pokazywania', stats.conditions],
    ['Pola z kontrolą poprawności', stats.validators],
    ['Pola ze słownikiem', stats.dictionaries],
    ['Pola z danymi z rejestru', stats.initialData],
  ] as const

  function onKeyDown(event: KeyboardEvent) {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
    event.preventDefault()
    const next: InspectorTab = tab === 'karta' ? 'json' : 'karta'
    onTabChange(next)
    tabRefs.current[next]?.focus()
  }

  return (
    <section className="inspektor" aria-label="Szczegóły formularza">
      <div className="zakladki" role="tablist" aria-label="Widok szczegółów" onKeyDown={onKeyDown}>
        {TABS.map(({ id, label }) => (
          <button
            key={id}
            ref={(element) => {
              tabRefs.current[id] = element
            }}
            type="button"
            role="tab"
            id={`zakladka-${id}`}
            className="zakladka"
            aria-selected={tab === id}
            aria-controls={id === 'json' ? jsonPanelId : 'panel-karta'}
            tabIndex={tab === id ? 0 : -1}
            onClick={() => onTabChange(id)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="inspektor-panel" role="tabpanel" id="panel-karta" aria-labelledby="zakladka-karta" hidden={tab !== 'karta'}>
        <dl className="karta">
          {numbers.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
          <div className="karta-szeroki">
            <dt>Czas analizy</dt>
            <dd>{formatElapsed(elapsedMs)}</dd>
          </div>
        </dl>
        <p className="karta-zrodlo">Liczby pochodzą z pliku JSON, nie z modelu.</p>
      </div>
      {/* Zwykły tekst w jednym elemencie: test akceptacyjny szuka w nim "techName": "twoje_dane". */}
      <div className="inspektor-panel inspektor-json" role="tabpanel" id={jsonPanelId} aria-labelledby="zakladka-json" tabIndex={0} hidden={tab !== 'json'}>
        <pre className="json">{json}</pre>
      </div>
    </section>
  )
}
