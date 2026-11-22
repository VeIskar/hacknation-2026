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
  destroy(): Promise<void>
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
