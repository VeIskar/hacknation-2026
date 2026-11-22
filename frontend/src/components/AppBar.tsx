import { CheckIcon, DocumentIcon } from './icons.tsx'

const STEPS = [
  { phase: 'upload', label: 'Wczytaj' },
  { phase: 'waiting', label: 'Analiza' },
  { phase: 'result', label: 'Podgląd' },
] as const

export type PhaseName = (typeof STEPS)[number]['phase']

const STATUS = { zrobiony: 'Gotowe', biezacy: 'Teraz', przed: 'Później' } as const

/**
 * Pasek usługi, linia wersji testowej i trzy etapy pracy. Stan etapu mówi tekst („Gotowe”,
 * „Teraz”, „Później”) i kształt znaku, nie sam kolor. Na wąskim ekranie etapy zwijają się do
 * jednego zdania; obie wersje są w DOM, a CSS pokazuje jedną, więc czytnik słyszy je raz.
 */
export function AppBar({ phase }: { phase: PhaseName }) {
  const current = STEPS.findIndex((step) => step.phase === phase)
  return (
    <>
      <header className="pasek">
        <div className="wb-wrap pasek-wiersz">
          <p className="pasek-marka">
            <DocumentIcon />
            PrzeFormuj
          </p>
          <p className="pasek-opis">Narzędzie dla urzędów</p>
        </div>
      </header>
      <div className="wersja">
        <p className="wb-wrap wersja-wiersz">
          <strong className="wersja-znak">Wersja testowa</strong>
          <span>
            Sprawdź wynik przed importem<span className="wersja-dalej"> do systemu docelowego</span>.
          </span>
        </p>
      </div>
      <nav className="wb-wrap etapy" aria-label="Etapy pracy">
        <div className="etapy-skrot">
          <p>
            <b>
              Etap {current + 1} z {STEPS.length}:
            </b>{' '}
            {STEPS[current].label}
          </p>
          <div className="etapy-pasek" aria-hidden="true">
            {STEPS.map((step, i) => (
              <span key={step.phase} data-pelny={i <= current} />
            ))}
          </div>
        </div>
        <ol className="etapy-lista">
          {STEPS.map((step, i) => {
            const state = i < current ? 'zrobiony' : i === current ? 'biezacy' : 'przed'
            return (
              <li key={step.phase} className="etap" data-stan={state} aria-current={state === 'biezacy' ? 'step' : undefined}>
                <span className="etap-znak" aria-hidden="true">
                  {state === 'zrobiony' ? <CheckIcon /> : i + 1}
                </span>
                <span className="etap-opis">
                  <span className="etap-nazwa">{step.label}</span>
                  <span className="etap-stan">{STATUS[state]}</span>
                </span>
              </li>
            )
          })}
        </ol>
      </nav>
    </>
  )
}
