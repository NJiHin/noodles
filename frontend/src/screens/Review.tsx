import { useEffect, useState } from 'react'
import { api, pdfHref, post } from '../api'
import { RunProgress } from '../RunProgress'
import { VersionShell, fmtDate } from '../Shell'
import { FORMAT_LABEL, type ReviewQuestion, type ReviewResp, type Step } from '../types'

type Course = { code: string; versions: { map_reviewed_at: string | null }[] }

const short = (q: ReviewQuestion) => q.question_id.replace(`${q.assessment_id}-`, '').toUpperCase()

/** c2-review: questions on the left, the selected question's student answer and steps on the right. */
export function Review({ vid, qid }: { vid: string; qid?: string }) {
  const [r, setR] = useState<ReviewResp | null>(null)
  const [prereqs, setPrereqs] = useState<string[]>([])
  const [prereq, setPrereq] = useState('')
  const [err, setErr] = useState('')
  const load = () => api<ReviewResp>(`/versions/${vid}/review`).then((x) => {
    setR(x); if (x.prerequisite) setPrereq(x.prerequisite)
  }).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [vid]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (r) api<Course[]>('/courses').then((cs) => setPrereqs(cs.filter((c) => c.code !== r.course_code
      && c.versions.some((v) => v.map_reviewed_at)).map((c) => c.code)))
  }, [r?.course_code]) // eslint-disable-line react-hooks/exhaustive-deps

  async function start() {
    setErr('')
    try { await post(`/versions/${vid}/test-drives`, { prerequisite: prereq || null }); await load() } catch (e) { setErr((e as Error).message) }
  }

  const qs = r?.questions ?? []
  const groups: [string, ReviewQuestion[]][] = [
    ['Gap: a step has no source', qs.filter((q) => q.gap)],
    ['No gap found', qs.filter((q) => q.answer && !q.gap)],
    ['Not run yet', qs.filter((q) => !q.answer && q.type !== 'code')],
    ['Not assessed (code question)', qs.filter((q) => q.type === 'code')],
  ]
  const sel = qs.find((q) => q.question_id === qid) ?? groups.flatMap(([, g]) => g)[0]
  const running = r?.run?.status === 'running'

  return (
    <VersionShell vid={vid} on="Assessment review">
      <div className="review">
        <section className="list">
          <div className="list-head">
            <h1>Assessment review</h1>
            {r?.run && !running && <p className="meta">Test-drive of {fmtDate(r.run.started_at)}{r.prerequisite && `, prerequisite ${r.prerequisite}`}{r.run.status !== 'done' && `, ${r.run.status}`}</p>}
            {running && r?.run && <RunProgress runId={r.run.run_id} onEnd={load} />}
            {!running && (
              <div className="start">
                <label>Prerequisite <select value={prereq} onChange={(e) => setPrereq(e.target.value)}>
                  <option value="">None</option>
                  {prereqs.map((c) => <option key={c}>{c}</option>)}
                </select></label>
                <button className="btn primary" onClick={start}>{r?.run ? 'Rerun test-drive' : 'Start test-drive'}</button>
              </div>
            )}
            {(err || r?.run?.error) && <p className="err">{err || r?.run?.error}</p>}
          </div>
          {groups.filter(([, g]) => g.length).map(([name, g]) => (
            <div key={name}>
              <div className="group"><span>{name}</span><span>{g.length}</span></div>
              {g.map((q) => (
                <a key={q.question_id} className={`item${q === sel ? ' on' : ''}${q.type === 'code' ? ' done' : ''}`} href={`#/v/${vid}/review/${q.question_id}`}>
                  <span className="id">{short(q)}</span><span className="t">{q.text}</span><span className="wk">{q.assessment_id}</span>
                </a>
              ))}
            </div>
          ))}
        </section>
        <main className="detail">{sel ? <Detail q={sel} prereq={r?.prerequisite ?? null} /> : <p className="muted">Confirm an assessment's questions, then start a test-drive.</p>}</main>
      </div>
    </VersionShell>
  )
}

function Detail({ q, prereq }: { q: ReviewQuestion; prereq: string | null }) {
  const a = q.answer
  return (
    <>
      <div>
        <div className="meta">{q.assessment_id}, question {short(q)}. Covers weeks 1 to {q.week_cutoff}, {FORMAT_LABEL[q.current_format]}.</div>
        <h2 className="qtitle">{q.text}</h2>
        {q.options && <ol className="opts">{q.options.map((o, i) => <li key={i}>({String.fromCharCode(65 + i)}) {o}</li>)}</ol>}
      </div>
      {q.type === 'code' && <p className="muted">Not assessed (code question).</p>}
      {q.type !== 'code' && !a && <p className="muted">Not run yet. Start a test-drive to see the student's answer.</p>}
      {a && (
        <>
          <div className="answers">
            <div className="ans">
              <h3>Course-limited student {q.gap && <span className="v bad">Gap</span>}</h3>
              <p className="a">{a.final_answer ?? <span className="muted">No answer: the student couldn't attempt it.</span>}</p>
            </div>
          </div>
          <div className="steps">
            <h2>The student's steps</h2>
            {a.steps.length === 0 && <p className="muted">No knowledge steps listed.</p>}
            <ol>{a.steps.map((s, i) => <StepItem key={s.step_id} s={s} n={i + 1} cutoff={q.week_cutoff} prereq={prereq} />)}</ol>
          </div>
        </>
      )}
    </>
  )
}

function StepItem({ s, n, cutoff, prereq }: { s: Step; n: number; cutoff: number; prereq: string | null }) {
  const cls = s.source === 'none' ? ' miss' : s.source === 'assumed_knowledge' ? ' ask' : ''
  return (
    <li className={`s${cls}`}><span className="mark">{n}</span>
      <div className="card">
        <p className="claim">{s.claim}</p>
        {s.evidence.map((p) => (
          <div className="passage" key={p.passage_id}>
            {p.slug && p.version_id && p.page
              ? <span><a href={pdfHref(p.version_id, p.slug, p.page)} target="_blank" rel="noreferrer">{p.course}, week {p.week}, {p.filename}, page {p.page}</a></span>
              : <span>{p.passage_id} (not a passage the student could see)</span>}
            {p.text && <q>{p.text}</q>}
          </div>
        ))}
        {s.source === 'none' && <p className="why"><b>No source.</b> Not found in weeks 1 to {cutoff}{prereq ? ` or ${prereq}` : ''}, including the keyword re-check.</p>}
        {s.source === 'assumed_knowledge' && <p className="why"><b>Assumed knowledge.</b> {s.accepted_id != null ? `Accepted assumption #${s.accepted_id}.` : s.reason}</p>}
      </div>
    </li>
  )
}
