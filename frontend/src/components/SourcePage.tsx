import { useEffect, useRef, useState } from 'react'
import { renderFirstPage } from '../pdf.ts'

type Kind = 'pdf' | 'image' | 'other'

function kindOf(file: File): Kind {
  const name = file.name.toLowerCase()
  if (name.endsWith('.pdf')) return 'pdf'
  if (/\.(jpe?g|jpe|png)$/.test(name)) return 'image'
  return 'other'
}

type PdfState = { status: 'loading' } | { status: 'ready'; pageCount: number } | { status: 'failed' }

// Szerokość renderu w pikselach CSS. Arkusz na ekranie jest węższy, CSS go skaluje.
const RENDER_WIDTH = 640

function PdfPage({ file }: { file: File }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [state, setState] = useState<PdfState>({ status: 'loading' })

  useEffect(() => {
    let current = true
    const canvas = canvasRef.current
    if (!canvas) return
    renderFirstPage(file, canvas, RENDER_WIDTH, () => current)
      .then((page) => {
        if (current && page) setState({ status: 'ready', pageCount: page.pageCount })
      })
      .catch(() => {
        if (current) setState({ status: 'failed' })
      })
    return () => {
      current = false
    }
  }, [file])

  return (
    <>
      <canvas
        ref={canvasRef}
        className="arkusz-obraz"
        role="img"
        aria-label={`Pierwsza strona pliku ${file.name}`}
        hidden={state.status !== 'ready'}
        data-ready={state.status === 'ready'}
      />
      {state.status === 'loading' && <p className="arkusz-zdanie">Wczytuję pierwszą stronę pliku.</p>}
      {state.status === 'failed' && <p className="arkusz-zdanie">Nie udało się pokazać pierwszej strony tego pliku.</p>}
      {state.status === 'ready' && <figcaption className="arkusz-podpis">Strona 1 z {state.pageCount}</figcaption>}
    </>
  )
}

function ImagePage({ file }: { file: File }) {
  const imageRef = useRef<HTMLImageElement>(null)

  // Adres obiektu żyje tylko z tym komponentem, więc trafia prosto do elementu, bez stanu.
  useEffect(() => {
    const image = imageRef.current
    if (!image) return
    const objectUrl = URL.createObjectURL(file)
    image.src = objectUrl
    return () => URL.revokeObjectURL(objectUrl)
  }, [file])

  return <img ref={imageRef} className="arkusz-obraz" alt={`Wczytany plik ${file.name}`} data-ready="true" />
}

/** Papier: pierwsza strona wybranego pliku. Plik nie opuszcza przeglądarki drugi raz. */
export function SourcePage({ file }: { file: File | null }) {
  if (!file) {
    return (
      <div className="arkusz arkusz-pusty">
        <p className="arkusz-zdanie">Tu zobaczysz pierwszą stronę pliku.</p>
      </div>
    )
  }
  const kind = kindOf(file)
  const fileKey = `${file.name}:${file.size}:${file.lastModified}`
  return (
    <figure className={kind === 'other' ? 'arkusz arkusz-pusty' : 'arkusz'}>
      {/* key: nowy plik to nowy komponent, więc stan podglądu zaczyna się od zera. */}
      {kind === 'pdf' && <PdfPage key={fileKey} file={file} />}
      {kind === 'image' && <ImagePage key={fileKey} file={file} />}
      {kind === 'other' && <p className="arkusz-zdanie">Pierwszą stronę pokazujemy dla plików PDF, JPG i PNG.</p>}
    </figure>
  )
}
