import { ShieldIcon } from '../components/icons.tsx'
import type { ApiInfo } from '../api.ts'

const STEPS = [
  { title: 'Wczytaj blankiet', text: 'PDF, skan, dokument tekstowy albo arkusz.' },
  { title: 'Poczekaj na analizę', text: 'Zwykle do 3 minut.' },
  { title: 'Sprawdź eUsługę i pobierz JSON', text: 'Przejdź kroki jak mieszkaniec i pobierz plik do importu.' },
]

/** „Jak to działa” i informacja o pliku. Tryb modelu podaje API (`GET /api/info`), nie front. */
export function UploadInfo({ info }: { info: ApiInfo | null }) {
  return (
    <aside className="info" aria-labelledby="info-tytul">
      <h2 className="info-tytul" id="info-tytul">
        Jak to działa
      </h2>
      <ol className="info-kroki">
        {STEPS.map((step, i) => (
          <li key={step.title}>
            <span className="info-numer" aria-hidden="true">
              {i + 1}
            </span>
            <span>
              <b>{step.title}</b>
              <span className="info-opis">{step.text}</span>
            </span>
          </li>
        ))}
      </ol>
      <div className="info-plik">
        <ShieldIcon />
        <p>
          <b>Plik nie jest zapisywany.</b> Serwer czyta go tylko na czas analizy.
          {info?.llm === 'edenai' && ' Tekst odczytany z pliku trafia do modelu w Eden AI.'}
        </p>
      </div>
    </aside>
  )
}
