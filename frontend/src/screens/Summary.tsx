import { Fragment, useEffect, useState } from 'react'
import { api } from '../api'
import { AddedNotice, VersionShell, fmtDate } from '../Shell'
import { FORMAT_LABEL, type Summary as S } from '../types'

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

/** c1-summary: verdict, key figures, top actions, exposure grid, one bar per assessment. */
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

          <section className="panel">
            <h2>By assessment</h2>
            <p className="hint">One segment per question, in paper order.</p>
            <div className="comps">
              {s.assessments.map((a) => {
                const notes = Object.entries(a.groups).filter(([k]) => k !== 'Keep as is').map(([k, n]) => `${n} ${k.toLowerCase()}`)
                return (
                  <div className="comp" key={a.assessment_id}>
                    <div><b>{a.assessment_id}</b><small>Week {a.week_cutoff}, {FORMAT_LABEL[a.current_format]}</small></div>
                    <div className="bar">{a.segments.map((x, i) => <span key={i} className={x} />)}</div>
                    <div className="note">{notes.join(', ') || 'All can stay as they are'}</div>
                  </div>
                )
              })}
            </div>
            <div className="legend"><span>Depends on the course</span><span className="ai">AI-exposed</span><span className="gap">Coverage gap</span><span className="other">Review or not assessed</span></div>
          </section>
        </>}
      </main>
    </VersionShell>
  )
}
