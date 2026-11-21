import { describe, expect, it } from 'vitest'
import { ApiError, NETWORK_ERROR, UNKNOWN_ERROR, analyzeForm } from './api.ts'

const file = new File(['%PDF-1.4'], 'Wniosek o wydanie zaświadczenia.pdf', { type: 'application/pdf' })
const form = { title: 'Wniosek', tabs: [{ id: 'a', title: 'Dane', type: 'MAIN', questions: [] }], flow: { links: [] } }

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

async function failure(run: Promise<unknown>): Promise<ApiError> {
  try {
    await run
  } catch (error) {
    if (error instanceof ApiError) return error
    throw error
  }
  throw new Error('analyzeForm nie zgłosiło błędu')
}

describe('analyzeForm', () => {
  it('wysyła jeden plik w polu file metodą POST na /api/forms', async () => {
    const calls: { url: string; init: RequestInit }[] = []
    const fetchFn = (async (url: string, init: RequestInit) => {
      calls.push({ url, init })
      return json(form, 200)
    }) as typeof fetch

    const controller = new AbortController()

    await expect(analyzeForm(file, { fetchFn, signal: controller.signal })).resolves.toEqual(form)

    expect(calls).toHaveLength(1)
    // Bez sygnału w żądaniu przycisk „Przerwij analizę” niczego by nie przerywał.
    expect(calls[0].init.signal).toBe(controller.signal)
    expect(calls[0].url).toBe('/api/forms')
    expect(calls[0].init.method).toBe('POST')
    const body = calls[0].init.body as FormData
    expect([...body.keys()]).toEqual(['file'])
    expect((body.get('file') as File).name).toBe('Wniosek o wydanie zaświadczenia.pdf')
  })

  it('przekazuje detail z odpowiedzi błędu bez zmian', async () => {
    const detail = 'Zawartość pliku nie pasuje do rozszerzenia .pdf.'
    const fetchFn = (async () => json({ detail }, 415)) as typeof fetch

    const error = await failure(analyzeForm(file, { fetchFn }))

    expect(error.detail).toBe(detail)
    expect(error.status).toBe(415)
  })

  it('daje ogólny komunikat, gdy błąd nie ma tekstowego detail', async () => {
    const notJson = (async () => new Response('<html>502</html>', { status: 502 })) as typeof fetch
    const listDetail = (async () => json({ detail: [{ msg: 'field required' }] }, 400)) as typeof fetch

    expect((await failure(analyzeForm(file, { fetchFn: notJson }))).detail).toBe(UNKNOWN_ERROR)
    expect((await failure(analyzeForm(file, { fetchFn: listDetail }))).detail).toBe(UNKNOWN_ERROR)
  })

  it('odrzuca odpowiedź 200, która nie jest formularzem', async () => {
    const fetchFn = (async () => json({ status: 'ok' }, 200)) as typeof fetch

    expect((await failure(analyzeForm(file, { fetchFn }))).detail).toBe(UNKNOWN_ERROR)
  })

  it('zamienia błąd sieci na komunikat o połączeniu', async () => {
    const fetchFn = (async () => {
      throw new TypeError('Failed to fetch')
    }) as typeof fetch

    const error = await failure(analyzeForm(file, { fetchFn }))

    expect(error.detail).toBe(NETWORK_ERROR)
    expect(error.status).toBeNull()
  })

  it('przerwanie przez użytkownika nie jest błędem API', async () => {
    const abort = new DOMException('Aborted', 'AbortError')
    const fetchFn = (async () => {
      throw abort
    }) as typeof fetch

    await expect(analyzeForm(file, { fetchFn })).rejects.toBe(abort)
  })
})
