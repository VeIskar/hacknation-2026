import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { formatBytes } from '../format.ts'

interface Props {
  file: File | null
  error: string | null
  errorId: string
  onChoose: (file: File | null) => void
  onSubmit: () => void
}

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
      <p className="pole-opis" id="plik-opis">
        PDF, DOC, DOCX, ODS, XLSX, JPG albo PNG.
      </p>
      {/* Prawdziwy input wypełnia całą strefę i jest przezroczysty: klik, klawiatura i upuszczenie
          pliku działają natywnie. Obrys fokusu rysuje strefa przez :has(:focus-visible). */}
      <div
        className="strefa"
        data-over={over}
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
        <p className="strefa-tekst" id="plik-stan">
          {file ? (
            <>
              <span className="zakreslone">{file.name}</span> {formatBytes(file.size)}. Możesz wybrać inny plik.
            </>
          ) : over ? (
            'Upuść plik.'
          ) : (
            'Przeciągnij plik tutaj albo wybierz go z dysku.'
          )}
        </p>
      </div>
      {error && (
        <p className="blad" id={errorId} role="alert" tabIndex={-1}>
          {error}
        </p>
      )}
      <button type="submit" className="b b-main b-krok">
        Analizuj formularz
      </button>
    </form>
  )
}
