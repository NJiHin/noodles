export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, init)
  const body = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? r.statusText))
  return body as T
}

export const post = <T,>(path: string, json: unknown) =>
  api<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(json) })

/** Link to a source PDF at a page (sys-design Stage 0, step 7). */
export const pdfHref = (versionId: string, slug: string, page: number) => `/files/${versionId}/${slug}.pdf#page=${page}`

/** A source page rendered as the PNG the VLM saw. */
export const pageImg = (versionId: string, slug: string, page: number) => `/files/${versionId}/${slug}/pages/${page}.png`
