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

export interface RenderedPage {
  pageCount: number
}

/**
 * Rysuje pierwszą stronę PDF-a na płótnie. Plik zostaje w przeglądarce.
 * `isCurrent` zwraca false, gdy użytkownik zdążył wybrać inny plik: wtedy nie rysujemy.
 */
export async function renderFirstPage(
  file: File,
  canvas: HTMLCanvasElement,
  cssWidth: number,
  isCurrent: () => boolean,
): Promise<RenderedPage | null> {
  const pdfjs = await loadPdfJs()
  const data = new Uint8Array(await file.arrayBuffer())
  const task = pdfjs.getDocument({ data })
  try {
    const pdf = await task.promise
    const page = await pdf.getPage(1)
    if (!isCurrent()) return null
    const base = page.getViewport({ scale: 1 })
    const pixelRatio = Math.min(window.devicePixelRatio || 1, 2)
    const viewport = page.getViewport({ scale: (cssWidth * pixelRatio) / base.width })
    canvas.width = Math.round(viewport.width)
    canvas.height = Math.round(viewport.height)
    await page.render({ canvas, viewport }).promise
    return { pageCount: pdf.numPages }
  } finally {
    await task.destroy()
  }
}
