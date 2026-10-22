import katex from 'katex'
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
