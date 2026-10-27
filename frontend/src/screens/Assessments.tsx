import { useEffect, useState } from 'react'
import { api } from '../api'
import { FileStatus, activeFile, useProgress } from '../FileProgress'
import { animated, vtName } from '../animated'
import { ConfirmDialog } from '../ConfirmDialog'
import { RunProgress } from '../RunProgress'
import { VersionShell } from '../Shell'
import { FORMAT_LABEL, QTYPES, type Assessment, type Question } from '../types'

/** Upload each assessment with its answers, then confirm the questions split out of it. */
export function Assessments({ vid }: { vid: string }) {
  const [list, setList] = useState<Assessment[] | null>(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [reading, setReading] = useState<{ id: string; files: string[] } | null>(null)  // files being read, for progress
  const prog = useProgress(reading?.id ?? null)
  const load = () => api<Assessment[]>(`/versions/${vid}/assessments`).then(setList).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [vid]) // eslint-disable-line react-hooks/exhaustive-deps

  async function add(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget
    const fd = new FormData(form)
    if (!(fd.get('answers') as File)?.size) fd.delete('answers')
    const id = crypto.randomUUID()
    fd.set('progress_id', id)
    setErr(''); setBusy(true)
    setReading({ id, files: ['paper', 'answers'].map((k) => (fd.get(k) as File | null)?.name).filter((n): n is string => !!n) })
    try {
      await api(`/versions/${vid}/assessments`, { method: 'POST', body: fd })
      form.reset(); await load()
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false); setReading(null) }
  }

  return (
    <VersionShell vid={vid} on="Assessments">
      <main className="page">
        <div className="page-head">
          <div className="meta">Version {vid}</div>
          <h1>Assessments</h1>
          <p>Upload each assessment with its answers or marking material. The paper is split into questions for you to check before any run. Assessments are never shown to the simulated student.</p>
        </div>

        <section className="panel">
          <h2>Add an assessment</h2>
          <p className="hint">The week cutoff is the last week it covers: the student sees weeks 1 to that week only.</p>
          <form className="row-form" onSubmit={add}>
            <label className="field">Name<input name="name" required placeholder="Midterm" /></label>
            <label className="field">Covers weeks 1 to<input name="week_cutoff" type="number" min={1} required style={{ width: 90 }} /></label>
            <label className="field">Current format
              <select name="current_format" required defaultValue="">
                <option value="" disabled>Choose…</option>
                {Object.entries(FORMAT_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
            <label className="field">Paper<input name="paper" type="file" accept=".pdf,.pptx,.docx" required /></label>
            <label className="field">Answers (optional)<input name="answers" type="file" accept=".pdf,.pptx,.docx" /></label>
            <button className="btn primary" disabled={busy}>{busy ? 'Reading files…' : 'Add'}</button>
          </form>
          {reading && (
            <table className="t">
              <tbody>
                {reading.files.map((f) => (
                  <tr key={f}><td>{f}</td><td style={{ width: 110 }}><FileStatus p={prog?.[f]} active={f === activeFile(reading.files, prog)} /></td></tr>
                ))}
              </tbody>
            </table>
          )}
          {err && <p className="err">{err}</p>}
        </section>

        {list?.map((a) => <AssessmentPanel key={`${a.assessment_id}-${a.state}-${a.run?.run_id ?? ''}`} vid={vid} a={a} reload={load}
          deleted={() => { animated(() => setList((l) => l && l.filter((x) => x.assessment_id !== a.assessment_id))); load() }} />)}
      </main>
    </VersionShell>
  )
}

function AssessmentPanel({ vid, a, reload, deleted }: { vid: string; a: Assessment; reload: () => void; deleted: () => void }) {
  const [qs, setQs] = useState<Question[]>(a.questions)
  const [err, setErr] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [open, setOpen] = useState(a.state !== 'confirmed')  // confirmed ones start collapsed
  const set = (i: number, q: Partial<Question>) => setQs(qs.map((x, j) => (j === i ? { ...x, ...q } : x)))
  const label = (q: Question) => q.question_id.replace(`${a.assessment_id}-`, '')
  // questions with identical context share one box, shown before the first of them; saving it rewrites all of them
  const sharing = (ctx: string) => qs.filter((x) => x.context === ctx)
  const setShared = (from: string, to: string) => setQs(qs.map((x) => (x.context === from ? { ...x, context: to } : x)))

  async function confirm() {
    setErr('')
    try {
      await api(`/versions/${vid}/assessments/${a.assessment_id}/questions`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ questions: qs.map(({ flags: _, ...q }) => q) }),
      })
      reload()
    } catch (e) { setErr((e as Error).message) }
  }

  const flagged = qs.filter((q) => q.flags?.length).length
  return (
    <section className="panel" style={{ viewTransitionName: vtName('a', a.assessment_id) }}>
      <div className="a-head">
        <div>
          <h2><button className="a-toggle" aria-expanded={open} onClick={() => setOpen(!open)}><span className="chev">›</span>{a.assessment_id}</button></h2>
          <p className="hint">Weeks 1 to {a.week_cutoff} · {FORMAT_LABEL[a.current_format]} · {Object.values(a.files).join(', ')}{!a.files.answers && ' · no answers file'}</p>
        </div>
        {a.state === 'confirmed' && <span className="v ok">Confirmed, {a.questions.length} questions</span>}
        {a.state === 'draft' && <span className="v part">Check and confirm{flagged ? `, ${flagged} flagged` : ''}</span>}
        {(a.state === 'failed' || a.state === 'interrupted') && <span className="v bad">Split {a.state}</span>}
        <button className="btn sm danger" onClick={() => setDeleting(true)}>Delete assessment</button>
      </div>
      {deleting && (
        <ConfirmDialog title={`Delete ${a.assessment_id}?`} action="Delete assessment" onClose={() => setDeleting(false)}
          onConfirm={() => api(`/versions/${vid}/assessments/${a.assessment_id}`, { method: 'DELETE' }).then(deleted)}>
          Its files and {a.questions.length} question{a.questions.length === 1 ? '' : 's'} are removed, so they leave the assessment review and the summary. Earlier test-drive results stay in the run logs.
        </ConfirmDialog>
      )}
      <div className={`a-body ${open ? 'open' : ''}`} inert={!open}><div>
      {a.state === 'running' && a.run && <RunProgress runId={a.run.run_id} onEnd={reload} />}
      {a.run?.error && a.state !== 'confirmed' && <p className="err">{a.run.error}</p>}

      {a.unmatched_marking_material.length > 0 && (
        <div className="orphans">
          <b>Marking material with no question</b>
          {a.unmatched_marking_material.map((m, i) => <p key={i}>{m}</p>)}
        </div>
      )}

      {qs.length > 0 && (
        <>
          <div className="qs-edit">
            {qs.map((q, i) => (
              <div key={q.question_id} className={q.context !== null && qs.findIndex((x) => x.context === q.context) === i ? 'q-group' : undefined}>
              {q.context !== null && qs.findIndex((x) => x.context === q.context) === i && (
                <div className="ctx">
                  <div className="ctx-h"><b>Context for {sharing(q.context).map(label).join(', ')}</b>
                    {sharing(q.context).length > 1 && <small>editing it changes all {sharing(q.context).length}</small>}</div>
                  <textarea aria-label={`Context for ${sharing(q.context).map(label).join(', ')}`} value={q.context} rows={6}
                    onChange={(e) => setShared(q.context!, e.target.value)} />
                </div>
              )}
              <div className="q-edit">
                <div className="q-top">
                  <b>{q.question_id.replace(`${a.assessment_id}-`, '')}</b>
                  <select aria-label={`Type of ${q.question_id}`} value={q.type} onChange={(e) => set(i, { type: e.target.value as Question['type'] })}>
                    {QTYPES.map((t) => <option key={t} value={t}>{t.replace('_', '/')}</option>)}
                  </select>
                  {q.type === 'code' && <span className="v n">not assessed (code question)</span>}
                  {q.flags?.map((f) => <span className={f === 'Double-check against the source' ? 'v part' : 'v bad'} key={f}>{f}</span>)}
                  <button className="btn del" onClick={() => setQs(qs.filter((_, j) => j !== i))}>Delete</button>
                </div>
                <textarea aria-label={`Text of ${q.question_id}`} value={q.text} rows={2} onChange={(e) => set(i, { text: e.target.value })} />
                {q.options && (
                  <textarea aria-label={`Options of ${q.question_id}`} className="opts" value={q.options.join('\n')} rows={q.options.length}
                    onChange={(e) => set(i, { options: e.target.value.split('\n') })} />
                )}
                <textarea aria-label={`Marking material of ${q.question_id}`} className="mm" placeholder="No marking material: AI exposure won't be assessed for this question"
                  value={q.marking_material ?? ''} rows={2} onChange={(e) => set(i, { marking_material: e.target.value || null })} />
                <details className="own-ctx">
                  <summary>{q.context === null ? 'Add context for this question' : 'Edit the context for this question only'}</summary>
                  <textarea aria-label={`Own context, ${q.question_id}`} value={q.context ?? ''} rows={4} placeholder="Scenario, data or formulas the question needs"
                    onChange={(e) => set(i, { context: e.target.value || null })} />
                </details>
              </div>
              </div>
            ))}
          </div>
          <div className="row-form">
            <button className="btn primary" onClick={confirm}>{a.state === 'confirmed' ? 'Save changes' : 'Confirm questions'}</button>
            {err && <span className="err">{err}</span>}
          </div>
        </>
      )}
      </div></div>
    </section>
  )
}
