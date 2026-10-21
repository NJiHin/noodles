import { useEffect, useState } from 'react'
import { api, post } from '../api'
import { Shell, fmtDate } from '../Shell'
import { go } from '../useHash'

type Course = { code: string; versions: { id: string; created_at: string; map_reviewed_at: string | null }[] }
type Upload = { upload_id: string; files: { filename: string; week_guess: number | null }[] }
type Progress = Record<string, { done: number; total: number }>  // per filename

/** Upload a course's files, confirm each file's week, then open the materials. */
export function Home() {
  const [courses, setCourses] = useState<Course[]>([])
  const [code, setCode] = useState('')
  const [up, setUp] = useState<Upload | null>(null)
  const [weeks, setWeeks] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [prog, setProg] = useState<Progress | null>(null)

  useEffect(() => { api<Course[]>('/courses').then(setCourses).catch((e) => setErr(e.message)) }, [])

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

  async function onConfirm() {
    setErr(''); setBusy(true)
    let polling = true
    const poll = async () => {  // the confirm request runs until every page is read; its progress is a separate endpoint
      while (polling) {
        const p = await api<Progress>(`/courses/${code}/uploads/${up!.upload_id}/progress`).catch(() => null)
        if (polling && p) setProg(p)
        await new Promise((r) => setTimeout(r, 1000))
      }
    }
    poll()
    try {
      const w = Object.fromEntries(Object.entries(weeks).map(([k, v]) => [k, Number(v)]))
      const { version_id } = await post<{ version_id: string }>(`/courses/${code}/versions`, { upload_id: up!.upload_id, weeks: w })
      go(`/v/${version_id}/materials`)
    } catch (e) { setErr((e as Error).message) } finally { polling = false; setBusy(false); setProg(null) }
  }

  // files are read in upload order, so the first unfinished one is the one being read
  const active = up?.files.find((f) => { const p = prog?.[f.filename]; return p && p.done < p.total })?.filename
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
              {courses.flatMap((c) => c.versions.map((v) => (
                <li key={v.id}>
                  <a className="q" href={`#/v/${v.id}/materials`}>{c.code}</a>
                  <small>Uploaded {fmtDate(v.created_at)} · {v.id}</small>
                </li>
              )))}
            </ul>
          </section>
        )}

        <section className="panel">
          <h2>New upload</h2>
          <p className="hint">Legacy .ppt and .doc files must be re-saved as .pptx or .docx first.</p>
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
              <table className="t">
                <thead><tr><th>File</th><th style={{ width: 110 }} /><th style={{ width: 140 }}>Week</th></tr></thead>
                <tbody>
                  {up.files.map((f) => (
                    <tr key={f.filename}>
                      <td>{f.filename}{f.week_guess === null && <span className="muted"> · no week in the name, pick one</span>}</td>
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
                  {busy ? 'Reading files…' : 'Confirm weeks'}
                </button>
                <button className="btn" disabled={busy} onClick={() => setUp(null)}>Start over</button>
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

/** Pages transcribed out of a file's flagged pages, with a spinner on the file being read (and on all while parsing). */
function FileStatus({ p, active }: { p?: { done: number; total: number }; active: boolean }) {
  if (!p) return <span className="st on"><span className="spin" role="status" aria-label="Reading" /></span>
  if (p.total === 0) return <span className="st" title="No pages need transcribing">–</span>
  return <span className={active ? 'st on' : 'st'}><span className="spin" aria-hidden="true" />{p.done}/{p.total}</span>
}
