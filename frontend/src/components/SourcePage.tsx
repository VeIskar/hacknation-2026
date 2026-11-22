import { useEffect, useRef, useState } from 'react'
import type { CSSProperties, KeyboardEvent, RefObject } from 'react'
import { openPdf } from '../pdf.ts'
import type { PdfDocument } from '../pdf.ts'
import { sourceKind } from '../source.ts'

const A4_RATIO = 595 / 842
const THUMBNAIL_WIDTH = 48
const MAX_THUMBNAILS = 24
// Zmiana szerokości okna idzie serią zdarzeń. Rysujemy raz, po chwili ciszy.
const RENDER_DELAY_MS = 80

function paint(target: HTMLCanvasElement, source: HTMLCanvasElement) {
  target.width = source.width
  target.height = source.height
  target.getContext('2d')?.drawImage(source, 0, 0)
}

/** Szerokość elementu w pikselach CSS. Zero, dopóki element jest zwinięty. */
function useWidth(ref: RefObject<HTMLElement | null>): number {
  const [width, setWidth] = useState(0)
  useEffect(() => {
    const element = ref.current
    if (!element) return
    const observer = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width)))
    observer.observe(element)
    return () => observer.disconnect()
  }, [ref])
  return width
}

interface ThumbnailsProps {
  pdf: PdfDocument
  current: number
  onSelect: (pageNumber: number) => void
}

function Thumbnails({ pdf, current, onSelect }: ThumbnailsProps) {
  const count = Math.min(pdf.pageCount, MAX_THUMBNAILS)
  const canvases = useRef<(HTMLCanvasElement | null)[]>([])
  const buttons = useRef<(HTMLButtonElement | null)[]>([])

  useEffect(() => {
    let live = true
    void (async () => {
      for (let pageNumber = 1; pageNumber <= Math.min(pdf.pageCount, MAX_THUMBNAILS) && live; pageNumber++) {
        try {
          const page = await pdf.renderPage(pageNumber, THUMBNAIL_WIDTH)
          const canvas = canvases.current[pageNumber - 1]
          if (live && canvas) paint(canvas, page.canvas)
        } catch {
          return
        }
      }
    })()
    return () => {
      live = false
    }
  }, [pdf])

  // Jeden przystanek Tab dla całego rzędu, strzałki wybierają stronę.
  function onKeyDown(event: KeyboardEvent) {
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[event.key]
    const next = event.key === 'Home' ? 1 : event.key === 'End' ? count : step ? current + step : null
    if (next === null || next < 1 || next > count) return
    event.preventDefault()
    onSelect(next)
    buttons.current[next - 1]?.focus()
  }

  return (
    <>
      <div className="miniatury" role="group" aria-label="Strony oryginału" onKeyDown={onKeyDown}>
        {Array.from({ length: count }, (_, i) => i + 1).map((pageNumber) => (
          <button
            key={pageNumber}
            ref={(element) => {
              buttons.current[pageNumber - 1] = element
            }}
            type="button"
            className="miniatura"
            aria-label={`Strona ${pageNumber}`}
            aria-pressed={pageNumber === current}
            tabIndex={pageNumber === current ? 0 : -1}
            onClick={() => onSelect(pageNumber)}
          >
            <canvas
              ref={(element) => {
                canvases.current[pageNumber - 1] = element
              }}
              aria-hidden="true"
            />
            <span aria-hidden="true">{pageNumber}</span>
          </button>
        ))}
      </div>
      {pdf.pageCount > count && <p className="papier-podpis">Miniatury pokazują pierwsze {count} stron.</p>}
    </>
  )
}

interface PdfPaperProps {
  file: File
  pageNumber: number
  onPageNumber: (pageNumber: number) => void
  onPageCount: (pageCount: number) => void
}

function PdfPaper({ file, pageNumber, onPageNumber, onPageCount }: PdfPaperProps) {
  const [pdf, setPdf] = useState<PdfDocument | null>(null)
  const [failed, setFailed] = useState(false)
  const [ratio, setRatio] = useState(A4_RATIO)
  const [ready, setReady] = useState(false)
  const sheetRef = useRef<HTMLElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const width = useWidth(sheetRef)

  useEffect(() => {
    let current = true
    let opened: PdfDocument | null = null
    openPdf(file)
      .then((next) => {
        opened = next
        if (!current) {
          void next.destroy()
          return
        }
        setPdf(next)
        onPageCount(next.pageCount)
      })
      .catch(() => {
        if (current) setFailed(true)
      })
    return () => {
      current = false
      void opened?.destroy()
    }
    // onPageCount to setter stanu z App: stały, więc PDF otwiera się raz na plik.
  }, [file, onPageCount])

  useEffect(() => {
    if (!pdf || width === 0) return
    let current = true
    const timer = setTimeout(() => {
      pdf
        .renderPage(pageNumber, width)
        .then((page) => {
          if (!current || !canvasRef.current) return
          paint(canvasRef.current, page.canvas)
          setRatio(page.ratio)
          setReady(true)
        })
        .catch(() => {
          if (current) setFailed(true)
        })
    }, RENDER_DELAY_MS)
    return () => {
      current = false
      clearTimeout(timer)
    }
  }, [pdf, pageNumber, width])

  const many = pdf !== null && pdf.pageCount > 1
  return (
    <div className="papier-strony" data-strony={many ? 'wiele' : 'jedna'} style={{ '--proporcja': ratio } as CSSProperties}>
      <div className="papier-pole">
        <figure className="arkusz" ref={sheetRef}>
          <canvas
            ref={canvasRef}
            role="img"
            aria-label={`Strona ${pageNumber} pliku ${file.name}`}
            hidden={!ready || failed}
            data-ready={ready && !failed}
          />
          {!ready && !failed && <p className="arkusz-zdanie">Wczytuję pierwszą stronę pliku.</p>}
          {failed && <p className="arkusz-zdanie">Nie udało się pokazać tego pliku. Analiza nadal jest możliwa.</p>}
        </figure>
      </div>
      {pdf && ready && !failed && (
        <p className="papier-podpis">
          Strona {pageNumber} z {pdf.pageCount}.
        </p>
      )}
      {pdf && many && !failed && <Thumbnails pdf={pdf} current={pageNumber} onSelect={onPageNumber} />}
    </div>
  )
}

function ImagePaper({ file }: { file: File }) {
  const imageRef = useRef<HTMLImageElement>(null)

  // Adres obiektu żyje tylko z tym komponentem, więc trafia prosto do elementu, bez stanu.
  useEffect(() => {
    const image = imageRef.current
    if (!image) return
    const objectUrl = URL.createObjectURL(file)
    image.src = objectUrl
    return () => URL.revokeObjectURL(objectUrl)
  }, [file])

  return (
    <div className="papier-strony" data-strony="jedna">
      <div className="papier-pole">
        <figure className="arkusz arkusz-obraz">
          <img ref={imageRef} alt={`Wczytany plik ${file.name}`} data-ready="true" />
        </figure>
      </div>
    </div>
  )
}

const CONTENT_ID = 'papier-tresc'

interface SourcePageProps {
  file: File
  /** Na ekranie wczytania przełącznik mówi o pierwszej stronie, potem o oryginale. */
  stage: 'wczytaj' | 'dalej'
  pageCount: number | null
  onPageCount: (pageCount: number) => void
}

/**
 * Papier: oryginał wybranego pliku, renderowany w przeglądarce. Na wąskim ekranie jest zwinięty
 * do przełącznika, na szerokim stoi obok i zostaje przy przewijaniu. Wołaj tylko dla PDF-a
 * i obrazu, z `key` zależnym od pliku: nowy plik to nowy stan strony i przełącznika.
 */
export function SourcePage({ file, stage, pageCount, onPageCount }: SourcePageProps) {
  const [open, setOpen] = useState(false)
  const [pageNumber, setPageNumber] = useState(1)
  const where = pageCount ? ` (strona ${pageNumber} z ${pageCount})` : ''
  const label = stage === 'wczytaj' ? (open ? 'Ukryj pierwszą stronę' : 'Pokaż pierwszą stronę') : open ? 'Ukryj oryginał' : `Pokaż oryginał${where}`
  return (
    // Tytuł widać od 1200 px. Węziej jest ukryty, ale dalej nazywa region.
    <section className="papier" aria-labelledby="papier-tytul" data-open={open}>
      <h2 className="papier-tytul" id="papier-tytul">
        Oryginał
      </h2>
      <button type="button" className="b papier-przelacznik" aria-expanded={open} aria-controls={CONTENT_ID} onClick={() => setOpen(!open)}>
        {label}
      </button>
      <div className="papier-tresc" id={CONTENT_ID}>
        {sourceKind(file) === 'pdf' ? (
          <PdfPaper file={file} pageNumber={pageNumber} onPageNumber={setPageNumber} onPageCount={onPageCount} />
        ) : (
          <ImagePaper file={file} />
        )}
      </div>
    </section>
  )
}
