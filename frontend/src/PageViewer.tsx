import { useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { api, pageImg, pdfHref } from './api'
import { Md, Tex } from './Tex'

export type Page = { passage_id: string; page: number; text: string; origin: 'parser' | 'vlm' }
type File = { slug: string; filename: string; pages: Page[] }

/** A link to a source page that opens it in the page viewer; ctrl/cmd-click still opens the PDF in a new tab. */
export function PageLink({ vid, slug, page, children }: { vid: string; slug: string; page: number; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <a href={pdfHref(vid, slug, page)} target="_blank" rel="noreferrer"
        onClick={(e) => { if (!e.metaKey && !e.ctrlKey) { e.preventDefault(); setOpen(true) } }}>{children}</a>
      {/* portal: links sit inside styled rows (chips, warnings) whose styles would leak into the dialog */}
      {open && createPortal(<PageViewer vid={vid} slug={slug} page={page} onClose={() => setOpen(false)} />, document.body)}
    </>
  )
}

/** Modal: the page's text (editable) on the left, the page image the VLM saw on the right. */
export function PageViewer({ vid, slug, page: start, onSaved, onClose }: { vid: string; slug: string; page: number; onSaved?: (p: Page) => void; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  const [n, setN] = useState(start)
  const [file, setFile] = useState<File | null>(null)
  const [draft, setDraft] = useState<string | null>(null)
  const [formatted, setFormatted] = useState(false)  // shows the Markdown rendered; editing is always on the raw text
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [saved, setSaved] = useState(false)
  const closeTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  useEffect(() => { ref.current?.showModal(); return () => clearTimeout(closeTimer.current) }, [])
  useEffect(() => {
    api<{ files: File[] }>(`/versions/${vid}/files`).then((v) => setFile(v.files.find((f) => f.slug === slug) ?? null)).catch((e) => setErr(e.message))
  }, [vid, slug])
  const page = file?.pages.find((p) => p.page === n)
  const at = file ? file.pages.findIndex((p) => p.page === n) : -1
  const prev = file?.pages[at - 1]?.page
  const next = file?.pages[at + 1]?.page
  function go(to: number | undefined) {  // blocked while editing so an unsaved draft isn't lost
    if (to === undefined || draft !== null) return
    setN(to); setSaved(false); setErr('')
  }

  async function save() {
    setErr(''); setBusy(true)
    try {
      await api(`/versions/${vid}/passages/${page!.passage_id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: draft }) })
      const next = { ...page!, text: draft! }
      setFile((f) => f && { ...f, pages: f.pages.map((p) => (p.page === n ? next : p)) })
      onSaved?.(next)
      setDraft(null); setSaved(true)
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }

  return (
    <dialog className="viewer" ref={ref} onClose={() => { closeTimer.current = setTimeout(onClose, 150) }}
      onKeyDown={(e) => { if (e.key === 'ArrowLeft') go(prev); else if (e.key === 'ArrowRight') go(next) }}>{/* unmount after the exit transition; a viewer replaced first never fires it */}
      <div className="viewer-head">
        <b>{file?.filename ?? slug}</b>
        <button className="btn sm" aria-label="Previous page" disabled={prev === undefined || draft !== null} onClick={() => go(prev)}>‹</button>
        <small>Page {n}{file && ` of ${file.pages.length}`}</small>
        <button className="btn sm" aria-label="Next page" disabled={next === undefined || draft !== null} onClick={() => go(next)}>›</button>
        {page?.origin === 'vlm' && <span className="v n">vlm</span>}
        <a className="btn" href={pdfHref(vid, slug, n)} target="_blank" rel="noreferrer">Open PDF</a>
        <button className="btn x" onClick={() => ref.current?.close()}>Close</button>
      </div>
      <div className="viewer-body">
        {!page ? (
          <div className="viewer-text">{err ? <span className="err">{err}</span> : <span className="muted">Loading…</span>}</div>
        ) : draft === null ? (
          <div className="viewer-text">
            <span className="src">{page.origin === 'vlm' ? 'Transcribed from the page image by the VLM' : 'Text from the PDF'}{saved && <span className="v ok pop">Saved</span>}<button className="btn" aria-pressed={formatted} onClick={() => setFormatted(!formatted)}>{formatted ? 'Raw' : 'Formatted'}</button><button className="btn" onClick={() => { setSaved(false); setDraft(page.text) }}>Edit</button></span>
            {page.text ? (formatted ? <Md>{page.text}</Md> : <Tex>{page.text}</Tex>) : <span className="muted">No text on this page.</span>}
          </div>
        ) : (
          <div className="viewer-text editing">
            <span className="src">Editing the transcription</span>
            <textarea aria-label="Transcription" value={draft} onChange={(e) => setDraft(e.target.value)} autoFocus />
            <div className="edit-bar">
              <button className="btn primary" disabled={busy} onClick={save}>{busy ? 'Saving…' : 'Save'}</button>
              <button className="btn" disabled={busy} onClick={() => setDraft(null)}>Cancel</button>
              {err ? <span className="err">{err}</span> : <span className="muted">Saved text replaces this page for search and citations.</span>}
            </div>
          </div>
        )}
        <div className="viewer-img"><img src={pageImg(vid, slug, n)} alt={`Page ${n} of ${file?.filename ?? slug}`} /></div>
      </div>
    </dialog>
  )
}
