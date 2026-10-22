import { useEffect, useState } from 'react'
import { api } from '../api'
import { VersionShell, fmtDate } from '../Shell'
import type { RunStatus } from '../types'

type TypeCost = { calls: number; input_tokens: number; cached_tokens: number; output_tokens: number; web_search_calls: number; cost: number }
type M = {
  course_code: string; created_at: string
  run: (RunStatus & {
    prerequisite: string | null; compared_with: { version_id: string; run: RunStatus } | null; passages: number; transcribed: number
    topics: number; map_reviewed_at: string | null; questions: number; assessments: number; assessed: number; rerun: number; models: string[]
  }) | null
  cost: { total: number | null; web_search_calls: number; by_type: Record<string, TypeCost> }
  runs: { run_id: string; kind: string; started_at: string; assessment_id: string | null; questions: number
    new_calls: number; web_search_calls: number; cost: number | null }[]
  runs_total: number | null  // null while a price is missing
}

const MODEL: Record<string, string> = { 'gpt-6-luna': 'GPT-6 Luna', 'gpt-6-sol': 'GPT-6 Sol' }
const usd = (x: number) => `US$${x.toFixed(x < 0.1 ? 4 : 2)}`
const n = (x: number) => x.toLocaleString('en-GB')
const when = (iso: string) => new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
const KIND: Record<string, string> = { map: 'Course map', split: 'Question split', test_drive: 'Test-drive' }

const STEPS: [string, string][] = [
  ['Read the materials', 'Every slide or page becomes a passage. Pages with diagrams, tables or equations are transcribed by a vision model, and the report says when a step relies on one.'],
  ['Build the course map', 'Topics are extracted week by week, merged, and confirmed by you before anything else runs.'],
  ['Attempt each question as a student', 'The student has the prerequisites and weeks 1 to N of the course, where N is the last week the assessment covers. It never sees later weeks or the answer key, and cites a passage for each step. Steps with no source get one keyword search over the same weeks, in case a passage was missed.'],
  ['Attempt each question with a web search', 'A second agent answers with the open web, standing in for a student using AI.'],
  ['Check and mark', 'Each cited step is checked against its passage. Both final answers are marked against your marking material, without the marker knowing which agent wrote them.'],
]
const LIMITS: [string, string][] = [
  ['One attempt per question.', 'Each agent answers once at temperature 0. A rerun can occasionally differ.'],
  ["The student isn't a real student.", "It shows whether the materials support an answer, not how hard students will find the question or what grades they'll get."],
  ['The web agent stands in for AI use in general.', 'A different tool or a stronger model might answer questions this one got wrong.'],
  ["Depth labels are a model's judgement.", '"Only mentioned" findings are prompts to check, not errors.'],
  ['Lookup or reasoning is a heuristic.', 'One knowledge step or fewer counts as lookup; two or more as reasoning.'],
  ['Topics are linked to questions through citations.', "A topic used only in an assumed or unsourced step doesn't count as assessed, and a cited passage tagged with several topics counts for all of them."],
  ['Code questions are not assessed.', 'No agent runs on them yet; they\'re listed as "not assessed (code question)".'],
  ["It doesn't detect AI-written work.", 'Nor does it make any assessment AI-proof. Recommendations are advisory; you decide.'],
]

/** c6-method: every run of the course with its cost, this run's facts, then how it works and the limitations. */
export function Method({ vid }: { vid: string }) {
  const [m, setM] = useState<M | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => { api<M>(`/versions/${vid}/method`).then(setM).catch((e) => setErr(e.message)) }, [vid])
  const r = m?.run
  const c = m?.cost
  const tokens = c ? Object.values(c.by_type).reduce((a, t) => a + t.input_tokens + t.output_tokens, 0) : 0
  const searches = c && c.web_search_calls ? `, incl. ${c.web_search_calls} web search${c.web_search_calls === 1 ? '' : 'es'}` : ''

  return (
    <VersionShell vid={vid} on="Method and limitations">
      <main className="page method">
        <div className="page-head">
          <h1>Method and limitations</h1>
          <p>How this report was produced, and what it can't tell you.</p>
        </div>
        {err && <p className="err">{err}</p>}
        <div className="cols">
          <section className="panel">
            <div className="runs-h"><h2>All runs for {m?.course_code ?? '…'}</h2>
              {m && <span>{m.runs_total !== null ? <b>{usd(m.runs_total)}</b> : <b>Prices not set</b>} across {m.runs.length} run{m.runs.length === 1 ? '' : 's'} · group budget US$40</span>}</div>
            {m && m.runs.length > 0 && (
              <table className="t runs">
                <thead><tr><th>When</th><th>Run</th><th>Questions</th><th>New calls</th><th>Web searches</th><th>Cost</th></tr></thead>
                <tbody>{m.runs.map((x) => (
                  <tr key={x.run_id}><td>{when(x.started_at)}</td><td>{KIND[x.kind] ?? x.kind}{x.assessment_id && `, ${x.assessment_id}`}</td>
                    <td>{x.questions || '—'}</td><td>{x.new_calls}</td><td>{x.web_search_calls}</td><td>{x.new_calls === 0 ? '—' : x.cost !== null ? usd(x.cost) : '–'}</td></tr>
                ))}</tbody>
                <tfoot><tr><td colSpan={3}>Total</td><td>{m.runs.reduce((a, x) => a + x.new_calls, 0)}</td>
                  <td>{m.runs.reduce((a, x) => a + x.web_search_calls, 0)}</td><td>{m.runs_total !== null ? usd(m.runs_total) : '–'}</td></tr></tfoot>
              </table>
            )}
            <p className="hint">Results reused from the run log cost nothing and aren't counted.</p>
          </section>
          <section className="panel">
            <h2>This run</h2>
            {m && !r && <p className="hint">No test-drive yet.</p>}
            {m && r && c && <>
              <dl>
                <dt>Course version</dt><dd>{fmtDate(m.created_at)}</dd>
                <dt>Compared with</dt><dd>{r.compared_with ? `Run of ${fmtDate(r.compared_with.run.started_at)}` : 'No previous run'}</dd>
                <dt>Prerequisites</dt><dd>{r.prerequisite ?? 'None'}</dd>
                <dt>Passages</dt><dd>{n(r.passages)}, of which {n(r.transcribed)} transcribed</dd>
                <dt>Topics in map</dt><dd>{r.topics}{r.map_reviewed_at && `, confirmed ${fmtDate(r.map_reviewed_at)}`}</dd>
                <dt>Questions</dt><dd>{r.questions} in {r.assessments} assessment{r.assessments === 1 ? '' : 's'}</dd>
                <dt>Rerun this time</dt><dd>{r.rerun} of {r.assessed} questions, the rest reused</dd>
                <dt>Models</dt><dd>{r.models.map((x) => MODEL[x] ?? x).join(', ') || 'None called'}</dd>
                <dt>Actual cost</dt><dd>{c.total !== null ? `${usd(c.total)}${searches}` : `Prices not set: ${n(tokens)} tokens${searches}`}</dd>
              </dl>
              {Object.keys(c.by_type).length > 0 && (
                <table className="t cost">
                  <thead><tr><th>Call type</th><th>New calls</th><th>Tokens in / out</th><th>Cost</th></tr></thead>
                  <tbody>{Object.entries(c.by_type).map(([k, t]) => (
                    <tr key={k}><td>{k}</td><td>{t.calls}</td><td>{n(t.input_tokens)} / {n(t.output_tokens)}</td><td>{c.total !== null ? usd(t.cost) : '–'}</td></tr>
                  ))}</tbody>
                </table>
              )}
              {c.total === null && <p className="hint">Set the per-model prices in noodles/cost.py to see the cost in dollars.</p>}
            </>}
          </section>
        </div>
        <section className="panel static">
          <div>
            <h2>How it works</h2>
            <ol className="flow">{STEPS.map(([b, p]) => <li key={b}><div><b>{b}</b><p>{p}</p></div></li>)}</ol>
          </div>
          <div>
            <h2>Limitations</h2>
            <div className="lim">{LIMITS.map(([b, p]) => <div key={b}><b>{b}</b><p>{p}</p></div>)}</div>
          </div>
        </section>
      </main>
    </VersionShell>
  )
}
