import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { UploadIcon } from '../components/icons.tsx'
import { formatBytes } from '../format.ts'

interface Props {
  file: File | null
  error: string | null
  errorId: string
  onChoose: (file: File | null) => void
  onSubmit: () => void
}

const FORMATS = ['PDF', 'DOC', 'DOCX', 'ODS', 'XLSX', 'JPG', 'PNG']

export function UploadPanel({ file, error, errorId, onChoose, onSubmit }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!file) inputRef.current?.focus()
    onSubmit()
  }

  return (
    <form onSubmit={submit} noValidate>
      <label className="pole-etykieta" htmlFor="plik">
        Plik formularza
      </label>
      <p className="sr-only" id="plik-opis">
        Formaty: PDF, DOC, DOCX, ODS, XLSX, JPG albo PNG.
      </p>
      {/* Prawdziwy input wypełnia całą strefę i jest przezroczysty: klik, klawiatura i upuszczenie
          pliku działają natywnie. Przycisk w strefie to tylko rysunek, a obrys fokusu rysuje strefa
          przez :has(:focus-visible). */}
      <div
        className="strefa"
        data-over={over}
        data-plik={file ? 'tak' : 'nie'}
        onDragEnter={() => setOver(true)}
        onDragLeave={() => setOver(false)}
        onDrop={() => setOver(false)}
      >
        <input
          ref={inputRef}
          id="plik"
          type="file"
          title=""
          accept=".pdf,.doc,.docx,.ods,.xlsx,.jpg,.jpeg,.jpe,.png"
          aria-describedby={error ? `plik-opis plik-stan ${errorId}` : 'plik-opis plik-stan'}
          aria-invalid={error ? true : undefined}
          onChange={(event) => onChoose(event.target.files?.[0] ?? null)}
        />
        {file ? (
          <>
            <p className="strefa-plik" id="plik-stan">
              <b className="strefa-nazwa">{file.name}</b> <span className="strefa-rozmiar">{formatBytes(file.size)}</span>
            </p>
            <span className="b strefa-przycisk" aria-hidden="true">
              Zmień plik
            </span>
          </>
        ) : (
          <>
            <UploadIcon />
            <p className="strefa-glowne" id="plik-stan">
              {over ? 'Upuść plik tutaj' : 'Przeciągnij plik tutaj'}
            </p>
            <span className="b b-main strefa-przycisk" aria-hidden="true">
              Wybierz plik
            </span>
            <ul className="formaty" aria-hidden="true">
              {FORMATS.map((format) => (
                <li key={format}>{format}</li>
              ))}
            </ul>
          </>
        )}
      </div>
      {error && (
        <p className="blad" id={errorId} role="alert" tabIndex={-1}>
          {error}
        </p>
      )}
      {/* Jeden przycisk główny naraz: przed wyborem pliku jest nim „Wybierz plik” w strefie. */}
      <button type="submit" className={file ? 'b b-main b-krok' : 'b b-krok'}>
        Analizuj formularz
      </button>
    </form>
  )
}
