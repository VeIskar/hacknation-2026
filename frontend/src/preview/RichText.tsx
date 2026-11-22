import type { ReactNode } from 'react'
import { parseRichText } from './richText.ts'
import type { RichNode } from './richText.ts'

function renderNode(node: RichNode, key: number, inline: boolean): ReactNode {
  if (typeof node === 'string') return node
  const children = node.children.map((child, i) => renderNode(child, i, inline))
  switch (node.tag) {
    case 'br':
      return <br key={key} />
    case 'strong':
      return <strong key={key}>{children}</strong>
    case 'em':
      return <em key={key}>{children}</em>
    case 'a':
      if (!node.href) return <span key={key}>{children}</span>
      return (
        <a key={key} href={node.href} target="_blank" rel="noopener noreferrer">
          {children}
          <span className="eu-sr"> (otwiera się w nowej karcie)</span>
        </a>
      )
    case 'ul':
    case 'ol':
    case 'li':
    case 'p': {
      // W etykiecie pola nie może stać akapit ani lista, więc zostaje sam tekst.
      if (inline) return <span key={key}>{children} </span>
      const Tag = node.tag
      return <Tag key={key}>{children}</Tag>
    }
  }
}

const BLOCKS = new Set(['p', 'ul', 'ol'])

/** Opis z JSON-a COI. `inline` daje treść bez akapitów, do wnętrza `<label>`. */
export function RichText({ html, inline = false }: { html: string; inline?: boolean }) {
  const nodes = parseRichText(html)
  if (inline) return <>{nodes.map((node, i) => renderNode(node, i, true))}</>
  // Tekst poza akapitem dostaje własny akapit. Akapit nie może trafić do środka akapitu.
  const blocks: ReactNode[] = []
  let loose: ReactNode[] = []
  const closeLoose = () => {
    if (loose.length > 0) blocks.push(<p key={`luz-${blocks.length}`}>{loose}</p>)
    loose = []
  }
  nodes.forEach((node, i) => {
    if (typeof node !== 'string' && BLOCKS.has(node.tag)) {
      closeLoose()
      blocks.push(renderNode(node, i, false))
    } else if (typeof node !== 'string' || node.trim() !== '' || loose.length > 0) {
      loose.push(renderNode(node, i, false))
    }
  })
  closeLoose()
  return <>{blocks}</>
}
