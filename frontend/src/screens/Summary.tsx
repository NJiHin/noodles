import { Fragment, useEffect, useState } from 'react'
import { api } from '../api'
import { AddedNotice, VersionShell, fmtDate } from '../Shell'
import type { Summary as S } from '../types'

/** 'week-4-quiz-q1b' -> ['Q1B', 'week-4-quiz'] */
const split = (id: string) => { const i = id.lastIndexOf('-q'); return [id.slice(i + 1).toUpperCase(), id.slice(0, i)] }

const ACTIONS: Record<string, [string, (n: number) => string]> = {
  fix_coverage: ['Fix coverage first', (n) => `${n} question${n === 1 ? ' has' : 's have'} a step with no source, a citation the grounding checker rejected, or knowledge you rejected.`],
  review: ['Review the question', (n) => `${n} question${n === 1 ? '' : 's'} the course-limited student gets wrong: the question may be broken, or it needs knowledge that's neither taught nor declared.`],
  keep_open: ['Could be open or take-home', (n) => `${n} invigilated question${n === 1 ? '' : 's'} only the course-limited student answered. They already certify learning.`],
  confirm_assumptions: ['Confirm assumptions', () => 'Steps the student treated as known from the entry requirements. Not counted as gaps until you reject them.'],
  change_format: ['Change format', (n) => `${n} AI-exposed question${n === 1 ? '' : 's'} in an open format. A lookup: closed-book, invigilated. Reasoning: open-book invigilated, or redesign.`],
}
const CELLS: [keyof S['matrix'], string, string, string][] = [
  ['ai_exposed', 'exposed', 'AI-exposed', 'A web search is enough'],
  ['course_specific', 'good', 'Depends on the course', 'Certifies learning'],
  ['neither_taught', 'bad', 'Needs untaught knowledge', 'Neither taught nor declared'],
  ['broken_or_gap', 'bad', 'Broken question, or a gap', 'Neither agent answers it'],
]

/** c1-summary: verdict, key figures, top actions, exposure grid, and what the assessments cover across the semester. */
export function Summary({ vid }: { vid: string }) {
  const [s, setS] = useState<S | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => { api<S>(`/versions/${vid}/summary`).then(setS).catch((e) => setErr(e.message)) }, [vid])
  const q = (id: string) => `#/v/${vid}/review/${id}`
  const chip = (id: string, withAssessment = true) => {
    const [label, aid] = split(id)
    return <a key={id} className="chip" href={q(id)}>{label}{withAssessment && <i>{aid}</i>}</a>
  }
  const g = (name: string) => s?.groups[name] ?? 0

  return (
    <VersionShell vid={vid} on="Summary">
      <main className="page summary">
        {err && <p className="err">{err}</p>}
        {s && !s.assessed && <div className="page-head"><h1>Summary</h1><p>No results yet. Start a test-drive on the <a href={`#/v/${vid}/review`}>Assessment review</a> page.</p></div>}
        {s && s.assessed > 0 && <>
          <div className="page-head">
            <div className="meta">{s.course_code}. Test-drive of {s.run && fmtDate(s.run.started_at)}.</div>
            <p className="verdict" style={{ marginTop: 10 }}>{s.keep} of {s.assessed} questions can stay as they are. <span>{s.figures.gaps} have a coverage gap, {g('Change format')} may need a new format, and {g('Could be open or take-home')} could be open or take-home.</span></p>
            <div className="figures">
              <div><b>{s.figures.gaps}</b>coverage gaps</div>
              <div><b>{s.figures.ai_exposed}</b>AI-exposed</div>
              <div><b>{s.figures.assumptions}</b>assumptions to confirm</div>
              <div><b>{s.figures.never_assessed}</b>topic{s.figures.never_assessed === 1 ? '' : 's'} never assessed</div>
            </div>
          </div>
          <AddedNotice key={s.run?.run_id} vid={vid} screen="results" />

          <div className="row">
            <section className="panel">
              <h2>Top actions</h2>
              <p className="hint">In the order the recommendation rules apply. Coverage comes first, because a question the course doesn't support can't be judged on format.</p>
              <ol className="actions">
                {s.actions.map((a) => (
                  <li key={a.key}>
                    <div>
                      <b>{a.key === 'confirm_assumptions' ? `Confirm ${s.figures.assumptions} assumption${s.figures.assumptions === 1 ? '' : 's'}` : ACTIONS[a.key][0]}</b>
                      <p>{ACTIONS[a.key][1](a.questions.length)}</p>
                      {a.key !== 'confirm_assumptions' && <div className="qs">{a.questions.map((id) => chip(id))}</div>}
                    </div>
                    <a className="btn" href={q(a.questions[0])}>{a.key === 'confirm_assumptions' ? 'Review' : 'Open'}</a>
                  </li>
                ))}
                {s.actions.length === 0 && <li><div><b>Nothing to change</b><p>Every assessed question can stay as it is.</p></div></li>}
              </ol>
            </section>

            <section className="panel">
              <h2>Who can answer each question</h2>
              <p className="hint">The course-limited student against the web-search agent. Questions without marking material aren't placed.</p>
              <div className="matrix">
                <div></div><div className="ax">Web agent right</div><div className="ax">Web agent wrong</div>
                {CELLS.map(([k, cls, title, sub], i) => (
                  <Fragment key={k}>
                    {i % 2 === 0 && <div className="ay">{i === 0 ? 'Student right' : 'Student wrong'}</div>}
                    <div className={`cell ${cls}`}>
                      <h3>{title} <span>{s.matrix[k].length}</span></h3>
                      <p>{sub}</p>
                      <div className="chips">{s.matrix[k].map((id) => chip(id, false))}</div>
                    </div>
                  </Fragment>
                ))}
              </div>
            </section>
          </div>

          <Coverage c={s.coverage} />
        </>}
      </main>
    </VersionShell>
  )
}

/** Topics introduced each week, assessed by any question or never; dotted lines where each assessment's weeks end. */
function Coverage({ c }: { c: S['coverage'] }) {
  const n = c.weeks.length
  const by = (w: number) => c.topics.filter((t) => t.first_week === w)
  const top = Math.max(1, ...c.weeks.map((w) => by(w).length))
  const cutoffs = [...new Set(c.assessments.map((a) => a.week_cutoff))].sort((a, b) => a - b)
  // the untested topics in the stretch of weeks before each test
  const spans = cutoffs.map((cut, i) => {
    const from = (cutoffs[i - 1] ?? 0) + 1
    const ts = c.topics.filter((t) => t.first_week !== null && t.first_week >= from && t.first_week <= cut)
    return { from, cut, names: c.assessments.filter((a) => a.week_cutoff === cut).map((a) => a.assessment_id).join(', '),
      total: ts.length, never: ts.filter((t) => !t.assessed) }
  })
  const [open, setOpen] = useState<number | null>(null)
  return (
    <section className="panel">
      <div className="cov-head">
        <div><h2>What the assessments cover</h2><p className="hint">Topics introduced each week, and whether any question tests them.</p></div>
        <div className="cov-key"><span><i className="yes" />assessed</span><span><i className="no" />never assessed</span><span><i className="dl" />last week an assessment covers</span></div>
      </div>
      <div className="cov-chart" style={{ '--n': n } as React.CSSProperties}>
        <div className="cov-cols">
          {c.weeks.map((w) => {
            const ts = by(w), yes = ts.filter((t) => t.assessed).length
            return (
              <div key={w} className="cov-col" title={`Week ${w}: ${yes} of ${ts.length} assessed`}>
                {yes > 0 && <i className="yes" style={{ height: `${(yes / top) * 150}px` }} />}
                {ts.length > yes && <i className="no" style={{ height: `${((ts.length - yes) / top) * 150}px` }} />}
                <span>{ts.length}</span>
              </div>
            )
          })}
        </div>
        {cutoffs.filter((w) => w <= n).map((w) => (
          <div key={w} className={`cov-test${w === n ? ' end' : ''}`} style={{ left: w === n ? '100%' : `calc(${w} * (100% + 10px) / ${n} - 5px)` }}>
            <span>{c.assessments.filter((a) => a.week_cutoff === w).map((a) => a.assessment_id).join(', ')}</span>
          </div>
        ))}
        <div className="cov-x">{c.weeks.map((w) => <span key={w}>W{w}</span>)}</div>
      </div>
      <div className="cov-per">
        {spans.map((p, i) => (
          <div key={p.cut}>
            <div><b>Weeks {p.from} to {p.cut}</b><small>before {p.names}</small></div>
            <span className="names"><b>{p.never.length} of {p.total}</b> never assessed{p.never.length > 0 && ': '}
              {(open === i ? p.never : p.never.slice(0, 4)).map((t) => t.name).join(', ')}{open !== i && p.never.length > 4 && ` and ${p.never.length - 4} more`}</span>
            {p.never.length > 4 && <button className="link" onClick={() => setOpen(open === i ? null : i)}>{open === i ? 'Show fewer' : 'Show all'}</button>}
          </div>
        ))}
      </div>
    </section>
  )
}
