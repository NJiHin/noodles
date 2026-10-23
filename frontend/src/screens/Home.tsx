import { useEffect, useState } from 'react'
import { api, post } from '../api'
import { animated, vtName } from '../animated'
import { ConfirmDialog } from '../ConfirmDialog'
import { WeekTable, unconfirmedWeeks, type Upload } from '../FileProgress'
import { Shell, fmtDate } from '../Shell'
import { go } from '../useHash'

type Course = { code: string; versions: { id: string; created_at: string; map_reviewed_at: string | null }[] }

/** Upload a course's files, confirm each file's week, then open the materials. Files are added later on Materials. */
export function Home() {
  const [courses, setCourses] = useState<Course[]>([])
  const [code, setCode] = useState('')
  const [up, setUp] = useState<Upload | null>(null)
  const [weeks, setWeeks] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [deleting, setDeleting] = useState<Course | null>(null)

  const loadCourses = () => api<Course[]>('/courses').then(setCourses).catch((e) => setErr(e.message))
  useEffect(() => { loadCourses() }, [])

  async function onUpload(files: FileList | null) {
    if (!files?.length) return
    const fd = new FormData()
    for (const f of Array.from(files)) fd.append('files', f)
    setErr(''); setBusy(true)
    try {
      const u = await api<Upload>(`/courses/${code}/uploads`, { method: 'POST', body: fd })
      setUp(u)
      setWeeks(Object.fromEntries(u.files.map((f) => [f.filename, f.week_guess?.toString() ?? ''])))
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }

  function startOver() { setUp(null) }

  async function onConfirm() {
    setErr(''); setBusy(true)
    try {
      const w = Object.fromEntries(Object.entries(weeks).map(([k, v]) => [k, Number(v)]))
      const { version_id } = await post<{ version_id: string }>(`/courses/${code}/versions`, { upload_id: up!.upload_id, weeks: w })
      go(`/v/${version_id}/materials`)
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }

  const unconfirmed = up ? unconfirmedWeeks(up, weeks) : 0

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
            <ul className="list-plain courses">
              {courses.flatMap((c) => c.versions.map((v, i) => (
                <li key={v.id} style={{ viewTransitionName: vtName('v', v.id) }}>
                  <a className="q" href={`#/v/${v.id}/materials`}>{c.code}</a>
                  <small>Uploaded {fmtDate(v.created_at)} · {v.id}</small>
                  {i === 0 && <button className="del-icon" aria-label={`Delete course ${c.code}`} title="Delete course" disabled={busy || !!up} onClick={() => setDeleting(c)}>
                    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M2.5 4h11M6 4V2.5h4V4M4 4l.7 9.5h6.6L12 4M6.8 6.5v4.5M9.2 6.5v4.5"
                      fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" /></svg></button>}
                </li>
              )))}
            </ul>
            {deleting && (
              <ConfirmDialog title={`Delete ${deleting.code}?`} action="Delete course" typeToConfirm={deleting.code} onClose={() => setDeleting(null)}
                onConfirm={() => api(`/courses/${deleting.code}`, { method: 'DELETE' }).then(() => {
                  const gone = deleting.code
                  animated(() => setCourses((cs) => cs.filter((c) => c.code !== gone)))
                  return loadCourses()
                })}>
                This deletes {deleting.code} and {deleting.versions.length === 1 ? 'its version' : `all ${deleting.versions.length} of its versions`}: the files
                and page text, course map, assessments and test-drive results. It can't be undone.
              </ConfirmDialog>
            )}
          </section>
        )}

        <section className="panel">
          <h2>New upload</h2>
          <p className="hint">Select all of the course's files in one upload (you can pick several at once). Missed one? Add it from the course's Materials page. Legacy .ppt and .doc files must be re-saved as .pptx or .docx first.</p>
          <div className="row-form">
            <label className="field">Course code
              <input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="CS1010" disabled={!!up} />
            </label>
            <label className="field">Files
              <input type="file" multiple accept=".pdf,.pptx,.docx,.ppt,.doc" disabled={!code || busy || !!up}
                onChange={(e) => onUpload(e.target.files)} />
            </label>
          </div>

          {up && (
            <>
              <WeekTable up={up} weeks={weeks} setWeeks={setWeeks} busy={busy} replaces={{}} />
              <div className="row-form">
                <button className="btn primary" disabled={busy || unconfirmed > 0} onClick={onConfirm}>
                  {busy ? 'Reading files…' : 'Confirm weeks'}
                </button>
                <button className="btn" disabled={busy} onClick={startOver}>Start over</button>
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

