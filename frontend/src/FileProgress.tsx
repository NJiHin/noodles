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
