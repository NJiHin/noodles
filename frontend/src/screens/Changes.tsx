import { useEffect, useState, type ReactNode } from 'react'
import { api } from '../api'
import { VersionShell, fmtDate } from '../Shell'
import type { Changes as C, FieldChange } from '../types'

const short = (id: string) => id.slice(id.lastIndexOf('-q') + 1).toUpperCase()
const FIELD: Record<FieldChange['field'], string> = {
  student_verdict: 'Student verdict', web_verdict: 'Web verdict', exposure: 'AI exposure', gap: 'Gap', recommendation: 'Recommendation',
}
const EXPOSURE: Record<string, string> = {
  ai_exposed: 'AI-exposed', course_specific: 'Depends on the course', neither_taught: 'Needs untaught knowledge',
  broken_or_gap: 'Broken question, or a gap', not_assessed: 'Not assessed',
}
const VCLS: Record<string, string> = { correct: 'ok', partial: 'part', incorrect: 'bad' }
const depth = (d: string | null) => (d ? d[0].toUpperCase() + d.slice(1).replace('_', ' ') : 'Not taught')

/** One side of a before -> after shift, styled as the c5 board does for its kind. */
function val(f: FieldChange, v: FieldChange['before'], old: boolean): ReactNode {
  const o = old ? ' old' : ''
  if (f.field === 'gap') return <span className={`v ${v ? 'bad' : 'ok'}${o}`}>{v ? 'Yes' : 'No'}</span>
  if (v === null) return <span className={o.trim()}>None</span>
  if (f.field.endsWith('verdict')) return <span className={`v ${VCLS[v as string]}${o}`}>{String(v)[0].toUpperCase() + String(v).slice(1)}</span>
  return <span className={o.trim()}>{f.field === 'exposure' ? EXPOSURE[v as string] : String(v)}</span>
}

/** c5-changes: this run against the latest run of the previous version. */
export function Changes({ vid }: { vid: string }) {
  const [c, setC] = useState<C | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => { api<C>(`/versions/${vid}/changes`).then(setC).catch((e) => setErr(e.message)) }, [vid])
  const jump = (id: string) => (e: React.MouseEvent) => { e.preventDefault(); document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' }) }
  const map = `#/v/${vid}/map`
  const n = c?.counts
  const m = c?.map

  return (
    <VersionShell vid={vid} on="Changes since last run">
      <main className="page changes">
        <div className="page-head">
          <h1>Changes since last run</h1>
          {c?.previous && c.run
            ? <p>This run ({fmtDate(c.run.started_at)}) against the latest run of the previous version ({fmtDate(c.previous.run.started_at)}, version of {fmtDate(c.previous.created_at)}). Questions are matched by ID, topics by concept ID.</p>
            : c && <p>There is no previous run to compare with: this is the first version of {c.course_code} with a test-drive{c.run ? '' : ', or this version has no test-drive yet'}.</p>}
        </div>
        {err && <p className="err">{err}</p>}
        {n && m && c?.questions && <>
          <div className="counts">
            <a href="" onClick={jump('q')}><b>{n.gaps_fixed}</b>gaps fixed</a>
            <a href="" onClick={jump('q')}><b>{n.new_gaps}</b>new gap{n.new_gaps === 1 ? '' : 's'}</a>
            <a href="" onClick={jump('q')}><b>{n.edited}</b>question{n.edited === 1 ? '' : 's'} edited</a>
            <a href="" onClick={jump('q')}><b>{n.results}</b>with changed results</a>
            <a href="" onClick={jump('m')}><b>{n.depth}</b>depth changes</a>
            <a href="" onClick={jump('m')}><b>{n.topics}</b>topics added or removed</a>
          </div>
          <div className="row">
            <section className="panel" id="q">
              <h2>Questions</h2>
              <p className="hint">Changes in student verdict, web verdict, AI exposure, gap and recommendation.</p>
              <div className="outcomes">
                {c.questions.length === 0 && <p className="muted">No question changed.</p>}
                {c.questions.flatMap((q) => {
                  const rows = [
                    ...(q.edited ? [<><p>Question edited</p>{q.fields.length === 0 && <div className="shift"><span>No change in results</span></div>}</>] : []),
                    ...q.fields.map((f) => <><p>{FIELD[f.field]}</p><div className="shift">{val(f, f.before, true)}<i>to</i>{val(f, f.after, false)}</div></>),
                  ]
                  return rows.map((r, i) => (
                    <div key={`${q.question_id}-${i}`} className={`oc${i ? ' sub' : ''}`}>
                      {i ? <span /> : <a className="q" href={`#/v/${vid}/review/${q.question_id}`}>{short(q.question_id)}</a>}{r}
                    </div>
                  ))
                })}
              </div>
            </section>
            <section className="panel" id="m">
              <h2>Course map</h2>
              <p className="hint">Depth changes per week{n.topics ? '' : '. No topics were added or removed'}.</p>
              <div className="files">
                {m.added.map((t) => <div className="file" key={`a${t.concept_id}`}><a className="q" href={map}>{t.name}</a><span className="wk">Topic</span><div className="shift"><span className="old">Not in the map</span><i>to</i><span>Added</span></div></div>)}
                {m.removed.map((t) => <div className="file" key={`r${t.concept_id}`}><span>{t.name}</span><span className="wk">Topic</span><div className="shift"><span className="old">In the map</span><i>to</i><span>Removed</span></div></div>)}
                {m.depth.map((d) => (
                  <div className="file" key={`${d.concept_id}-${d.week}`}><a className="q" href={map}>{d.name}</a><span className="wk">Week {d.week}</span>
                    <div className="shift"><span className="old">{depth(d.before)}</span><i>to</i><span>{depth(d.after)}</span></div></div>
                ))}
                {m.depth.length + m.added.length + m.removed.length === 0 && <p className="muted">No change in the course map.</p>}
              </div>
            </section>
          </div>
        </>}
      </main>
    </VersionShell>
  )
}
