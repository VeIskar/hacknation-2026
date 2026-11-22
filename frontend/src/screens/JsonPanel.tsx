import { useMemo } from 'react'
import { jsonTokens } from '../jsonTokens.ts'
import { SECTION_TYPES } from '../preview/answers.ts'
import type { CoiForm } from '../types.ts'

export type JsonMode = 'element' | 'plik'

/** Pozycja elementu w oryginalnym pliku z API. */
export interface JsonSelection {
  tabIndex: number
  cellIndex: number
  childIndex?: number
}

interface Props {
  /** Formularz z API bez normalizacji: panel pokazuje plik, a nie kopię podglądu. */
  form: CoiForm
  /** Cały plik w czytelnym układzie. Do pobrania idzie odpowiedź API bez zmian. */
  fullJson: string
  selection: JsonSelection | null
  mode: JsonMode
  open: boolean
  onToggle: () => void
  panelId: string
}

const CONTENT_ID = 'json-tresc'
const LOCATION_ID = 'json-miejsce'

function Highlighted({ json }: { json: string }) {
  const tokens = useMemo(() => jsonTokens(json), [json])
  return tokens.map((token, i) =>
    token.kind === 'znak' ? (
      token.text
    ) : (
      <span key={i} className={`json-${token.kind}`}>
        {token.text}
      </span>
    ),
  )
}

/**
 * Panel JSON obok podglądu. Domyślnie JSON sekcji, którą urzędnik kliknął albo w której pracuje
 * klawiaturą. „Pokaż JSON” przełącza na cały plik. Na wąskim ekranie panel jest zwinięty pod
 * podglądem, jak oryginał nad nim.
 */
export function JsonPanel({ form, fullJson, selection, mode, open, onToggle, panelId }: Props) {
  // Plik z API może nie mieć kluczy, które podgląd uzupełnił na kopii. Stąd `?.` przy każdym kroku.
  const tab = selection ? form.tabs?.[selection.tabIndex] : undefined
  const top = selection ? tab?.questions?.[selection.cellIndex] : undefined
  const cell = selection?.childIndex === undefined ? top : top?.field?.repeatingSectionGrid?.[selection.childIndex]
  const elementJson = useMemo(() => (cell ? JSON.stringify(cell, null, 2) : ''), [cell])
  const whole = mode === 'plik' || !cell
  const title = whole ? 'Cały plik JSON' : 'JSON wybranego elementu'
  const kind = SECTION_TYPES.has(cell?.field?.type ?? '') ? 'sekcja' : 'pole'
  const parent = selection?.childIndex === undefined ? '' : `, sekcja „${top?.field?.title ?? ''}”`
  const where = cell ? `Strona „${tab?.title ?? ''}”${parent}, ${kind} „${cell.field?.title ?? ''}”.` : ''

  return (
    <section className="inspektor" aria-labelledby="json-tytul" data-open={open}>
      <h2 className="inspektor-tytul" id="json-tytul">
        {title}
      </h2>
      <button type="button" className="b papier-przelacznik inspektor-przelacznik" aria-expanded={open} aria-controls={CONTENT_ID} onClick={onToggle}>
        {open ? `Ukryj ${title.charAt(0).toLowerCase()}${title.slice(1)}` : title}
      </button>
      <div className="inspektor-tresc" id={CONTENT_ID}>
        <div className="inspektor-ramka">
          {!whole && <p className="inspektor-co" id={LOCATION_ID}>{where}</p>}
          {/* Przewijany obszar: fokus z klawiatury pozwala przewijać go strzałkami. */}
          <pre className="json" id={panelId} role="region" tabIndex={0} aria-label={title} aria-describedby={whole ? undefined : LOCATION_ID}>
            <Highlighted json={whole ? fullJson : elementJson} />
          </pre>
        </div>
        <p className="inspektor-rada">
          {whole
            ? 'Przycisk „Pobierz JSON” zapisuje odpowiedź serwera bez zmian.'
            : 'Wybierz element eUsługi lub zakładkę na papierze, aby zobaczyć jego JSON.'}
        </p>
      </div>
    </section>
  )
}
