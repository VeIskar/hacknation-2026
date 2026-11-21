import type { CoiForm } from './types.ts'

export const NETWORK_ERROR = 'Nie udało się połączyć z serwerem. Spróbuj ponownie.'
// Ten sam tekst co `detail` odpowiedzi 500 w SPEC.md.
export const UNKNOWN_ERROR = 'Coś poszło nie tak. Spróbuj ponownie.'

export class ApiError extends Error {
  readonly detail: string
  readonly status: number | null

  constructor(detail: string, status: number | null) {
    super(detail)
    this.name = 'ApiError'
    this.detail = detail
    this.status = status
  }
}

export function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

function isForm(value: unknown): value is CoiForm {
  if (typeof value !== 'object' || value === null) return false
  const form = value as Partial<CoiForm>
  return typeof form.title === 'string' && Array.isArray(form.tabs)
}

interface AnalyzeOptions {
  signal?: AbortSignal
  fetchFn?: typeof fetch
}

/** Wysyła plik do `POST /api/forms`. Błąd API niesie `detail` bez zmian (SPEC "API contract"). */
export async function analyzeForm(file: File, options: AnalyzeOptions = {}): Promise<CoiForm> {
  const { signal, fetchFn = fetch } = options
  const body = new FormData()
  body.append('file', file, file.name)

  let response: Response
  try {
    response = await fetchFn('/api/forms', { method: 'POST', body, signal })
  } catch (error) {
    if (isAbort(error)) throw error
    throw new ApiError(NETWORK_ERROR, null)
  }

  let payload: unknown = null
  try {
    payload = await response.json()
  } catch (error) {
    if (isAbort(error)) throw error
  }

  if (!response.ok) {
    const detail = (payload as { detail?: unknown } | null)?.detail
    throw new ApiError(typeof detail === 'string' && detail !== '' ? detail : UNKNOWN_ERROR, response.status)
  }
  if (!isForm(payload)) throw new ApiError(UNKNOWN_ERROR, response.status)
  return payload
}
