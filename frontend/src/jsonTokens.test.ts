import { describe, expect, it } from 'vitest'
import { jsonTokens } from './jsonTokens.ts'

describe('jsonTokens', () => {
  it('rozpoznaje klucze, teksty, liczby i stałe', () => {
    const tokens = jsonTokens('{"x": 0, "title": "Kod \\"A\\"", "readOnly": false, "v": null, "n": -1.5e3}')
    const kinds = tokens.filter((token) => token.kind !== 'znak').map((token) => `${token.kind}:${token.text}`)
    expect(kinds).toEqual([
      'klucz:"x"',
      'liczba:0',
      'klucz:"title"',
      'tekst:"Kod \\"A\\""',
      'klucz:"readOnly"',
      'stala:false',
      'klucz:"v"',
      'stala:null',
      'klucz:"n"',
      'liczba:-1.5e3',
    ])
  })

  it('złączone kawałki to dokładnie wejście, także z cyframi i słowami w tekście', () => {
    const json = JSON.stringify({ title: 'Wniosek 12 true null', tabs: [{ id: 'a-1', x: 3 }] }, null, 2)
    expect(jsonTokens(json).map((token) => token.text).join('')).toBe(json)
    expect(jsonTokens(json).filter((token) => token.kind === 'liczba').map((token) => token.text)).toEqual(['3'])
  })
})
