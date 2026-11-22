import type { PDFPageProxy } from 'pdfjs-dist'
import type { SourceRect, SourceText, SourceTextPage } from './sourceMatches.ts'

type PdfJs = typeof import('pdfjs-dist')

let library: Promise<PdfJs> | null = null

// pdfjs waży ponad 1 MB, więc ładujemy go dopiero po wybraniu pliku PDF.
function loadPdfJs(): Promise<PdfJs> {
  library ??= Promise.all([import('pdfjs-dist'), import('pdfjs-dist/build/pdf.worker.min.mjs?url')]).then(
    ([pdfjs, worker]) => {
      pdfjs.GlobalWorkerOptions.workerSrc = worker.default
      return pdfjs
    },
  )
  return library
}

// Powyżej 3 płótno rośnie szybciej niż ostrość, którą widać.
const MAX_PIXEL_RATIO = 3

export interface RenderedPage {
  /** Płótno poza dokumentem, w pikselach urządzenia. Wywołujący przerysowuje je u siebie. */
  canvas: HTMLCanvasElement
  /** Szerokość strony podzielona przez wysokość. */
  ratio: number
}

export interface PdfDocument {
  pageCount: number
  /** `cssWidth` to szerokość, w jakiej strona stanie na ekranie: render trafia piksel w piksel. */
  renderPage(pageNumber: number, cssWidth: number): Promise<RenderedPage>
  readTextPages(signal: AbortSignal): Promise<SourceTextPage[]>
  destroy(): Promise<void>
}

interface PdfLine {
  text: string
  rects: SourceRect[]
  x: number
  y: number
  right: number
  height: number
  fontName: string
}

type TextViewport = Pick<ReturnType<PDFPageProxy['getViewport']>, 'transform' | 'width' | 'height'>
type TextContent = Awaited<ReturnType<PDFPageProxy['getTextContent']>>

export function textPage(viewport: TextViewport, { items, styles }: TextContent): SourceTextPage {
  const [vx, vy, wx, wy, tx, ty] = viewport.transform
  const project = (x: number, y: number) => [vx * x + wx * y + tx, vy * x + wy * y + ty]
  const lines: PdfLine[] = []
  let line: PdfLine | undefined
  let hasText = false
  for (const item of items) {
    if (!('str' in item)) continue
    if (item.str.trim()) {
      hasText ||= /[\p{L}\p{N}]/u.test(item.str)
      const [a, b, , , x, y] = item.transform
      const height = item.height
      const style = styles[item.fontName]
      // Prostokąt z metryk tekstu i tego samego widoku (obrót, obszar cięcia) co płótno.
      const horizontal = a > 0 && Math.abs(b) < a * 0.01 && !style?.vertical
      const ascent = (style?.ascent || (style?.descent ? 1 + style.descent : 0.8)) * height
      const [left, top] = project(x, y + ascent - height)
      const [right, bottom] = project(x + item.width, y + ascent)
      const x1 = Math.max(0, Math.min(left, right))
      const y1 = Math.max(0, Math.min(top, bottom))
      const x2 = Math.min(viewport.width, Math.max(left, right))
      const y2 = Math.min(viewport.height, Math.max(top, bottom))
      const rect = horizontal && x2 > x1 && y2 > y1
        ? { left: x1 / viewport.width, top: y1 / viewport.height, width: (x2 - x1) / viewport.width, height: (y2 - y1) / viewport.height }
        : null
      if (!rect) {
        // Taki tekst może wykluczyć jednoznaczność, lecz nie daje zakładki.
        lines.push({ text: item.str, rects: [], x, y, right: x, height, fontName: item.fontName })
        line = undefined
        continue
      }
      const gap = line ? x - line.right : 0
      if (line && Math.abs(y - line.y) <= height * 0.25 && gap >= -height * 0.25 && gap <= height * 1.5) {
        line.text += (gap > height * 0.15 ? ' ' : '') + item.str
        line.right = x + item.width
        line.rects.push(rect)
      } else {
        line = { text: item.str, rects: [rect], x, y, right: x + item.width, height, fontName: item.fontName }
        lines.push(line)
      }
    } else if (line && item.str) {
      line.text += item.str
    }
    if (item.hasEOL) line = undefined
  }
  const wrapped: SourceText[] = []
  for (const [index, first] of lines.entries()) {
    const second = lines[index + 1]
    if (!second || !first.rects.length || !second.rects.length || /[:?.…_*]\s*$/.test(first.text)) continue
    // Samo sąsiedztwo nie wystarcza. „Data” i „Podpis” mogą mieć identyczne wcięcie.
    if (!/^\s*\p{Ll}/u.test(second.text) || first.fontName !== second.fontName || Math.abs(first.height - second.height) > 0.1) continue
    const gap = first.y - second.y
    if (Math.abs(first.x - second.x) <= first.height * 0.5 && gap >= first.height * 0.8 && gap <= first.height * 1.6) {
      wrapped.push({ text: `${first.text.trim()} ${second.text.trim()}`, rects: [...first.rects, ...second.rects] })
    }
  }
  return { lines, wrapped, hasText }
}

/** Otwiera PDF w przeglądarce. Plik nie jest nigdzie wysyłany. */
export async function openPdf(file: File): Promise<PdfDocument> {
  const pdfjs = await loadPdfJs()
  const data = new Uint8Array(await file.arrayBuffer())
  const task = pdfjs.getDocument({ data })
  try {
    const pdf = await task.promise
    return {
      pageCount: pdf.numPages,
      async readTextPages(signal) {
        const pages: SourceTextPage[] = []
        for (let page = 1; page <= pdf.numPages; page++) {
          signal.throwIfAborted()
          const pdfPage = await pdf.getPage(page)
          pages.push(textPage(pdfPage.getViewport({ scale: 1 }), await pdfPage.getTextContent()))
        }
        signal.throwIfAborted()
        return pages
      },
      async renderPage(pageNumber, cssWidth) {
        const page = await pdf.getPage(pageNumber)
        const base = page.getViewport({ scale: 1 })
        const pixelRatio = Math.min(window.devicePixelRatio || 1, MAX_PIXEL_RATIO)
        const viewport = page.getViewport({ scale: (cssWidth * pixelRatio) / base.width })
        // Osobne płótno na każdy render: pdfjs nie pozwala rysować dwa razy naraz na tym samym.
        const canvas = document.createElement('canvas')
        canvas.width = Math.round(viewport.width)
        canvas.height = Math.round(viewport.height)
        // Własny kontekst z przezroczystością: na nieprzezroczystym płótnie, które pdfjs tworzy sam,
        // przeglądarka wygładza tekst subpikselowo i kropkowane linie wniosku dostają kolorowe obwódki.
        const canvasContext = canvas.getContext('2d')
        if (!canvasContext) throw new Error('Przeglądarka nie dała kontekstu płótna')
        await page.render({ canvas: null, canvasContext, viewport }).promise
        return { canvas, ratio: base.width / base.height }
      },
      destroy: () => task.destroy(),
    }
  } catch (error) {
    await task.destroy()
    throw error
  }
}
