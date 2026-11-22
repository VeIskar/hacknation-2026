import { describe, expect, it } from 'vitest'
import { ApiError, BAD_RESULT_ERROR, NETWORK_ERROR, TIMEOUT_ERROR, TOO_LARGE_ERROR, UNKNOWN_ERROR, analyzeForm, fetchInfo } from './api.ts'

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

    const result = await analyzeForm(file, { fetchFn, signal: controller.signal })
    expect(result.form).toEqual(form)

    expect(calls).toHaveLength(1)
    // Bez sygnału w żądaniu przycisk „Przerwij analizę” niczego by nie przerywał.
    expect(calls[0].init.signal).toBe(controller.signal)
    expect(calls[0].url).toBe('/api/forms')
    expect(calls[0].init.method).toBe('POST')
    const body = calls[0].init.body as FormData
    expect([...body.keys()]).toEqual(['file'])
    expect((body.get('file') as File).name).toBe('Wniosek o wydanie zaświadczenia.pdf')
    // Bez tokenu nie ma nagłówka: przy JWT_ENABLED=false API go nie wymaga.
    expect(new Headers(calls[0].init.headers).has('Authorization')).toBe(false)
  })

  it('dodaje token jako nagłówek Bearer', async () => {
    let headers = new Headers()
    const fetchFn = (async (_url: string, init: RequestInit) => {
      headers = new Headers(init.headers)
      return json(form, 200)
    }) as typeof fetch

    await analyzeForm(file, { fetchFn, token: '  abc.def.ghi \n' })

    expect(headers.get('Authorization')).toBe('Bearer abc.def.ghi')
  })

  it('oddaje treść odpowiedzi bajt w bajt, do pobrania bez zmian', async () => {
    const raw = '{"title":"Wniosek","tabs":[],"flow":{"links":[]},"liczba":1.0}'
    const fetchFn = (async () => new Response(raw, { status: 200 })) as typeof fetch

    const result = await analyzeForm(file, { fetchFn })

    expect(result.raw).toBe(raw)
    // Ponowna serializacja zgubiłaby zapis 1.0. Dlatego pobieramy `raw`, a nie `form`.
    expect(JSON.stringify(result.form)).not.toBe(raw)
  })

  it('liczy czas od chwili wysłania żądania', async () => {
    const order: string[] = []
    const fetchFn = (async () => {
      order.push('fetch')
      return json(form, 200)
    }) as typeof fetch

    await analyzeForm(file, { fetchFn, onStart: (startedAt) => order.push(typeof startedAt) })

    expect(order).toEqual(['number', 'fetch'])
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

    const notJson500 = (async () => new Response('<html>500</html>', { status: 500 })) as typeof fetch

    expect((await failure(analyzeForm(file, { fetchFn: notJson }))).detail).toBe(TIMEOUT_ERROR)
    expect((await failure(analyzeForm(file, { fetchFn: notJson500 }))).detail).toBe(UNKNOWN_ERROR)
    expect((await failure(analyzeForm(file, { fetchFn: listDetail }))).detail).toBe(UNKNOWN_ERROR)
  })

  it('rozpoznaje limit i czas serwera pośredniego po kodzie odpowiedzi', async () => {
    const tooLarge = (async () => new Response('<html>413</html>', { status: 413 })) as typeof fetch
    const timeout = (async () => new Response('', { status: 504 })) as typeof fetch

    expect((await failure(analyzeForm(file, { fetchFn: tooLarge }))).detail).toBe(TOO_LARGE_ERROR)
    expect((await failure(analyzeForm(file, { fetchFn: timeout }))).detail).toBe(TIMEOUT_ERROR)
  })

  it('pokazuje 401 z treścią z API i zachowuje kod', async () => {
    const detail = 'Brak tokenu dostępu albo token jest nieważny.'
    const fetchFn = (async () => json({ detail }, 401)) as typeof fetch

    const error = await failure(analyzeForm(file, { fetchFn }))

    expect(error.detail).toBe(detail)
    expect(error.status).toBe(401)
  })

  it('odrzuca odpowiedź 200, która nie jest formularzem', async () => {
    const fetchFn = (async () => json({ status: 'ok' }, 200)) as typeof fetch

    expect((await failure(analyzeForm(file, { fetchFn }))).detail).toBe(BAD_RESULT_ERROR)
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

describe('fetchInfo', () => {
  it('czyta dostawcę i model z GET /api/info', async () => {
    let url = ''
    const fetchFn = (async (target: string) => {
      url = target
      return json({ llm: 'edenai', model: 'flexai/Qwen3.5-9B@eu' }, 200)
    }) as typeof fetch

    await expect(fetchInfo({ fetchFn })).resolves.toEqual({ llm: 'edenai', model: 'flexai/Qwen3.5-9B@eu' })
    expect(url).toBe('/api/info')
  })

  it('daje null przy błędzie, złej treści i braku sieci', async () => {
    const notFound = (async () => json({ detail: 'Not Found' }, 404)) as typeof fetch
    const wrong = (async () => json({ llm: 1 }, 200)) as typeof fetch
    const offline = (async () => {
      throw new TypeError('Failed to fetch')
    }) as typeof fetch

    for (const fetchFn of [notFound, wrong, offline]) await expect(fetchInfo({ fetchFn })).resolves.toBeNull()
  })
})
