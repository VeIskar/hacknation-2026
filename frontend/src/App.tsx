import { useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, UNKNOWN_ERROR, analyzeForm, fetchInfo, isAbort } from './api.ts'
import type { ApiInfo } from './api.ts'
import { AppBar } from './components/AppBar.tsx'
import { statsSentences, structureProblems, technicalProblems } from './check.ts'
import { AlertIcon, CheckIcon, DownloadIcon } from './components/icons.tsx'
import { SourcePage } from './components/SourcePage.tsx'
import { formStats, formatBytes, formatElapsed, jsonFileName, plural } from './format.ts'
import { normalizeForm } from './preview/normalize.ts'
import type { SelectHow } from './preview/Preview.tsx'
import { JsonPanel } from './screens/JsonPanel.tsx'
import type { JsonMode, JsonSelection } from './screens/JsonPanel.tsx'
import { ResultPanel } from './screens/ResultPanel.tsx'
import { UploadInfo } from './screens/UploadInfo.tsx'
import { UPLOAD_FORM_ID, UploadPanel } from './screens/UploadPanel.tsx'
import type { UploadError } from './screens/UploadPanel.tsx'
import { WaitingPanel } from './screens/WaitingPanel.tsx'
import { sourceKind } from './source.ts'
import type { SourceMatch, SourceMatches } from './sourceMatches.ts'
import type { CoiForm } from './types.ts'
import { fileProblem } from './upload.ts'

type Phase =
  | { name: 'upload' }
  | { name: 'waiting'; startedAt: number }
  | {
      name: 'result'
      /** Formularz z API, bez zmian. Panel JSON pokazuje jego fragmenty. */
      form: CoiForm
      /** Kopia do podglądu z uzupełnionymi kluczami (preview/normalize.ts). */
      view: CoiForm
      raw: string
      json: string
      elapsedMs: number
      problems: string[]
    }

const TITLES: Record<Phase['name'], string> = {
  upload: 'Wczytaj formularz',
  waiting: 'Analiza formularza',
  result: 'Podgląd eUsługi',
}

const JSON_PANEL_ID = 'panel-json'
const ERROR_ID = 'plik-blad'
const NOTICE_ID = 'plik-uwaga'
const TOKEN_MISSING = 'Wklej token dostępu, aby wysłać plik.'
const CANCELLED =
  'Przerwano analizę w tej karcie. Serwer mógł jeszcze dokończyć pracę, ale wyniku nie pokażemy.'

/** Pobiera odpowiedź API bez zmian: ten sam plik, który zwrócił `POST /api/forms`. */
function downloadJson(form: CoiForm, raw: string) {
  const url = URL.createObjectURL(new Blob([raw], { type: 'application/json' }))
  const link = document.createElement('a')
  link.href = url
  link.download = jsonFileName(form.title)
  document.body.append(link)
  link.click()
  link.remove()
  // Przeglądarka zaczyna pobieranie po zakończeniu tego zadania, więc adres zwalniamy później.
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function fileKey(file: File): string {
  return `${file.name}:${file.size}:${file.lastModified}`
}

function App() {
  const [file, setFile] = useState<File | null>(null)
  const [pageCount, setPageCount] = useState<number | null>(null)
  const [phase, setPhase] = useState<Phase>({ name: 'upload' })
  const [error, setError] = useState<UploadError | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [needToken, setNeedToken] = useState(false)
  const [token, setToken] = useState('')
  const [info, setInfo] = useState<ApiInfo | null>(null)
  const [jsonMode, setJsonMode] = useState<JsonMode>('element')
  const [jsonOpen, setJsonOpen] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [sourceMatches, setSourceMatches] = useState<SourceMatches | 'failed' | null>(null)
  const [paperPageChoice, setPaperPage] = useState<number | null>(null)
  const [paperOpen, setPaperOpen] = useState(false)
  const [paperFocus, setPaperFocus] = useState<{ id: string } | null>(null)
  const [previewFocus, setPreviewFocus] = useState<SourceMatch | null>(null)
  const [previewPage, setPreviewPage] = useState(0)
  const [previewHidden, setPreviewHidden] = useState<ReadonlySet<string> | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const tokenRef = useRef<HTMLInputElement>(null)
  const shownPhase = useRef(phase.name)
  const focusMessage = useRef(false)
  const focusJson = useRef(false)
  const title = TITLES[phase.name]

  useEffect(() => {
    const controller = new AbortController()
    void fetchInfo({ signal: controller.signal }).then(setInfo)
    return () => controller.abort()
  }, [])

  // Plik upuszczony obok strefy przeglądarka otworzyłaby w miejscu aplikacji, a wynik by przepadł.
  useEffect(() => {
    const guard = (event: DragEvent) => {
      const target = event.target as HTMLElement | null
      if (target?.closest('.strefa')) return
      event.preventDefault()
    }
    window.addEventListener('dragover', guard)
    window.addEventListener('drop', guard)
    return () => {
      window.removeEventListener('dragover', guard)
      window.removeEventListener('drop', guard)
    }
  }, [])

  // Po zmianie ekranu fokus trafia na nagłówek, żeby czytnik ekranu ogłosił nowy ekran. Po błędzie
  // albo przerwaniu trafia na komunikat: sam nagłówek nie mówi, co się stało.
  useEffect(() => {
    document.title = `${title} – PrzeFormuj`
    const changed = shownPhase.current !== phase.name
    shownPhase.current = phase.name
    if (!changed && !focusMessage.current) return
    focusMessage.current = false
    const message = document.getElementById(ERROR_ID) ?? document.getElementById(NOTICE_ID)
    ;(message ?? headingRef.current)?.focus()
  })

  // „Pokaż JSON” stoi w pasku narzędzi, a JSON w panelu bocznym, na wąskim ekranie pod formularzem.
  // Fokus idzie więc za treścią, którą przycisk odsłonił.
  useEffect(() => {
    if (!focusJson.current) return
    focusJson.current = false
    document.getElementById(JSON_PANEL_ID)?.focus()
  })

  function chooseFile(next: File | null) {
    setFile(next)
    setPageCount(null)
    setSourceMatches(null)
    setPaperPage(null)
    setPaperOpen(false)
    setPaperFocus(null)
    setPreviewFocus(null)
    setPreviewPage(0)
    setPreviewHidden(null)
    setError(null)
    setNotice(null)
  }

  function showError(next: UploadError) {
    setError(next)
    focusMessage.current = true
  }

  async function analyze() {
    if (!file) {
      inputRef.current?.focus()
      return
    }
    setNotice(null)
    const problem = fileProblem(file)
    if (problem) {
      showError({ text: problem, target: 'plik' })
      return
    }
    if (needToken && token.trim() === '') {
      showError({ text: TOKEN_MISSING, target: 'token' })
      return
    }
    setError(null)
    const controller = new AbortController()
    abortRef.current = controller
    try {
      let startedAt = performance.now()
      const result = await analyzeForm(file, {
        signal: controller.signal,
        token: needToken ? token : undefined,
        onStart: (at) => {
          startedAt = at
          setPhase({ name: 'waiting', startedAt: at })
        },
      })
      const elapsedMs = performance.now() - startedAt
      const view = normalizeForm(result.form)
      setJsonMode('element')
      setJsonOpen(false)
      setSelectedId(view.tabs[0]?.questions[0]?.field.id ?? null)
      setPhase({
        name: 'result',
        form: result.form,
        view,
        raw: result.raw,
        json: JSON.stringify(result.form, null, 2),
        elapsedMs,
        problems: [...structureProblems(result.form), ...technicalProblems(view)],
      })
    } catch (failure) {
      setPhase({ name: 'upload' })
      if (isAbort(failure)) {
        setNotice(CANCELLED)
        focusMessage.current = true
        return
      }
      const status = failure instanceof ApiError ? failure.status : null
      const text = failure instanceof ApiError ? failure.detail : UNKNOWN_ERROR
      if (status === 401) setNeedToken(true)
      showError({ text, target: status === 401 ? 'token' : 'plik' })
    } finally {
      abortRef.current = null
    }
  }

  function startOver() {
    chooseFile(null)
    setPhase({ name: 'upload' })
  }

  // „Pokaż JSON” przełącza panel na cały plik i z powrotem. Na telefonie panel też się rozwija.
  function toggleJson() {
    const next: JsonMode = jsonMode === 'plik' ? 'element' : 'plik'
    focusJson.current = next === 'plik'
    if (next === 'plik') setJsonOpen(true)
    setJsonMode(next)
  }

  // Klik w element wraca z całego pliku do JSON-u tego elementu. Fokus i zmiana strony tylko
  // przestawiają wybór: Shift+Tab z kodu nie może po cichu wyłączyć „Pokaż JSON”.
  const matches = sourceMatches === 'failed' ? null : sourceMatches
  const selectionSource = selectedId ? matches?.byId.get(selectedId) : undefined
  const paperPage = paperPageChoice ?? selectionSource?.page ?? 1

  function selectElement(id: string | null, how: SelectHow) {
    setSelectedId(id)
    const source = id ? matches?.byId.get(id) : undefined
    if (source) setPaperPage(source.page)
    if (how === 'klik' || how === 'zrodlo') setJsonMode('element')
    if (how === 'zrodlo' && source) {
      setPaperOpen(true)
      setPaperFocus({ id: source.id })
    } else {
      setPaperFocus(null)
    }
  }

  function selectPaper(source: SourceMatch) {
    selectElement(source.id, 'klik')
    setPreviewPage(source.tabIndex)
    setPreviewFocus({ ...source })
  }

  // Szuka w kopii podglądu, bo tam każdy element ma `id`. Kopia zachowuje kolejność, więc te same
  // numery wskazują ten element w pliku z API.
  function selection(form: CoiForm): JsonSelection | null {
    for (const [tabIndex, tab] of form.tabs.entries()) {
      for (const [cellIndex, { field }] of tab.questions.entries()) {
        if (field.id === selectedId) return { tabIndex, cellIndex }
        const childIndex = field.repeatingSectionGrid.findIndex((cell) => cell.field.id === selectedId)
        if (childIndex >= 0) return { tabIndex, cellIndex, childIndex }
      }
    }
    return null
  }

  const paper = file !== null && sourceKind(file) !== 'other'
  const pdf = file !== null && sourceKind(file) === 'pdf'
  const paperLinks = useMemo(() => {
    if (!matches || !previewHidden) return []
    return [...matches.byId.values()].filter(({ id, page, parentId }) =>
      page === paperPage && !previewHidden.has(id) && (!parentId || !previewHidden.has(parentId)),
    )
  }, [matches, paperPage, previewHidden])
  const sourceNotice = !pdf
    ? 'Dopasowanie do papieru jest dostępne dla plików PDF z tekstem.'
    : sourceMatches === 'failed'
      ? 'Nie udało się odczytać tekstu z tego pliku PDF.'
      : !matches
        ? 'Szukam pól i sekcji w oryginale.'
        : !matches.hasText
          ? 'Ten PDF nie zawiera warstwy tekstowej. Dopasowanie do papieru jest niedostępne.'
          : !matches.byId.size
            ? 'Nie znaleziono jednoznacznych dopasowań w oryginale.'
            : null
  const layout = { upload: 'wczytaj', waiting: 'analiza', result: 'wynik' }[phase.name]
  const subtitle = phase.name === 'upload' || !file ? null : `${file.name}, ${formatBytes(file.size)}`

  return (
    <div className="wb">
      <AppBar phase={phase.name} />
      <main className="wb-wrap wb-main" data-uklad={layout} data-papier={paper ? 'tak' : 'nie'}>
        <div className="wb-naglowek">
          <div>
            <h1 ref={headingRef} tabIndex={-1}>
              {title}
            </h1>
            {phase.name === 'upload' && (
              <p className="wb-wstep">PrzeFormuj czyta papierowy wniosek i układa z niego eUsługę oraz plik JSON do importu.</p>
            )}
            {phase.name === 'waiting' && <p className="wb-id">{subtitle}</p>}
            {phase.name === 'result' && (
              <>
                <h2 className="tytul-wniosku">{phase.form.title}</h2>
                <p className="wb-id">
                  Plik: {file?.name}. Czas analizy: {formatElapsed(phase.elapsedMs)}.
                </p>
                <p className="liczby">{statsSentences(formStats(phase.view)).join(' ')}</p>
                <div className="zrodla-status" role="status">
                  {(!pdf || sourceMatches) && (
                    <p>Pola ze źródłem na papierze: {matches?.fieldCount ?? 0} z {formStats(phase.view).fields}</p>
                  )}
                  {sourceNotice && <p>{sourceNotice}</p>}
                </div>
                {phase.problems.length === 0 ? (
                  <p className="kontrola" data-wynik="ok">
                    <CheckIcon />
                    Kontrola techniczna: 0 błędów
                  </p>
                ) : (
                  <div className="kontrola" data-wynik="bledy">
                    <p>
                      <AlertIcon />
                      Kontrola techniczna: {plural(phase.problems.length, ['błąd', 'błędy', 'błędów'])}
                    </p>
                    <ul>
                      {phase.problems.map((problem, index) => (
                        <li key={index}>{problem}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}
          </div>
          {phase.name === 'result' && (
            <div className="narzedzia" role="group" aria-label="Akcje">
              <button type="button" className="b b-main" onClick={() => downloadJson(phase.form, phase.raw)}>
                <DownloadIcon />
                Pobierz JSON
              </button>
              <button type="button" className="b" aria-pressed={jsonMode === 'plik'} onClick={toggleJson}>
                Pokaż JSON
              </button>
              <button type="button" className="b-link" onClick={startOver}>
                Wczytaj inny plik
              </button>
            </div>
          )}
        </div>

        {phase.name === 'upload' && (
          <div className="panel">
            {notice && (
              <p className="uwaga" id={NOTICE_ID} tabIndex={-1}>
                {notice}
              </p>
            )}
            <UploadPanel
              file={file}
              pageCount={pageCount}
              error={error}
              errorId={ERROR_ID}
              needToken={needToken}
              token={token}
              inputRef={inputRef}
              tokenRef={tokenRef}
              onChoose={chooseFile}
              onToken={setToken}
              onSubmit={() => void analyze()}
            />
          </div>
        )}
        {phase.name === 'waiting' && (
          <div className="panel">
            <WaitingPanel startedAt={phase.startedAt} onCancel={() => abortRef.current?.abort()} />
          </div>
        )}

        {/* Papier stoi w DOM po polu pliku, a przed przyciskiem: na telefonie w tej kolejności go widać.
            Ten sam element przez wszystkie etapy, więc PDF rysuje się raz. */}
        {paper && file && (
          <SourcePage
            key={fileKey(file)}
            file={file}
            stage={phase.name === 'upload' ? 'wczytaj' : 'dalej'}
            pageCount={pageCount}
            onPageCount={setPageCount}
            pageNumber={paperPage}
            onPageNumber={(page) => {
              setPaperPage(page)
              setPaperFocus(null)
            }}
            open={paperOpen}
            onToggleOpen={() => {
              setPaperOpen(!paperOpen)
              setPaperFocus(null)
            }}
            form={phase.name === 'result' ? phase.view : null}
            onIndex={setSourceMatches}
            links={paperLinks}
            selectedId={selectedId}
            currentTab={previewPage}
            focusLink={paperFocus}
            onSelectLink={selectPaper}
          />
        )}

        {phase.name === 'upload' && file && (
          <div className="akcja">
            {/* Atrybut form: przycisk stoi poza formularzem, bo między nimi jest papier. */}
            <button type="submit" form={UPLOAD_FORM_ID} className="b b-main b-krok">
              Analizuj formularz
            </button>
          </div>
        )}
        {phase.name === 'upload' && !file && (
          <p className="akcja akcja-opis">Po wyborze pliku pojawi się przycisk „Analizuj formularz”.</p>
        )}
        {phase.name === 'upload' && <UploadInfo info={info} />}

        {phase.name === 'result' && (
          <div className="panel">
            <ResultPanel
              form={phase.view}
              selectedId={selectedId}
              onSelect={selectElement}
              sources={matches?.byId}
              focusSource={previewFocus}
              page={previewPage}
              onPage={setPreviewPage}
              onHidden={setPreviewHidden}
            />
          </div>
        )}
        {phase.name === 'result' && (
          <JsonPanel
            form={phase.form}
            fullJson={phase.json}
            selection={selection(phase.view)}
            mode={jsonMode}
            open={jsonOpen}
            onToggle={() => setJsonOpen(!jsonOpen)}
            panelId={JSON_PANEL_ID}
          />
        )}
      </main>
    </div>
  )
}

export default App
