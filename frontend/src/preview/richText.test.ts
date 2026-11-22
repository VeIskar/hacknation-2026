import { describe, expect, it } from 'vitest'
import { isRichTextEmpty, parseRichText, richTextContent } from './richText.ts'

describe('parseRichText', () => {
  it('pusty opis sekcji z COI jest pusty', () => {
    expect(isRichTextEmpty('<html><head></head><body></body></html>')).toBe(true)
    expect(isRichTextEmpty('')).toBe(true)
    expect(isRichTextEmpty('<html><head><title>Tytuł</title></head><body><p> </p></body></html>')).toBe(true)
    expect(isRichTextEmpty('<html><head></head><body><p>Dodaj dokument.</p></body></html>')).toBe(false)
  })

  it('zostawia akapity, pogrubienie i link http z wzorca COI', () => {
    const html =
      '<html><head></head><body><p>Opłata wynosi <strong>17 zł</strong>.</p><p>Więcej na <a href="https://www.biznes.gov.pl/pl/portal/0089#8" target="_blank">biznes.gov.pl</a>.</p></body></html>'
    expect(parseRichText(html)).toEqual([
      { tag: 'p', children: ['Opłata wynosi ', { tag: 'strong', children: ['17 zł'] }, '.'] },
      { tag: 'p', children: ['Więcej na ', { tag: 'a', href: 'https://www.biznes.gov.pl/pl/portal/0089#8', children: ['biznes.gov.pl'] }, '.'] },
    ])
  })

  it('skrypt, styl i obsługa zdarzeń nie przechodzą', () => {
    const nodes = parseRichText('<p onclick="alert(1)">Tekst<script>alert(2)</script><style>p{}</style><img src=x onerror=alert(3)></p>')
    expect(nodes).toEqual([{ tag: 'p', children: ['Tekst'] }])
  })

  it('link z adresem innym niż http, https i mailto traci adres', () => {
    const [bad] = parseRichText('<a href="javascript:alert(1)">Kliknij</a>')
    const [mail] = parseRichText("<a href='mailto:urzad@example.com'>Napisz</a>")
    expect(bad).toEqual({ tag: 'a', href: undefined, children: ['Kliknij'] })
    expect(mail).toEqual({ tag: 'a', href: 'mailto:urzad@example.com', children: ['Napisz'] })
  })

  it('nieznany znacznik zostawia swój tekst, a encje są dekodowane', () => {
    const nodes = parseRichText('<div><span>A &amp; B &lt;c&gt; &#8222;d&#x201D;</span><br>e</div>')
    expect(richTextContent(nodes)).toBe('A & B <c> „d”e')
    expect(nodes).toContainEqual({ tag: 'br', children: [] })
  })

  it('niedomknięty znacznik nie gubi dalszego tekstu', () => {
    expect(richTextContent(parseRichText('<p>Raz <strong>dwa</p><p>trzy</p>'))).toBe('Raz dwatrzy')
  })
})
