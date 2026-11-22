// Podział tekstu JSON na kawałki do podświetlenia. Złączone kawałki dają dokładnie wejście,
// więc podświetlenie nie zmienia pokazanego pliku (sprawdza to test).

export type JsonTokenKind = 'klucz' | 'tekst' | 'liczba' | 'stala' | 'znak'

export interface JsonToken {
  kind: JsonTokenKind
  text: string
}

const TOKEN = /("(?:\\.|[^"\\])*")(\s*:)?|\b(?:true|false|null)\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/g

export function jsonTokens(json: string): JsonToken[] {
  const tokens: JsonToken[] = []
  let last = 0
  for (const match of json.matchAll(TOKEN)) {
    const start = match.index
    if (start > last) tokens.push({ kind: 'znak', text: json.slice(last, start) })
    const [whole, quoted, colon] = match
    if (quoted !== undefined) {
      tokens.push({ kind: colon ? 'klucz' : 'tekst', text: quoted })
      if (colon) tokens.push({ kind: 'znak', text: colon })
    } else {
      tokens.push({ kind: /^[tfn]/.test(whole) ? 'stala' : 'liczba', text: whole })
    }
    last = start + whole.length
  }
  if (last < json.length) tokens.push({ kind: 'znak', text: json.slice(last) })
  return tokens
}
