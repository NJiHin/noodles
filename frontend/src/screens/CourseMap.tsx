import { useEffect, useRef, useState } from 'react'
import { flushSync } from 'react-dom'
import { api, post } from '../api'
import { PageLink } from '../PageViewer'
import { RunProgress } from '../RunProgress'
import { VersionShell, fmtDate } from '../Shell'
import { DEPTHS, type Concept, type PassageRef, type RunStatus } from '../types'

type MapResp = {
  course_code: string; state: 'none' | 'draft' | 'reviewed'; reviewed_at: string | null
  run: RunStatus | null; concepts: Concept[]; passages: Record<string, PassageRef>
  id_diff: { previous_version: string; disappeared: string[]; new: string[] } | null
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

/** Applies a list change inside a view transition where the browser has one, so removed rows fade and the rest slide up. */
function animated(update: () => void) {
  if (!document.startViewTransition) return update()
  document.startViewTransition(() => flushSync(update))
}

/** Run extraction, watch it, then review the course map as a topic × week grid, correct topics in the side panel, and confirm. */
export function CourseMap({ vid }: { vid: string }) {
  const [m, setM] = useState<MapResp | null>(null)
  const [edit, setEdit] = useState<Concept[]>([])
  const [runId, setRunId] = useState<string | null>(null)
  const [err, setErr] = useState('')
  const [saved, setSaved] = useState(false)
  const [sel, setSel] = useState<string | null>(null)
  const [flash, setFlash] = useState<{ week: number; n: number } | null>(null)
  const [openWeeks, setOpenWeeks] = useState<Set<number> | null>(null) // null: open only when there is a single group
  const [closing, setClosing] = useState(false)
  const closeTimer = useRef<ReturnType<typeof setTimeout>>(undefined)

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

  // IDs against the previous reviewed version, kept live while editing: a rename shows as one gone and one new
  const prevIds = m?.id_diff && new Set([...m.id_diff.disappeared, ...m.concepts.map((c) => c.concept_id).filter((i) => !m.id_diff!.new.includes(i))])
  const editIds = new Set(edit.map((c) => c.concept_id))
  const gone = prevIds ? [...prevIds].filter((i) => !editIds.has(i)).sort() : []
  const added = prevIds ? [...editIds].filter((i) => !prevIds.has(i)).sort() : []


  // grid: topics grouped by the week they first appear; each row has a cell per week the topic is covered
  const weeks = [...new Set(edit.flatMap((c) => c.occurrences.map((o) => o.week)))].sort((a, b) => a - b)
  const first = (c: Concept) => Math.min(...c.occurrences.map((o) => o.week))
  const groups = [...new Set(edit.map(first))].sort((a, b) => a - b).map((w) => ({
    week: w, topics: edit.filter((c) => first(c) === w).sort((a, b) => a.name.localeCompare(b.name)),
  }))
  const order = groups.flatMap((g) => g.topics)
  const isOpen = (w: number) => openWeeks?.has(w) ?? groups.length === 1
  const c = edit.find((x) => x.concept_id === sel)

  const before = new Map(m?.concepts.map((x) => [x.concept_id, JSON.stringify(x)]))
  const changes = edit.filter((x) => before.get(x.concept_id) !== JSON.stringify(x)).length + [...before.keys()].filter((i) => !editIds.has(i)).length

  const setC = (next: Concept) => setEdit(edit.map((x) => (x.concept_id === next.concept_id ? next : x)))
  const toggle = (w: number) => setOpenWeeks(new Set(isOpen(w) ? [...groups.map((g) => g.week).filter((x) => x !== w && isOpen(x))] : [...groups.map((g) => g.week).filter(isOpen), w]))

  function open(t: Concept, week: number | null) {
    clearTimeout(closeTimer.current); setClosing(false)
    if (!isOpen(first(t))) toggle(first(t))
    setSel(t.concept_id)
    setFlash(week === null ? null : { week, n: (flash?.n ?? 0) + 1 })
  }
  function close() {
    setClosing(true)
    closeTimer.current = setTimeout(() => { setSel(null); setClosing(false) }, 150) // let the exit transition play
  }

  // ↑/↓ move between topics while the panel is open, Esc closes it; typing in a field or an open page viewer wins
  useEffect(() => {
    if (!sel) return
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).closest('input, select, textarea') || document.querySelector('dialog[open]')) return
      if (e.key === 'Escape') close()
      if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
      e.preventDefault()
      const next = order[order.findIndex((x) => x.concept_id === sel) + (e.key === 'ArrowDown' ? 1 : -1)]
      if (next) open(next, null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })
  useEffect(() => { document.querySelector('.mx-row.sel')?.scrollIntoView({ block: 'nearest' }) }, [sel])
  useEffect(() => { document.querySelector('.ed-wk.flash')?.scrollIntoView({ block: 'nearest' }) }, [flash])

  return (
    <VersionShell vid={vid} on="Course map">
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
              {saved && <span className="v ok pop">Saved</span>}
              <button className="btn" onClick={start}>{m.state === 'none' ? 'Build course map' : 'Rebuild'}</button>
              {m.state !== 'none' && (
                <button className="btn primary" disabled={m.state === 'reviewed' && !changes} onClick={confirm}>
                  Confirm map{changes > 0 && ` · ${changes} change${changes === 1 ? '' : 's'}`}
                </button>
              )}
            </div>
          </section>
        )}
        {err && <p className="err">{err}</p>}

        {m && !runId && prevIds && edit.length > 0 && (gone.length > 0 || added.length > 0) && (
          <section className="panel">
            <h2>Topic IDs since the previous version</h2>
            <p className="hint">A renamed topic shows up as one disappeared and one new ID. If a new ID is the same topic as one that disappeared, give it the old ID so changes are tracked across versions.</p>
            <div className="id-diff">
              <div><b>Disappeared</b>{gone.length ? gone.map((i) => <span key={i} className="chip">{i}</span>) : <span className="muted">none</span>}</div>
              <div><b>New</b>{added.length ? added.map((i) => (
                <span key={i} className="chip">{i}
                  {gone.length > 0 && (
                    <select aria-label={`Same topic as for ${i}`} value="" onChange={(e) => setEdit(edit.map((x) => (x.concept_id === i ? { ...x, concept_id: e.target.value } : x)))}>
                      <option value="">Same topic as…</option>
                      {gone.map((g) => <option key={g} value={g}>{g}</option>)}
                    </select>
                  )}
                </span>
              )) : <span className="muted">none</span>}</div>
            </div>
          </section>
        )}

        {m && !runId && edit.length > 0 && (
          <div className="cm-split">
            <section className="panel mx" style={{ '--weeks': weeks.length } as React.CSSProperties}>
              <div className="mx-top"><b>Topics by week</b>
                <div className="legend">{DEPTHS.map((d, i) => <span key={d}><i className={`sw d${i}`} />{label(d)}</span>)}</div>
              </div>
              <div className="mx-row mx-head"><span />{weeks.map((w) => <span key={w}>W{w}</span>)}</div>
              {groups.map((g) => (
                <div key={g.week}>
                  <button className={`mx-row mx-band ${isOpen(g.week) ? 'open' : ''}`} aria-expanded={isOpen(g.week)} onClick={() => toggle(g.week)}>
                    <span className="nm"><span className="chev">›</span>Introduced in week {g.week}<small>{g.topics.length} topic{g.topics.length === 1 ? '' : 's'}</small></span>
                    {weeks.map((w) => {
                      const n = g.topics.filter((t) => t.occurrences.some((o) => o.week === w)).length
                      return <span key={w} className="cnt">{n || ''}</span>
                    })}
                  </button>
                  <div className={`mx-body ${isOpen(g.week) ? 'open' : ''}`} inert={!isOpen(g.week)}>
                    <div>
                      {g.topics.map((t) => (
                        <div key={t.concept_id} className={`mx-row ${t.concept_id === sel ? 'sel' : ''}`} onClick={() => open(t, null)}
                          style={{ viewTransitionName: 'cm-' + t.concept_id.replace(/[^\w-]/g, '-') }}>
                          <button className="nm" title={t.name}>{t.name}</button>
                          {weeks.map((w) => {
                            const o = t.occurrences.find((x) => x.week === w)
                            return o
                              ? <button key={w} className={`c d${DEPTHS.indexOf(o.depth)}`} aria-label={`${t.name}, week ${w}: ${label(o.depth)}`}
                                  title={`Week ${w}: ${label(o.depth)} · ${o.evidence.length} page${o.evidence.length === 1 ? '' : 's'}`}
                                  onClick={(e) => { e.stopPropagation(); open(t, w) }} />
                              : <span key={w} />
                          })}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </section>

            {c ? (
              <aside className={`panel cm-side cm-ed ${closing ? 'out' : ''}`} key="ed" aria-label={`Edit ${c.name}`}>
                <div className="ed-head"><b>{c.name || c.concept_id}</b><small>Week{c.occurrences.length === 1 ? '' : 's'} {c.occurrences.map((o) => o.week).join(', ')}</small>
                  <button className="btn x" onClick={close}>Close</button></div>
                <label className="ed-f">Name<input className="topic-name" aria-label={`Name of ${c.concept_id}`} value={c.name} onChange={(e) => setC({ ...c, name: e.target.value })} /></label>
                <label className="ed-f">Also called<input aria-label={`Aliases of ${c.concept_id}`} value={c.aliases.join(', ')} placeholder="Other names, comma separated"
                  onChange={(e) => setC({ ...c, aliases: e.target.value.split(',').map((a) => a.trim()).filter(Boolean) })} /></label>
                {c.description && <p className="desc">{c.description}</p>}
                <div className="ed-f">Weeks
                  {c.occurrences.map((o, oi) => (
                    <div className={`ed-wk ${flash?.week === o.week ? 'flash' : ''}`} key={flash?.week === o.week ? `${o.week}-${flash.n}` : o.week}>
                      <span className="wk">Week {o.week}</span>
                      <select aria-label={`Depth of ${c.concept_id} in week ${o.week}`} value={o.depth}
                        onChange={(e) => setC({ ...c, occurrences: c.occurrences.map((x, k) => (k === oi ? { ...x, depth: e.target.value as Concept['occurrences'][0]['depth'] } : x)) })}>
                        {DEPTHS.map((d) => <option key={d} value={d}>{label(d)}</option>)}
                      </select>
                      <span className="ev">
                        {o.evidence.map((pid) => {
                          const p = m.passages[pid]
                          return (
                            <span className={`chip ${p ? '' : 'missing'}`} key={pid}>
                              {p ? <PageLink vid={vid} slug={p.slug} page={p.page}>{p.slug} p{p.page}</PageLink>
                                : <span title="No such passage in this version">{pid} (not found)</span>}
                              <button aria-label={`Remove ${pid} from ${c.concept_id}`} onClick={() => setC({
                                ...c, occurrences: c.occurrences.map((x, k) => (k === oi ? { ...x, evidence: x.evidence.filter((e) => e !== pid) } : x)),
                              })}>×</button>
                            </span>
                          )
                        })}
                      </span>
                    </div>
                  ))}
                </div>
                <div className="ed-foot">
                  <select aria-label={`Merge ${c.concept_id} into`} value="" onChange={(e) => {
                    const into = e.target.value
                    animated(() => { setEdit(edit.flatMap((x) => (x === c ? [] : x.concept_id === into ? [merge(x, c)] : [x]))); setSel(into) })
                  }}>
                    <option value="">Merge into…</option>
                    {edit.filter((x) => x !== c).map((x) => <option key={x.concept_id} value={x.concept_id}>{x.name}</option>)}
                  </select>
                  <button className="btn danger" onClick={() => animated(() => { setEdit(edit.filter((x) => x !== c)); setSel(null) })}>Delete topic</button>
                </div>
                <div className="ed-id">{c.concept_id}</div>
              </aside>
            ) : (
              <aside className="panel cm-side cm-hint" key="hint">
                <p className="muted">Click a topic to edit it, or a week's cell to jump to that week. ↑ and ↓ move between topics.</p>
              </aside>
            )}
          </div>
        )}
      </main>
    </VersionShell>
  )
}
