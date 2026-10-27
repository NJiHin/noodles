import { useEffect, useRef, useState } from 'react'
import { api, post } from '../api'
import { animated, vtName } from '../animated'
import { WeekTable, unconfirmedWeeks, type Upload } from '../FileProgress'
import { ConfirmDialog } from '../ConfirmDialog'
import { useSticky } from '../sticky'
import { PageViewer, type Page } from '../PageViewer'
import { AddedNotice, VersionShell } from '../Shell'

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
  const [deleting, setDeleting] = useState<File | null>(null)
  const [changes, setChanges] = useState(0)  // remounts the notice after files are added or deleted
  const load = () => api<Version>(`/versions/${vid}/files`).then(setV).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [vid]) // eslint-disable-line react-hooks/exhaustive-deps
  const reload = () => load().then(() => setChanges((n) => n + 1))

  // adding files: only to the course's latest version (sys-design Stage 0, "Adding files to a course")
  const [latest, setLatest] = useState(false)
  const [up, setUp] = useSticky<Upload | null>(`materials:${vid}:up`, null)  // sticky: a read survives switching tabs
  const [weeksIn, setWeeksIn] = useSticky<Record<string, string>>(`materials:${vid}:weeks`, {})
  const [busy, setBusy] = useSticky(`materials:${vid}:busy`, false)
  const [addErr, setAddErr] = useSticky(`materials:${vid}:err`, '')
  const pick = useRef<HTMLInputElement>(null)
  useEffect(() => {
    if (v) api<{ code: string; versions: { id: string }[] }[]>('/courses')
      .then((cs) => setLatest(cs.find((c) => c.code === v.course_code)?.versions[0]?.id === vid)).catch(() => setLatest(false))
  }, [v?.course_code, vid]) // eslint-disable-line react-hooks/exhaustive-deps

  async function onPick(files: FileList | null) {
    if (!files?.length || !v) return
    const fd = new FormData()
    for (const f of Array.from(files)) fd.append('files', f)
    setAddErr(''); setBusy(true)
    try {
      const u = await api<Upload>(`/courses/${v.course_code}/uploads`, { method: 'POST', body: fd })
      setUp(u)  // a file replacing one in the version starts with that file's week
      setWeeksIn(Object.fromEntries(u.files.map((f) => [f.filename, (v.files.find((x) => x.filename === f.filename)?.week ?? f.week_guess)?.toString() ?? ''])))
    } catch (e) { setAddErr((e as Error).message) } finally { setBusy(false) }
  }

  async function addToCourse() {
    setAddErr(''); setBusy(true)
    try {
      await post(`/versions/${vid}/files`, { upload_id: up!.upload_id, weeks: Object.fromEntries(Object.entries(weeksIn).map(([k, w]) => [k, Number(w)])) })
      setUp(null); await reload()
    } catch (e) { setAddErr((e as Error).message) } finally { setBusy(false) }
  }

  const weeks = v ? [...new Set(v.files.map((f) => f.week))] : []
  const pages = v ? v.files.reduce((n, f) => n + f.pages.length, 0) : 0

  function saved(page: Page) {
    setV((cur) => cur && { ...cur, files: cur.files.map((f) => ({ ...f, pages: f.pages.map((p) => (p.passage_id === page.passage_id ? page : p)) })) })
  }

  return (
    <VersionShell vid={vid} on="Materials">
      <main className="page">
        <div className="page-head">
          <div className="meta">Version {vid}</div>
          <div className="head-row"><h1>Materials</h1>
            {latest && !up && <button className="btn" disabled={busy} onClick={() => pick.current?.click()}>Add files</button>}
            <input ref={pick} type="file" multiple accept=".pdf,.pptx,.docx,.ppt,.doc" hidden aria-label="Files to add"
              onChange={(e) => { onPick(e.target.files); e.target.value = '' }} /></div>
          <p>{v ? `${v.files.length} files, ${pages} pages. One passage per page; click a page to see it next to its text.` : err || 'Loading…'}</p>
        </div>
        <AddedNotice key={changes} vid={vid} screen="materials" />
        {up && v && (
          <section className="panel appear">
            <h2>Add files to {v.course_code}</h2>
            <p className="hint">Confirm each file's week. A file with the same name as one already here replaces it.</p>
            <WeekTable up={up} weeks={weeksIn} setWeeks={setWeeksIn} busy={busy} replaces={Object.fromEntries(v.files.map((f) => [f.filename, f.pages.length]))} />
            <div className="row-form">
              <button className="btn primary" disabled={busy || unconfirmedWeeks(up, weeksIn) > 0} onClick={addToCourse}>{busy ? 'Reading files…' : 'Add to course'}</button>
              <button className="btn" disabled={busy} onClick={() => setUp(null)}>Cancel</button>
            </div>
          </section>
        )}
        {addErr && <p className="err">{addErr}</p>}
        {v && (
          <section className="panel">
            {weeks.map((w) => (
              <div key={w}>
                <div className="week-h">Week {w}</div>
                {v.files.filter((f) => f.week === w).map((f) => (
                  <details className="file" key={f.slug} style={{ viewTransitionName: vtName('file', f.slug) }}>
                    <summary><b>{f.filename}</b><small>{f.pages.length} page{f.pages.length === 1 ? '' : 's'}</small>{vlmCount(f) > 0 && <small>· {vlmCount(f)} transcribed (vlm)</small>}
                      <button className="btn sm danger" disabled={v.files.length === 1} title={v.files.length === 1 ? "A version's last file can't be deleted" : undefined}
                        onClick={(e) => { e.preventDefault(); setDeleting(f) }}>Delete</button></summary>
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
        {deleting && (
          <ConfirmDialog title={`Delete ${deleting.filename}?`} action="Delete file" onClose={() => setDeleting(null)}
            onConfirm={() => api(`/versions/${vid}/files/${deleting.slug}`, { method: 'DELETE' }).then(() => {
            const gone = deleting.slug
            animated(() => setV((cur) => cur && { ...cur, files: cur.files.filter((f) => f.slug !== gone) }))
            return reload()
          })}>
            Its {deleting.pages.length} page{deleting.pages.length === 1 ? '' : 's'}, and any corrections on them, are removed from this version.
            The course map and test-drive results then show as outdated until you rebuild and rerun.
          </ConfirmDialog>
        )}
        {open && <PageViewer key={open.page.passage_id} vid={vid} slug={open.file.slug} page={open.page.page} onSaved={saved} onClose={() => setOpen(null)} />}
      </main>
    </VersionShell>
  )
}
