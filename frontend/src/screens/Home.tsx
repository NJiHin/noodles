import { useEffect, useRef, useState } from 'react'
import { api, post } from '../api'
import { ConfirmDialog } from '../ConfirmDialog'
import { FileStatus, activeFile, useProgress } from '../FileProgress'
import { Shell, fmtDate } from '../Shell'
import { go } from '../useHash'

type Course = { code: string; versions: { id: string; created_at: string; map_reviewed_at: string | null }[] }
type Upload = { upload_id: string; files: { filename: string; week_guess: number | null }[] }
type Target = { code: string; vid: string; created_at: string; files: Record<string, { week: number; pages: number }> }

/** Upload a course's files, or add files to a course's latest version; confirm each file's week, then open the materials. */
export function Home() {
  const [courses, setCourses] = useState<Course[]>([])
  const [code, setCode] = useState('')
  const [up, setUp] = useState<Upload | null>(null)
  const [weeks, setWeeks] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [target, setTarget] = useState<Target | null>(null)  // set while adding files to an existing version
  const [deleting, setDeleting] = useState<Course | null>(null)
  const addInput = useRef<HTMLInputElement>(null)

  const loadCourses = () => api<Course[]>('/courses').then(setCourses).catch((e) => setErr(e.message))
  useEffect(() => { loadCourses() }, [])

  async function onUpload(files: FileList | null, into: Target | null = null) {
    if (!files?.length) return
    const fd = new FormData()
    for (const f of Array.from(files)) fd.append('files', f)
    setErr(''); setBusy(true)
    try {
      const u = await api<Upload>(`/courses/${into?.code ?? code}/uploads`, { method: 'POST', body: fd })
      setUp(u); setTarget(into)
      // a file replacing one in the course starts with that file's week
      setWeeks(Object.fromEntries(u.files.map((f) => [f.filename, (into?.files[f.filename]?.week ?? f.week_guess)?.toString() ?? ''])))
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }

  async function startAdd(c: Course) {
    const v = c.versions[0]
    setErr('')
    try {
      const vf = await api<{ files: { filename: string; week: number; pages: unknown[] }[] }>(`/versions/${v.id}/files`)
      const t = { code: c.code, vid: v.id, created_at: v.created_at, files: Object.fromEntries(vf.files.map((f) => [f.filename, { week: f.week, pages: f.pages.length }])) }
      const input = addInput.current!
      input.onchange = () => { onUpload(input.files, t); input.value = '' }
      input.click()
    } catch (e) { setErr((e as Error).message) }
  }

  function startOver() { setUp(null); setTarget(null) }

  async function onConfirm() {
    setErr(''); setBusy(true)
    try {
      const w = Object.fromEntries(Object.entries(weeks).map(([k, v]) => [k, Number(v)]))
      const body = { upload_id: up!.upload_id, weeks: w }
      const { version_id } = target ? await post<{ version_id: string }>(`/versions/${target.vid}/files`, body)
        : await post<{ version_id: string }>(`/courses/${code}/versions`, body)
      go(`/v/${version_id}/materials`)
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }

  // the confirm request runs until every page is read; its progress is polled separately
  const prog = useProgress(busy && up ? up.upload_id : null)
  const active = activeFile(up?.files.map((f) => f.filename) ?? [], prog)
  const unconfirmed = up ? up.files.filter((f) => !(Number(weeks[f.filename]) >= 1)).length : 0

  return (
    <Shell course="Noodles" sub="Test-drive your course" nav={[{ label: 'Courses', href: '#/', on: true }]}>
      <main className="page">
        <div className="page-head">
          <h1>Courses</h1>
          <p>Upload a course's weekly files (.pdf, .pptx, .docx), confirm the week of each, and browse what was read.</p>
        </div>

        {courses.length > 0 && (
          <section className="panel">
            <h2>Versions</h2>
            <ul className="list-plain">
              {courses.flatMap((c) => c.versions.map((v, i) => (
                <li key={v.id}>
                  <a className="q" href={`#/v/${v.id}/materials`}>{c.code}</a>
                  <small>Uploaded {fmtDate(v.created_at)} · {v.id}</small>
                  {i === 0 && <button className="btn add" disabled={busy || !!up} onClick={() => startAdd(c)}>Add files</button>}
                  {i === 0 && <button className="btn sm danger" disabled={busy || !!up} onClick={() => setDeleting(c)}>Delete course</button>}
                </li>
              )))}
            </ul>
            {deleting && (
              <ConfirmDialog title={`Delete ${deleting.code}?`} action="Delete course" typeToConfirm={deleting.code} onClose={() => setDeleting(null)}
                onConfirm={() => api(`/courses/${deleting.code}`, { method: 'DELETE' }).then(loadCourses)}>
                This deletes {deleting.code} and {deleting.versions.length === 1 ? 'its version' : `all ${deleting.versions.length} of its versions`}: the files
                and page text, course map, assessments and test-drive results. It can't be undone.
              </ConfirmDialog>
            )}
            <input ref={addInput} type="file" multiple accept=".pdf,.pptx,.docx,.ppt,.doc" hidden aria-label="Files to add" />
          </section>
        )}

        <section className="panel">
          {target ? <>
            <h2>Add files to {target.code}</h2>
            <p className="hint">Added to the version of {fmtDate(target.created_at)} · {target.vid}. Confirm each file's week. A file with the same name as one already in the course replaces it.</p>
          </> : <>
            <h2>New upload</h2>
            <p className="hint">Select all of the course's files in one upload (you can pick several at once). Missed one? Use Add files on the course above. Legacy .ppt and .doc files must be re-saved as .pptx or .docx first.</p>
          </>}
          {!target && <div className="row-form">
            <label className="field">Course code
              <input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="CS1010" disabled={!!up} />
            </label>
            <label className="field">Files
              <input type="file" multiple accept=".pdf,.pptx,.docx,.ppt,.doc" disabled={!code || busy || !!up}
                onChange={(e) => onUpload(e.target.files)} />
            </label>
          </div>}

          {up && (
            <>
              <table className="t">
                <thead><tr><th>File</th><th style={{ width: 110 }} /><th style={{ width: 140 }}>Week</th></tr></thead>
                <tbody>
                  {up.files.map((f) => (
                    <tr key={f.filename}>
                      <td>{f.filename}
                        {target?.files[f.filename] ? <span className="rep"> · replaces {f.filename} ({target.files[f.filename].pages} pages and any corrections on them)</span>
                          : f.week_guess === null && <span className="muted"> · no week in the name, pick one</span>}</td>
                      <td>{busy && <FileStatus p={prog?.[f.filename]} active={f.filename === active} />}</td>
                      <td>
                        <input type="number" min={1} aria-label={`Week for ${f.filename}`} value={weeks[f.filename]}
                          onChange={(e) => setWeeks({ ...weeks, [f.filename]: e.target.value })} style={{ width: 90 }} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="row-form">
                <button className="btn primary" disabled={busy || unconfirmed > 0} onClick={onConfirm}>
                  {busy ? 'Reading files…' : target ? 'Add to course' : 'Confirm weeks'}
                </button>
                <button className="btn" disabled={busy} onClick={startOver}>{target ? 'Cancel' : 'Start over'}</button>
                {unconfirmed > 0 && <span className="muted">{unconfirmed === 1 ? '1 file still needs' : `${unconfirmed} files still need`} a week</span>}
              </div>
            </>
          )}
          {err && <p className="err">{err}</p>}
        </section>
      </main>
    </Shell>
  )
}

