import katex from 'katex'
import { marked } from 'marked'
import 'katex/dist/katex.min.css'
import type { ReactNode } from 'react'

// \[..\] and $$..$$ display; \(..\) and $..$ inline. A $ pair must hug its content and not be followed by a digit,
// so prices like "$5 and $6" stay text.
const MATH = /\\\[([\s\S]+?)\\\]|\$\$([\s\S]+?)\$\$|\\\(([\s\S]+?)\\\)|\$(?=\S)([^$\n]+?)\$(?!\d)/g

/** Text with its LaTeX rendered by KaTeX; maths KaTeX can't parse is shown as written, in red. */
export function Tex({ children }: { children: string }) {
  const parts: ReactNode[] = []
  let last = 0
  for (const m of children.matchAll(MATH)) {
    if (m.index > last) parts.push(children.slice(last, m.index))
    const html = katex.renderToString(m[1] ?? m[2] ?? m[3] ?? m[4], { displayMode: m[1] !== undefined || m[2] !== undefined, throwOnError: false })
    parts.push(<span key={m.index} dangerouslySetInnerHTML={{ __html: html }} />)
    last = m.index + m[0].length
  }
  parts.push(children.slice(last))
  return <>{parts}</>
}

const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

/** Markdown (tables, headings, lists, bold) with its LaTeX rendered. Maths is set aside before parsing so Markdown can't
 * mangle it, and the text is HTML-escaped so a stray tag shows as text. inline: no block elements (for headings). */
export function Md({ children, inline = false }: { children: string; inline?: boolean }) {
  const maths: string[] = []
  const src = esc(children.replace(MATH, (_, d1, d2, i1, i2) => {
    maths.push(katex.renderToString(d1 ?? d2 ?? i1 ?? i2, { displayMode: d1 !== undefined || d2 !== undefined, throwOnError: false }))
    return `%%MATH${maths.length - 1}%%`
  }))
  const opts = { async: false as const, gfm: true, breaks: true }
  const html = (inline ? marked.parseInline(src, opts) : marked.parse(src, opts)).replace(/%%MATH(\d+)%%/g, (_, i) => maths[+i])
  return inline ? <span dangerouslySetInnerHTML={{ __html: html }} /> : <div className="md" dangerouslySetInnerHTML={{ __html: html }} />
}
