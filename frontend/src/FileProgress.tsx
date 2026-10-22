import { useEffect, useState } from 'react'
import { api } from './api'

export type Progress = Record<string, { done: number; total: number }>  // per filename

/** Polls /progress/{key} every second while key is set: each file's flagged pages transcribed so far. */
export function useProgress(key: string | null) {
  const [prog, setProg] = useState<Progress | null>(null)
  useEffect(() => {
    if (!key) { setProg(null); return }
    let stop = false
    const tick = async () => {
      const p = await api<Progress>(`/progress/${key}`).catch(() => null)
      if (stop) return
      if (p) setProg(p)
      setTimeout(tick, 1000)
    }
    tick()
    return () => { stop = true }
  }, [key])
  return prog
}

/** Files are read in order, so the first unfinished one is the one being read. */
export const activeFile = (names: string[], prog: Progress | null) =>
  names.find((n) => { const p = prog?.[n]; return p && p.done < p.total })

/** Pages transcribed out of a file's flagged pages, with a spinner on the file being read (and on all while parsing). */
export function FileStatus({ p, active }: { p?: { done: number; total: number }; active: boolean }) {
  if (!p) return <span className="st on"><span className="spin" role="status" aria-label="Reading" /></span>
  if (p.total === 0) return <span className="st" title="No pages need transcribing">–</span>
  return <span className={active ? 'st on' : 'st'}><span className="spin" aria-hidden="true" />{p.done}/{p.total}</span>
}

export type Upload = { upload_id: string; files: { filename: string; week_guess: number | null }[] }

/** Each uploaded file with its week to confirm, and its reading progress while `busy`. `replaces` names files already
 * in the version (filename -> page count), which a same-name upload replaces. */
export function WeekTable({ up, weeks, setWeeks, busy, replaces }: {
  up: Upload; weeks: Record<string, string>; setWeeks: (w: Record<string, string>) => void; busy: boolean
  replaces: Record<string, number>
}) {
  const prog = useProgress(busy ? up.upload_id : null)
  const active = activeFile(up.files.map((f) => f.filename), prog)
  return (
    <table className="t">
      <thead><tr><th>File</th><th style={{ width: 110 }} /><th style={{ width: 140 }}>Week</th></tr></thead>
      <tbody>
        {up.files.map((f) => (
          <tr key={f.filename}>
            <td>{f.filename}
              {f.filename in replaces ? <span className="rep"> · replaces {f.filename} ({replaces[f.filename]} pages and any corrections on them)</span>
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
  )
}

export const unconfirmedWeeks = (up: Upload, weeks: Record<string, string>) => up.files.filter((f) => !(Number(weeks[f.filename]) >= 1)).length
