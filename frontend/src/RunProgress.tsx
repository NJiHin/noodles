import { useEffect, useState } from 'react'
import { api } from './api'
import type { RunStatus } from './types'

/** Polls a background run and shows its stage; calls onEnd once it stops running. */
export function RunProgress({ runId, onEnd }: { runId: string; onEnd: (r: RunStatus) => void }) {
  const [r, setR] = useState<RunStatus | null>(null)
  useEffect(() => {
    let stop = false
    const tick = async () => {
      const s = await api<RunStatus>(`/runs/${runId}`)
      if (stop) return
      setR(s)
      if (s.status === 'running') setTimeout(tick, 1000)
      else onEnd(s)
    }
    tick()
    return () => { stop = true }
  }, [runId]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!r) return <p className="muted">Starting…</p>
  const pct = r.total ? Math.round((100 * r.done) / r.total) : 0
  return (
    <div className="progress">
      <div className="progress-head"><b>{r.stage || 'Working'}</b><span className="muted">{r.done}{r.total ? ` of ${r.total}` : ''} calls</span></div>
      <div className="progress-bar"><span style={{ width: `${pct}%` }} /></div>
    </div>
  )
}
