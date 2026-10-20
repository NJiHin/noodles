import { useEffect, useState } from 'react'
import { api, pdfHref, post } from '../api'
import { RunProgress } from '../RunProgress'
import { Shell, fmtDate, versionNav } from '../Shell'
import { DEPTHS, type Concept, type PassageRef, type RunStatus } from '../types'

type MapResp = {
  course_code: string; state: 'none' | 'draft' | 'reviewed'; reviewed_at: string | null
  run: RunStatus | null; concepts: Concept[]; passages: Record<string, PassageRef>
}

const label = (d: string) => d.replace('_', ' ')

/** Merge topic `from` into `into`: names become aliases, weeks combine (deeper depth, evidence union). */
function merge(into: Concept, from: Concept): Concept {
  const aliases = [...new Set([...into.aliases, from.name, ...from.aliases])].filter((a) => a !== into.name)
  const weeks = new Map(into.occurrences.map((o) => [o.week, { ...o, evidence: [...o.evidence] }]))
  for (const o of from.occurrences) {
    const w = weeks.get(o.week)
    if (!w) weeks.set(o.week, { ...o, evidence: [...o.evidence] })
    else {
      if (DEPTHS.indexOf(o.depth) > DEPTHS.indexOf(w.depth)) w.depth = o.depth
      w.evidence = [...new Set([...w.evidence, ...o.evidence])]
    }
  }
  return { ...into, aliases, occurrences: [...weeks.values()].sort((a, b) => a.week - b.week) }
}

/** Run extraction, watch it, then review and correct the course map before confirming it. */
export function CourseMap({ vid }: { vid: string }) {
  const [m, setM] = useState<MapResp | null>(null)
  const [edit, setEdit] = useState<Concept[]>([])
  const [runId, setRunId] = useState<string | null>(null)
  const [err, setErr] = useState('')
  const [saved, setSaved] = useState(false)

  const load = () => api<MapResp>(`/versions/${vid}/map`).then((r) => {
    setM(r); setEdit(r.concepts); setSaved(false)
    setRunId(r.run?.status === 'running' ? r.run.run_id : null)
  }).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [vid]) // eslint-disable-line react-hooks/exhaustive-deps

  async function start() {
    setErr('')
    try { setRunId((await post<{ run_id: string }>(`/versions/${vid}/map-runs`, {})).run_id) } catch (e) { setErr((e as Error).message) }
  }

  async function confirm() {
    setErr('')
    try {
      await api(`/versions/${vid}/map`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ concepts: edit }) })
      await load(); setSaved(true)
    } catch (e) { setErr((e as Error).message) }
  }

  const set = (i: number, c: Concept) => setEdit(edit.map((x, j) => (j === i ? c : x)))
  const dirty = m && JSON.stringify(edit) !== JSON.stringify(m.concepts)

  return (
    <Shell course={m?.course_code ?? '…'} sub={m?.reviewed_at ? `Map reviewed ${fmtDate(m.reviewed_at)}` : 'Map not reviewed'} nav={versionNav(vid, 'Course map')}>
      <main className="page">
        <div className="page-head">
          <div className="meta">Version {vid}</div>
          <h1>Course map</h1>
          <p>Topics found in each week's materials, merged across weeks. Correct anything wrong, then confirm: the test-drive uses only the confirmed map.</p>
        </div>

        {runId && (
          <section className="panel">
            <h2>Building the map</h2>
            <RunProgress runId={runId} onEnd={(r) => { if (r.status !== 'done') setErr(r.error || `Run ${r.status}`); load() }} />
          </section>
        )}

        {m && !runId && (
          <section className="panel map-bar">
            <div>
              <h2>{m.state === 'none' ? 'No map yet' : m.state === 'draft' ? `Draft: ${edit.length} topics` : `Confirmed: ${edit.length} topics`}</h2>
              <p className="hint">
                {m.state === 'none' ? 'One extractor per week, then one call that merges topics across weeks.'
                  : m.state === 'draft' ? 'Not used until you confirm it.' : `Confirmed ${fmtDate(m.reviewed_at!)}. Edits replace it when you confirm again.`}
              </p>
            </div>
            <div className="map-actions">
              {saved && <span className="v ok">Saved</span>}
              <button className="btn" onClick={start}>{m.state === 'none' ? 'Build course map' : 'Rebuild'}</button>
              {m.state !== 'none' && (
                <button className="btn primary" disabled={m.state === 'reviewed' && !dirty} onClick={confirm}>Confirm map</button>
              )}
            </div>
          </section>
        )}
        {err && <p className="err">{err}</p>}

        {m && !runId && edit.length > 0 && (
          <section className="panel">
            {edit.map((c, i) => (
              <div className="topic" key={c.concept_id}>
                <div className="topic-head">
                  <input className="topic-name" aria-label={`Name of ${c.concept_id}`} value={c.name} onChange={(e) => set(i, { ...c, name: e.target.value })} />
                  <span className="muted id">{c.concept_id}</span>
                  <select aria-label={`Merge ${c.concept_id} into`} value="" onChange={(e) => {
                    const j = edit.findIndex((x) => x.concept_id === e.target.value)
                    setEdit(edit.map((x, k) => (k === j ? merge(x, c) : x)).filter((_, k) => k !== i))
                  }}>
                    <option value="">Merge into…</option>
                    {edit.filter((x) => x !== c).map((x) => <option key={x.concept_id} value={x.concept_id}>{x.name}</option>)}
                  </select>
                  <button className="btn" onClick={() => setEdit(edit.filter((_, k) => k !== i))}>Delete</button>
                </div>
                <label className="aliases">Also called
                  <input aria-label={`Aliases of ${c.concept_id}`} value={c.aliases.join(', ')} placeholder="none"
                    onChange={(e) => set(i, { ...c, aliases: e.target.value.split(',').map((a) => a.trim()).filter(Boolean) })} />
                </label>
                {c.description && <p className="desc">{c.description}</p>}
                {c.occurrences.map((o, oi) => (
                  <div className="occ" key={o.week}>
                    <span className="wk">Week {o.week}</span>
                    <select aria-label={`Depth of ${c.concept_id} in week ${o.week}`} value={o.depth}
                      onChange={(e) => set(i, { ...c, occurrences: c.occurrences.map((x, k) => (k === oi ? { ...x, depth: e.target.value as Concept['occurrences'][0]['depth'] } : x)) })}>
                      {DEPTHS.map((d) => <option key={d} value={d}>{label(d)}</option>)}
                    </select>
                    <span className="ev">
                      {o.evidence.map((pid) => {
                        const p = m.passages[pid]
                        return (
                          <span className={`chip ${p ? '' : 'missing'}`} key={pid}>
                            {p ? <a href={pdfHref(vid, p.slug, p.page)} target="_blank" rel="noreferrer">{p.slug} p{p.page}</a>
                              : <span title="No such passage in this version">{pid} (not found)</span>}
                            <button aria-label={`Remove ${pid} from ${c.concept_id}`} onClick={() => set(i, {
                              ...c, occurrences: c.occurrences.map((x, k) => (k === oi ? { ...x, evidence: x.evidence.filter((e) => e !== pid) } : x)),
                            })}>×</button>
                          </span>
                        )
                      })}
                    </span>
                  </div>
                ))}
              </div>
            ))}
          </section>
        )}
      </main>
    </Shell>
  )
}
