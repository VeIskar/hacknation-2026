import { useEffect, useState } from 'react'
import { formatElapsed } from '../format.ts'

interface Props {
  /** Chwila wysłania żądania (`performance.now()`), a nie kliknięcia. */
  startedAt: number
  onCancel: () => void
}

function useElapsed(startedAt: number): number {
  const [now, setNow] = useState(() => performance.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(performance.now()), 250)
    return () => clearInterval(timer)
  }, [])
  return now - startedAt
}

/**
 * Oczekiwanie bez udawanych etapów: prawdziwy czas i jedno zdanie o tym, co robi serwer.
 * „Przerwij analizę” przerywa żądanie w przeglądarce. API nie ma sposobu, by zatrzymać pracę
 * serwera, więc komunikat po przerwaniu mówi to wprost (App.tsx).
 */
export function WaitingPanel({ startedAt, onCancel }: Props) {
  const elapsed = useElapsed(startedAt)
  return (
    <div className="czekanie">
      <p className="czas-etykieta" id="czas-etykieta">
        Analiza trwa
      </p>
      {/* Licznik zmienia się co sekundę, więc czytnik ekranu go nie ogłasza. Zdanie niżej czytnik przeczyta po h1, na który przechodzi fokus. */}
      <p className="czas" role="timer" aria-live="off" aria-labelledby="czas-etykieta">
        {formatElapsed(elapsed)}
      </p>
      <p className="zdanie">
        Serwer czyta plik, a model układa z niego kroki, sekcje i pola eUsługi.
      </p>
      <p className="zdanie">Zwykle trwa to do 3 minut. Nie zamykaj tej karty.</p>
      <button type="button" className="b b-krok" onClick={onCancel}>
        Przerwij analizę
      </button>
    </div>
  )
}
