// Opisy sekcji i pól są w JSON-ie COI dokumentami HTML. Podgląd nie wstawia ich do strony
// jako HTML: przepuszcza tylko znaczniki z listy niżej, resztę zamienia na sam tekst.

export type RichTag = 'p' | 'strong' | 'em' | 'a' | 'ul' | 'ol' | 'li' | 'br'

export interface RichElement {
  tag: RichTag
  href?: string
  children: RichNode[]
}

export type RichNode = string | RichElement

const TAGS: Record<string, RichTag> = {
  p: 'p',
  strong: 'strong',
  b: 'strong',
  em: 'em',
  i: 'em',
  a: 'a',
  ul: 'ul',
  ol: 'ol',
  li: 'li',
  br: 'br',
}
const SKIPPED = new Set(['head', 'script', 'style', 'title'])
const ENTITIES: Record<string, string> = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ' }

function decode(text: string): string {
  return text.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (whole, name: string) => {
    if (name[0] !== '#') return ENTITIES[name.toLowerCase()] ?? whole
    const code = name[1].toLowerCase() === 'x' ? parseInt(name.slice(2), 16) : parseInt(name.slice(1), 10)
    return code > 0 && code <= 0x10ffff ? String.fromCodePoint(code) : whole
  })
}

function safeHref(attributes: string): string | undefined {
  const match = /\bhref\s*=\s*(?:"([^"]*)"|'([^']*)')/i.exec(attributes)
  const href = decode(match?.[1] ?? match?.[2] ?? '').trim()
  return /^(https?:\/\/|mailto:)/i.test(href) ? href : undefined
}

export function parseRichText(html: string): RichNode[] {
  const root: RichNode[] = []
  const open: RichElement[] = []
  let skipped: string | null = null
  const target = () => open.at(-1)?.children ?? root

  for (const token of html.split(/(<[^>]*>)/)) {
    const tag = /^<(\/?)([a-z][a-z0-9]*)([^>]*)>$/i.exec(token)
    if (!tag) {
      if (!skipped && !token.startsWith('<') && token !== '') target().push(decode(token))
      continue
    }
    const closing = tag[1] === '/'
    const name = tag[2].toLowerCase()
    if (skipped) {
      if (closing && name === skipped) skipped = null
      continue
    }
    if (SKIPPED.has(name)) {
      if (!closing) skipped = name
      continue
    }
    const known = TAGS[name]
    if (!known) continue
    if (closing) {
      const at = open.findLastIndex((element) => element.tag === known)
      if (at >= 0) open.length = at
      continue
    }
    const element: RichElement = { tag: known, children: [] }
    if (known === 'a') element.href = safeHref(tag[3])
    target().push(element)
    if (known !== 'br') open.push(element)
  }
  return root
}

export function richTextContent(nodes: RichNode[]): string {
  return nodes.map((node) => (typeof node === 'string' ? node : richTextContent(node.children))).join('')
}

export function isRichTextEmpty(html: string): boolean {
  return html === '' || richTextContent(parseRichText(html)).trim() === ''
}
