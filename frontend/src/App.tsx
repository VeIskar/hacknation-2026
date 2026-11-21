import { useEffect, useRef, useState } from 'react'
import { ApiError, UNKNOWN_ERROR, analyzeForm, isAbort } from './api.ts'
import { SourcePage } from './components/SourcePage.tsx'
import { jsonFileName } from './format.ts'
import { ResultPanel } from './screens/ResultPanel.tsx'
import { UploadPanel } from './screens/UploadPanel.tsx'
import { WaitingPanel } from './screens/WaitingPanel.tsx'
import type { CoiForm } from './types.ts'

type Phase =
  | { name: 'upload' }
  | { name: 'waiting'; startedAt: number }
  | { name: 'result'; form: CoiForm; json: string; elapsedMs: number }

const TITLES: Record<Phase['name'], string> = {
  upload: 'Wczytaj formularz',
  waiting: 'Analiza formularza',
  result: 'Podgląd eUsługi',
}

const JSON_REGION_ID = 'json-formularza'
const ERROR_ID = 'plik-blad'

function downloadJson(form: CoiForm, json: string) {
  const url = URL.createObjectURL(new Blob([json], { type: 'application/json' }))
  const link = document.createElement('a')
  link.href = url
  link.download = jsonFileName(form.title)
  document.body.append(link)
  link.click()
  link.remove()
  // Przeglądarka zaczyna pobieranie po zakończeniu tego zadania, więc adres zwalniamy później.
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function App() {
  const [file, setFile] = useState<File | null>(null)
  const [phase, setPhase] = useState<Phase>({ name: 'upload' })
  const [error, setError] = useState<string | null>(null)
  const [jsonShown, setJsonShown] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const shownPhase = useRef(phase.name)
  const title = TITLES[phase.name]

  // Po zmianie ekranu fokus trafia na nagłówek, żeby czytnik ekranu ogłosił nowy ekran.
  // Po błędzie API trafia na komunikat: sam nagłówek nie mówi, co poszło źle.
  useEffect(() => {
    document.title = `${title} – PrzeFormuj`
    if (shownPhase.current === phase.name) return
    shownPhase.current = phase.name
    const alert = document.getElementById(ERROR_ID)
    ;(alert ?? headingRef.current)?.focus()
  }, [phase.name, title])

  function chooseFile(next: File | null) {
    setFile(next)
    setError(null)
  }

  async function analyze() {
    if (!file) {
      setError('Wybierz plik formularza.')
      return
    }
    setError(null)
    const controller = new AbortController()
    abortRef.current = controller
    const startedAt = performance.now()
    setPhase({ name: 'waiting', startedAt })
    try {
      const form = await analyzeForm(file, { signal: controller.signal })
      setJsonShown(false)
      setPhase({ name: 'result', form, json: JSON.stringify(form, null, 2), elapsedMs: performance.now() - startedAt })
    } catch (failure) {
      setPhase({ name: 'upload' })
      if (isAbort(failure)) return
      setError(failure instanceof ApiError ? failure.detail : UNKNOWN_ERROR)
    }
  }

  function startOver() {
    setFile(null)
    setError(null)
    setJsonShown(false)
    setPhase({ name: 'upload' })
  }

  return (
    <main className="wb">
      <header className="wb-top">
        <div>
          <h1 ref={headingRef} tabIndex={-1}>
            {title}
          </h1>
          <p className="wb-id">
            <b>PrzeFormuj</b>
            {phase.name === 'upload' || !file ? ' zamienia plik wniosku w eUsługę i plik JSON.' : `, plik: ${file.name}`}
          </p>
        </div>
        {phase.name === 'result' && (
          <div className="wb-akcje">
            <button
              type="button"
              className="b"
              aria-expanded={jsonShown}
              aria-controls={JSON_REGION_ID}
              onClick={() => setJsonShown((shown) => !shown)}
            >
              {jsonShown ? 'Ukryj JSON' : 'Pokaż JSON'}
            </button>
            <button type="button" className="b b-main" onClick={() => downloadJson(phase.form, phase.json)}>
              Pobierz JSON
            </button>
            <button type="button" className="b" onClick={startOver}>
              Wczytaj inny plik
            </button>
          </div>
        )}
      </header>

      <div className="scena">
        <div className="panel">
          {phase.name === 'upload' && <UploadPanel file={file} error={error} errorId={ERROR_ID} onChoose={chooseFile} onSubmit={analyze} />}
          {phase.name === 'waiting' && (
            <WaitingPanel startedAt={phase.startedAt} onCancel={() => abortRef.current?.abort()} />
          )}
          {phase.name === 'result' && (
            <ResultPanel
              form={phase.form}
              json={phase.json}
              elapsedMs={phase.elapsedMs}
              jsonShown={jsonShown}
              jsonRegionId={JSON_REGION_ID}
            />
          )}
        </div>
        <section className="papier" aria-label="Podgląd pliku">
          <SourcePage file={file} />
        </section>
      </div>
    </main>
  )
}

export default App
