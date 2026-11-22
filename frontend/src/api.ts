import type { CoiForm } from './types.ts'

export const NETWORK_ERROR = 'Nie udało się połączyć z serwerem. Spróbuj ponownie.'
// Ten sam tekst co `detail` odpowiedzi 500 w SPEC.md.
export const UNKNOWN_ERROR = 'Coś poszło nie tak. Spróbuj ponownie.'
// Odpowiedzi bez `detail` przychodzą od serwera pośredniego (nginx), nie od API.
export const TOO_LARGE_ERROR = 'Plik jest za duży dla serwera. Wybierz mniejszy plik.'
export const TIMEOUT_ERROR = 'Serwer nie odpowiedział na czas. Spróbuj ponownie za chwilę.'
export const BAD_RESULT_ERROR = 'Serwer zwrócił wynik, którego nie da się pokazać. Spróbuj ponownie.'

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

/** Komunikat dla odpowiedzi błędu bez tekstowego `detail`. */
function fallbackDetail(status: number): string {
  if (status === 413) return TOO_LARGE_ERROR
  if (status === 502 || status === 504) return TIMEOUT_ERROR
  return UNKNOWN_ERROR
}

export interface AnalyzeOptions {
  signal?: AbortSignal
  fetchFn?: typeof fetch
  /** Token JWT. Wymagany tylko przy `JWT_ENABLED=true` (SPEC "API contract"). */
  token?: string
  /** Woła się tuż przed wysłaniem żądania, z czasem z `performance.now()`. */
  onStart?: (startedAt: number) => void
}

export interface AnalyzeResult {
  form: CoiForm
  /** Treść odpowiedzi API bajt w bajt. Do pobrania, bez ponownej serializacji. */
  raw: string
}

/** Wysyła plik do `POST /api/forms`. Błąd API niesie `detail` bez zmian (SPEC "API contract"). */
export async function analyzeForm(file: File, options: AnalyzeOptions = {}): Promise<AnalyzeResult> {
  const { signal, fetchFn = fetch, token, onStart } = options
  const body = new FormData()
  body.append('file', file, file.name)
  const headers: Record<string, string> = {}
  const bearer = token?.trim()
  if (bearer) headers.Authorization = `Bearer ${bearer}`

  let response: Response
  try {
    onStart?.(performance.now())
    response = await fetchFn('/api/forms', { method: 'POST', body, headers, signal })
  } catch (error) {
    if (isAbort(error)) throw error
    throw new ApiError(NETWORK_ERROR, null)
  }

  let raw = ''
  try {
    raw = await response.text()
  } catch (error) {
    if (isAbort(error)) throw error
    throw new ApiError(NETWORK_ERROR, response.status)
  }

  let payload: unknown = null
  try {
    payload = JSON.parse(raw)
  } catch {
    payload = null
  }

  if (!response.ok) {
    const detail = (payload as { detail?: unknown } | null)?.detail
    throw new ApiError(typeof detail === 'string' && detail !== '' ? detail : fallbackDetail(response.status), response.status)
  }
  if (!isForm(payload)) throw new ApiError(BAD_RESULT_ERROR, response.status)
  return { form: payload, raw }
}

export interface ApiInfo {
  /** Dostawca modelu: `ollama` (lokalnie) albo `edenai` (README, `GET /api/info`). */
  llm: string
  model: string
}

/** Dostawca i model z `GET /api/info`. `null`, gdy API nie odpowie: to tylko informacja. */
export async function fetchInfo(options: { signal?: AbortSignal; fetchFn?: typeof fetch } = {}): Promise<ApiInfo | null> {
  const { signal, fetchFn = fetch } = options
  try {
    const response = await fetchFn('/api/info', { signal })
    if (!response.ok) return null
    const payload = (await response.json()) as Partial<ApiInfo> | null
    if (typeof payload?.llm !== 'string' || typeof payload.model !== 'string') return null
    return { llm: payload.llm, model: payload.model }
  } catch {
    return null
  }
}
