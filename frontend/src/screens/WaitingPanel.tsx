import { useEffect, useState } from 'react'
import { formatElapsed } from '../format.ts'

interface Props {
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

/** Oczekiwanie bez udawanych etapów: prawdziwy czas i jedno zdanie o tym, co robi serwer. */
export function WaitingPanel({ startedAt, onCancel }: Props) {
  const elapsed = useElapsed(startedAt)
  return (
    <div className="czekanie">
      <p className="czas-etykieta" id="czas-etykieta">
        Analiza trwa
      </p>
      {/* Licznik zmienia się co sekundę, więc czytnik ekranu go nie ogłasza. Ogłasza zdanie niżej. */}
      <p className="czas" role="timer" aria-live="off" aria-labelledby="czas-etykieta">
        <span className="zakreslone-pas">{formatElapsed(elapsed)}</span>
      </p>
      <p className="zdanie" role="status">
        Serwer czyta plik, a model układa z niego strony, sekcje i pola eUsługi.
      </p>
      <p className="zdanie">Zwykle trwa to do 3 minut. Nie zamykaj tej karty.</p>
      <button type="button" className="b b-krok" onClick={onCancel}>
        Przerwij analizę
      </button>
    </div>
  )
}
