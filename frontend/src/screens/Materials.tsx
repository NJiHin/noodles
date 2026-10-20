import { useEffect, useState } from 'react'
import { api, pdfHref } from '../api'
import { Shell, fmtDate, versionNav } from '../Shell'

type Page = { passage_id: string; page: number; text: string; origin: 'parser' | 'vlm' }
type File = { slug: string; filename: string; week: number; pages: Page[] }
type Version = { version_id: string; course_code: string; created_at: string; files: File[] }

/** Every file and page of a version, grouped by week; each page opens its source PDF. */
export function Materials({ vid }: { vid: string }) {
  const [v, setV] = useState<Version | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => { api<Version>(`/versions/${vid}/files`).then(setV).catch((e) => setErr(e.message)) }, [vid])

  const weeks = v ? [...new Set(v.files.map((f) => f.week))] : []
  const pages = v ? v.files.reduce((n, f) => n + f.pages.length, 0) : 0

  return (
    <Shell course={v?.course_code ?? '…'} sub={v ? `Version of ${fmtDate(v.created_at)}` : ''} nav={versionNav(vid, 'Materials')}>
      <main className="page">
        <div className="page-head">
          <div className="meta">Version {vid}</div>
          <h1>Materials</h1>
          <p>{v ? `${v.files.length} files, ${pages} pages. One passage per page; each page opens its PDF.` : err || 'Loading…'}</p>
        </div>
        {v && (
          <section className="panel">
            {weeks.map((w) => (
              <div key={w}>
                <div className="week-h">Week {w}</div>
                {v.files.filter((f) => f.week === w).map((f) => (
                  <details className="file" key={f.slug}>
                    <summary><b>{f.filename}</b><small>{f.pages.length} page{f.pages.length === 1 ? '' : 's'}</small></summary>
                    {f.pages.map((p) => (
                      <div className="pg" key={p.passage_id}>
                        <a href={pdfHref(vid, f.slug, p.page)} target="_blank" rel="noreferrer">Page {p.page}</a>
                        <p>{p.text || <span className="muted">No text on this page.</span>}</p>
                      </div>
                    ))}
                  </details>
                ))}
              </div>
            ))}
          </section>
        )}
      </main>
    </Shell>
  )
}
