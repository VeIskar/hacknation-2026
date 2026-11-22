import { useEffect, useRef, useState } from 'react'
import { ApiError, UNKNOWN_ERROR, analyzeForm, isAbort } from './api.ts'
import { AppBar } from './components/AppBar.tsx'
import { DownloadIcon } from './components/icons.tsx'
import { SourcePage } from './components/SourcePage.tsx'
import { jsonFileName } from './format.ts'
import { Inspector } from './screens/Inspector.tsx'
import type { InspectorTab } from './screens/Inspector.tsx'
import { ResultPanel } from './screens/ResultPanel.tsx'
import { UploadPanel } from './screens/UploadPanel.tsx'
import { WaitingPanel } from './screens/WaitingPanel.tsx'
import { sourceKind } from './source.ts'
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

const JSON_PANEL_ID = 'panel-json'
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
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>('karta')
  const abortRef = useRef<AbortController | null>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const shownPhase = useRef(phase.name)
  const focusJson = useRef(false)
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

  // „Pokaż JSON” stoi w pasku narzędzi, a JSON w panelu bocznym, na wąskim ekranie pod formularzem.
  // Fokus idzie więc za treścią, którą przycisk odsłonił.
  useEffect(() => {
    if (!focusJson.current) return
    focusJson.current = false
    document.getElementById(JSON_PANEL_ID)?.focus()
  })

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
      setInspectorTab('karta')
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
    setInspectorTab('karta')
    setPhase({ name: 'upload' })
  }

  function toggleJson() {
    const next: InspectorTab = inspectorTab === 'json' ? 'karta' : 'json'
    focusJson.current = next === 'json'
    setInspectorTab(next)
  }

  const paper = file !== null && sourceKind(file) !== 'other'
  const layout = phase.name === 'result' ? (paper ? 'wynik' : 'wynik-bez-papieru') : paper ? 'dwa' : 'start'

  return (
    <div className="wb">
      <AppBar phase={phase.name} />
      <main className="wb-wrap wb-main" data-uklad={layout}>
        <div className="wb-naglowek">
          <div>
            <h1 ref={headingRef} tabIndex={-1}>
              {title}
            </h1>
            <p className="wb-id">{phase.name === 'upload' || !file ? 'Zamień plik wniosku w eUsługę i plik JSON.' : `Plik: ${file.name}`}</p>
          </div>
          {phase.name === 'result' && (
            <div className="narzedzia" role="group" aria-label="Akcje">
              <button type="button" className="b b-main" onClick={() => downloadJson(phase.form, phase.json)}>
                <DownloadIcon />
                Pobierz JSON
              </button>
              <button type="button" className="b" aria-pressed={inspectorTab === 'json'} onClick={toggleJson}>
                Pokaż JSON
              </button>
              <button type="button" className="b-link" onClick={startOver}>
                Wczytaj inny plik
              </button>
            </div>
          )}
        </div>

        {/* Papier stoi w DOM przed panelem, w tej samej kolejności co na ekranie. Pojawia się
            dopiero po wyborze pliku, a panel nie zmienia miejsca w drzewie, więc pole pliku
            nie traci wyboru. */}
        {paper && file && <SourcePage file={file} />}

        <div className="panel">
          {phase.name === 'upload' && <UploadPanel file={file} error={error} errorId={ERROR_ID} onChoose={chooseFile} onSubmit={analyze} />}
          {phase.name === 'waiting' && <WaitingPanel startedAt={phase.startedAt} onCancel={() => abortRef.current?.abort()} />}
          {phase.name === 'result' && <ResultPanel form={phase.form} />}
        </div>

        {phase.name === 'result' && (
          <Inspector
            form={phase.form}
            json={phase.json}
            elapsedMs={phase.elapsedMs}
            tab={inspectorTab}
            onTabChange={setInspectorTab}
            jsonPanelId={JSON_PANEL_ID}
          />
        )}
      </main>
    </div>
  )
}

export default App
