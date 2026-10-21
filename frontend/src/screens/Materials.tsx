import { useEffect, useState } from 'react'
import { api } from '../api'
import { PageViewer, type Page } from '../PageViewer'
import { VersionShell } from '../Shell'

type File = { slug: string; filename: string; week: number; pages: Page[] }
type Version = { version_id: string; course_code: string; created_at: string; files: File[] }

const vlmCount = (f: File) => f.pages.filter((p) => p.origin === 'vlm').length
/** First non-empty line without markdown markers, as the row's label (usually the slide title). */
const firstLine = (t: string) => t.split('\n').map((l) => l.replace(/^[#>*\-\s]+/, '').trim()).find(Boolean) ?? ''

/** Every file and page of a version, grouped by week; a page opens next to its image, and its text can be corrected. */
export function Materials({ vid }: { vid: string }) {
  const [v, setV] = useState<Version | null>(null)
  const [err, setErr] = useState('')
  const [open, setOpen] = useState<{ file: File; page: Page } | null>(null)
  useEffect(() => { api<Version>(`/versions/${vid}/files`).then(setV).catch((e) => setErr(e.message)) }, [vid])

  const weeks = v ? [...new Set(v.files.map((f) => f.week))] : []
  const pages = v ? v.files.reduce((n, f) => n + f.pages.length, 0) : 0

  function saved(page: Page) {
    setV((cur) => cur && { ...cur, files: cur.files.map((f) => ({ ...f, pages: f.pages.map((p) => (p.passage_id === page.passage_id ? page : p)) })) })
    setOpen((cur) => cur && { ...cur, page })
  }

  return (
    <VersionShell vid={vid} on="Materials">
      <main className="page">
        <div className="page-head">
          <div className="meta">Version {vid}</div>
          <h1>Materials</h1>
          <p>{v ? `${v.files.length} files, ${pages} pages. One passage per page; click a page to see it next to its text.` : err || 'Loading…'}</p>
        </div>
        {v && (
          <section className="panel">
            {weeks.map((w) => (
              <div key={w}>
                <div className="week-h">Week {w}</div>
                {v.files.filter((f) => f.week === w).map((f) => (
                  <details className="file" key={f.slug}>
                    <summary><b>{f.filename}</b><small>{f.pages.length} page{f.pages.length === 1 ? '' : 's'}</small>{vlmCount(f) > 0 && <small>· {vlmCount(f)} transcribed (vlm)</small>}</summary>
                    {f.pages.map((p) => (
                      <button className="pg-row" key={p.passage_id} onClick={() => setOpen({ file: f, page: p })}>
                        <span className="n">Page {p.page}</span>
                        <span>{p.origin === 'vlm' && <span className="v n" title="Transcribed from the page image by the VLM">vlm</span>}</span>
                        <span className="first">{firstLine(p.text) || <span className="muted">No text on this page.</span>}</span>
                      </button>
                    ))}
                  </details>
                ))}
              </div>
            ))}
          </section>
        )}
        {open && <PageViewer key={open.page.passage_id} vid={vid} slug={open.file.slug} page={open.page.page} onSaved={saved} onClose={() => setOpen(null)} />}
      </main>
    </VersionShell>
  )
}
