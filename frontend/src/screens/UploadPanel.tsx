import { useState } from 'react'
import type { DragEvent, FormEvent, RefObject } from 'react'
import { DocumentIcon, UploadIcon } from '../components/icons.tsx'
import { PAGES, formatBytes, plural } from '../format.ts'
import { ACCEPT_ATTRIBUTE, MAX_FILE_MB } from '../upload.ts'

export const UPLOAD_FORM_ID = 'wczytaj'
export const FILE_INPUT_ID = 'plik'
export const TOKEN_INPUT_ID = 'token'

/** Błąd przy polu: pliku (typ, nazwa, odpowiedź API) albo tokenu (401). */
export interface UploadError {
  text: string
  target: 'plik' | 'token'
}

interface Props {
  file: File | null
  pageCount: number | null
  error: UploadError | null
  errorId: string
  needToken: boolean
  token: string
  inputRef: RefObject<HTMLInputElement | null>
  tokenRef: RefObject<HTMLInputElement | null>
  onChoose: (file: File | null) => void
  onToken: (token: string) => void
  onSubmit: () => void
}

/**
 * Pole pliku i token. Przycisk „Analizuj formularz” stoi osobno (atrybut `form`), bo na telefonie
 * między kartą pliku a przyciskiem jest pierwsza strona pliku.
 *
 * Jeden prawdziwy input przez cały czas, w tym samym miejscu drzewa, więc fokus i wybór zostają
 * po zmianie wyglądu. Pusta strefa: input jest przezroczysty i wypełnia całą strefę, więc klik,
 * klawiatura i upuszczenie pliku działają natywnie. Po wyborze pliku input przykrywa tylko odsyłacz
 * „Zmień plik”, a upuszczenie nowego pliku na kartę obsługuje `onDrop`.
 */
export function UploadPanel(props: Props) {
  const { file, pageCount, error, errorId, needToken, token, inputRef, tokenRef, onChoose, onToken, onSubmit } = props
  const [over, setOver] = useState(false)
  const fileError = error?.target === 'plik' ? error : null
  const tokenError = error?.target === 'token' ? error : null

  function submit(event: FormEvent) {
    event.preventDefault()
    onSubmit()
  }

  // Na pustej strefie plik przyjmuje sam input. Na karcie pliku cel upuszczenia to karta.
  function dragOver(event: DragEvent) {
    if (!file) return
    event.preventDefault()
    setOver(true)
  }

  function drop(event: DragEvent) {
    setOver(false)
    if (!file || event.target === inputRef.current) return
    event.preventDefault()
    const dropped = event.dataTransfer.files[0]
    if (dropped) onChoose(dropped)
  }

  const describedBy = ['plik-opis', 'plik-stan', fileError && errorId].filter(Boolean).join(' ')
  const details = file ? [formatBytes(file.size), pageCount ? plural(pageCount, PAGES) : null].filter(Boolean).join(', ') : ''

  return (
    <form id={UPLOAD_FORM_ID} onSubmit={submit} noValidate>
      <label className="pole-etykieta" htmlFor={FILE_INPUT_ID} id="plik-etykieta">
        Plik formularza
      </label>
      <p className="pole-opis" id="plik-opis">
        PDF, DOC, DOCX, ODS, XLSX, JPG albo PNG. Najwyżej {MAX_FILE_MB} MB.
      </p>
      <div
        className="strefa"
        data-over={over}
        data-plik={file ? 'tak' : 'nie'}
        data-invalid={fileError ? true : undefined}
        onDragEnter={() => setOver(true)}
        onDragLeave={() => setOver(false)}
        onDragOver={dragOver}
        onDrop={drop}
      >
        {file ? (
          <>
            <DocumentIcon size={28} />
            <p className="strefa-plik" id="plik-stan">
              <b className="strefa-nazwa">{file.name}</b>
              <span className="strefa-rozmiar">{details}</span>
            </p>
          </>
        ) : (
          <>
            <UploadIcon />
            <p className="strefa-glowne" id="plik-stan">
              {over ? 'Upuść plik tutaj' : 'Przeciągnij plik tutaj'}
            </p>
            <p className="strefa-albo" aria-hidden="true">
              albo
            </p>
          </>
        )}
        <span className="strefa-akcja">
          {/* Nazwa: etykieta i widoczny napis akcji, żeby zadziałało też sterowanie głosem. */}
          <input
            ref={inputRef}
            id={FILE_INPUT_ID}
            type="file"
            title=""
            accept={ACCEPT_ATTRIBUTE}
            aria-labelledby="plik-etykieta plik-akcja"
            aria-describedby={describedBy}
            aria-invalid={fileError ? true : undefined}
            onChange={(event) => onChoose(event.target.files?.[0] ?? null)}
          />
          <span className={file ? 'strefa-zmien' : 'b b-main strefa-przycisk'} id="plik-akcja" aria-hidden="true">
            {file ? 'Zmień plik' : 'Wybierz plik'}
          </span>
        </span>
      </div>
      {fileError && (
        <p className="blad" id={errorId} role="alert" tabIndex={-1}>
          {fileError.text}
        </p>
      )}
      {needToken && (
        <div className="token" data-invalid={tokenError ? true : undefined}>
          <label className="pole-etykieta" htmlFor={TOKEN_INPUT_ID}>
            Token dostępu
          </label>
          <p className="pole-opis" id="token-opis">
            Ten serwer wymaga tokenu. Wklej token od administratora. Zostaje tylko w tej karcie.
          </p>
          {tokenError && (
            <p className="blad" id={errorId} role="alert" tabIndex={-1}>
              {tokenError.text}
            </p>
          )}
          <input
            ref={tokenRef}
            id={TOKEN_INPUT_ID}
            className="pole-tekst"
            type="password"
            autoComplete="off"
            spellCheck={false}
            value={token}
            aria-describedby={tokenError ? `token-opis ${errorId}` : 'token-opis'}
            aria-invalid={tokenError ? true : undefined}
            onChange={(event) => onToken(event.target.value)}
          />
        </div>
      )}
    </form>
  )
}
