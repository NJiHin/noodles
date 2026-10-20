import { useEffect, useState } from 'react'
import { api, pdfHref, post } from '../api'
import { RunProgress } from '../RunProgress'
import { VersionShell, fmtDate } from '../Shell'
import { FORMAT_LABEL, type Mark, type ReviewQuestion, type ReviewResp, type Step, type Verdict } from '../types'

type Course = { code: string; versions: { map_reviewed_at: string | null }[] }

const GROUNDING = { supported: 'Supported.', partial: 'Weak citation.', unsupported: 'Unsupported: counts as a gap.' }

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
    ['Gap: a step is uncited or unsupported', qs.filter((q) => q.gap)],
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
        <main className="detail">{sel ? <Detail q={sel} prereq={r?.prerequisite ?? null} runId={r?.run?.run_id ?? ''} reload={load} /> : <p className="muted">Confirm an assessment's questions, then start a test-drive.</p>}</main>
      </div>
    </VersionShell>
  )
}

function Detail({ q, prereq, runId, reload }: { q: ReviewQuestion; prereq: string | null; runId: string; reload: () => void }) {
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
          <Exposure q={q} />
          <div className="answers">
            <AnswerCard title="Course-limited student" answer={a.final_answer} mark={q.marks?.student} gap={q.gap}
              override={(v) => setVerdict(runId, q.question_id, 'student', v, reload)} />
            {q.web && <AnswerCard title="Web-search agent" answer={q.web.final_answer} mark={q.marks?.web} sources={q.web.sources}
              override={(v) => setVerdict(runId, q.question_id, 'web', v, reload)} />}
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
  const g = s.grounding
  const cls = s.source === 'none' || g?.verdict === 'unsupported' ? ' miss' : g?.verdict === 'partial' ? ' thin'
    : s.source === 'assumed_knowledge' ? ' ask' : ''
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
        {g && <p className="why"><b>{GROUNDING[g.verdict]}</b> {g.verdict !== 'supported' && `Grounding checker: ${g.verdict}. `}{g.reason}</p>}
        {s.source === 'none' && <p className="why"><b>No source.</b> Not found in weeks 1 to {cutoff}{prereq ? ` or ${prereq}` : ''}, including the keyword re-check.</p>}
        {s.source === 'assumed_knowledge' && <p className="why"><b>Assumed knowledge.</b> {s.accepted_id != null ? `Accepted assumption #${s.accepted_id}.` : s.reason}</p>}
      </div>
    </li>
  )
}

const VERDICT_CLASS: Record<Verdict, string> = { correct: 'ok', partial: 'part', incorrect: 'bad' }
const cap = (s: string) => s[0].toUpperCase() + s.slice(1)

async function setVerdict(runId: string, qid: string, agent: string, verdict: Verdict, reload: () => void) {
  await api(`/runs/${runId}/overrides/${qid}/${agent}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ verdict }) })
  reload()
}

function AnswerCard({ title, answer, mark, gap, sources, override }: {
  title: string; answer: string | null; mark?: Mark; gap?: boolean; sources?: string[]; override: (v: Verdict) => void
}) {
  const [open, setOpen] = useState(false)
  return (
    <div className="ans">
      <h3>{title} <span>{gap && <span className="v bad">Gap</span>} {mark && <span className={`v ${VERDICT_CLASS[mark.verdict]}`}>{cap(mark.verdict)}</span>}</span></h3>
      <p className="a">{answer ?? <span className="muted">No answer: couldn't attempt it.</span>}</p>
      <p className="src">
        {mark && <>{mark.by === 'marker' ? 'Marker: ' : ''}{mark.reason}
          {mark.overridden && ` Overridden by you; the marker said ${mark.overridden}.`}
          {open
            ? <select className="ovr-pick" aria-label={`Override ${title}`} autoFocus defaultValue="" onChange={(e) => { setOpen(false); override(e.target.value as Verdict) }}>
                <option value="" disabled>Verdict…</option>
                {(['correct', 'partial', 'incorrect'] as Verdict[]).map((v) => <option key={v} value={v}>{cap(v)}</option>)}
              </select>
            : <button className="ovr" onClick={() => setOpen(true)}>Override</button>}</>}
        {sources && sources.length > 0 && <>{mark && <br />}Sources: {sources.map((u, i) => <span key={u}>{i > 0 && ', '}<a href={u} target="_blank" rel="noreferrer">{host(u)}</a></span>)}</>}
      </p>
    </div>
  )
}

const host = (u: string) => { try { return new URL(u).hostname } catch { return u } }

const EXPOSURE: Record<string, [string, string, string]> = {
  ai_exposed: ['r-format', 'AI-exposed', 'The web-search agent answers it correctly, as does the course-limited student.'],
  course_specific: ['r-keep', 'Depends on course-specific context', 'The student answers it from the course; the web-search agent doesn\'t.'],
  neither_taught: ['r-gap', 'Needs knowledge that\'s neither taught nor declared', 'The web-search agent answers it correctly; the course-limited student doesn\'t.'],
  broken_or_gap: ['r-gap', 'Broken question, or a gap', 'Neither answer is correct.'],
  not_assessed: ['', 'AI exposure not assessed', 'This question has no marking material.'],
}

function Exposure({ q }: { q: ReviewQuestion }) {
  if (!q.exposure) return null
  const [cls, title, text] = EXPOSURE[q.exposure]
  return (
    <div className={`rec ${cls}`}>
      <b>{title}</b>
      <p>{text}</p>
      {q.marks && <p className="facts">Student {q.marks.student.verdict}, web-search agent {q.marks.web.verdict}. Only "correct" counts as right.</p>}
    </div>
  )
}
