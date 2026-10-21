import { Fragment, useEffect, useState } from 'react'
import { api } from '../api'
import { PageLink } from '../PageViewer'
import { VersionShell } from '../Shell'
import type { Changes, Cited } from '../types'

type Topic = {
  concept_id: string; name: string; depths: Record<string, string>; questions: string[]
  mentioned: (Cited & { question_id: string; week_cutoff: number })[]; finding: 'only_mentioned' | 'not_assessed' | null
}
type LP = {
  weeks: number[]; assessments: { assessment_id: string; week_cutoff: number }[]; topics: Topic[]
  gaps: { question_id: string; text: string; steps: string[] }[]
}

const D: Record<string, string> = { mentioned: 'm', explained: 'e', worked_example: 'w', practised: 'p' }
const short = (id: string) => id.slice(id.lastIndexOf('-q') + 1).toUpperCase()

/** c3-learning-path: topics by week shaded by depth, the questions using each, and findings. */
export function LearningPath({ vid }: { vid: string }) {
  const [lp, setLp] = useState<LP | null>(null)
  const [err, setErr] = useState('')
  const [chg, setChg] = useState<Record<string, string>>({})
  useEffect(() => { api<LP>(`/versions/${vid}/learning-path`).then(setLp).catch((e) => setErr(e.message)) }, [vid])
  useEffect(() => {
    const d = (x: string | null) => (x ? x.replace('_', ' ') : 'not taught')
    api<Changes>(`/versions/${vid}/changes`).then((c) => setChg(Object.fromEntries((c.map?.depth ?? []).map((x) =>
      [`${x.concept_id}|${x.week}`, `Since last run: ${d(x.before)} to ${d(x.after)}`])))).catch(() => setChg({}))
  }, [vid])
  const due = new Map<number, string[]>()
  lp?.assessments.forEach((a) => due.set(a.week_cutoff, [...(due.get(a.week_cutoff) ?? []), a.assessment_id]))
  const q = (id: string) => `#/v/${vid}/review/${id}`

  return (
    <VersionShell vid={vid} on="Learning path">
      <main className="page lp">
        <div className="page-head">
          <h1>Learning path</h1>
          <p>Each topic in the course map, the weeks it's taught in, and the questions that use it. Questions are linked to topics through the passages the student cited, so a topic used only in an assumed or unsourced step doesn't count as assessed, and a cited passage tagged with several topics counts for all of them.</p>
        </div>
        {err && <p className="err">{err}</p>}
        {lp && (
          <section className="panel">
            <div className="map-head">
              <div><h2>Topics by week</h2><p className="hint">Darker means taught in more depth. Depth is the extractor's judgement, so treat it as a prompt to check, not a verdict. Shaded columns are the weeks assessments cover up to.</p></div>
            </div>
            <div className="map" style={{ gridTemplateColumns: `180px repeat(${lp.weeks.length}, 1fr) 150px 250px` }}>
              <div></div>
              {lp.weeks.map((w) => <div key={w} className={`wk${due.has(w) ? ' due' : ''}`}>{w}{due.has(w) && <small>{due.get(w)!.join(', ')}</small>}</div>)}
              <div className="wk left">Assessed by</div><div className="wk left">Finding</div>
              {lp.topics.map((t) => (
                <Fragment key={t.concept_id}>
                  <div className="tn" title={t.concept_id}>{t.name}</div>
                  {lp.weeks.map((w) => (
                    <div key={w} className={`c${due.has(w) ? ' due' : ''}${chg[`${t.concept_id}|${w}`] ? ' chg' : ''}`}
                      title={chg[`${t.concept_id}|${w}`] ?? t.depths[w]?.replace('_', ' ')}>
                      {t.depths[w] && <span className={`d ${D[t.depths[w]]}`} />}
                    </div>
                  ))}
                  <div className="by">{t.questions.map((id) => <a key={id} className="chip" href={q(id)}>{short(id)}</a>)}</div>
                  <div className={`fd${t.finding === 'only_mentioned' ? ' thin' : t.finding ? ' n' : ''}`}>
                    {t.finding === 'not_assessed' && 'Not assessed'}
                    {t.finding === 'only_mentioned' && t.mentioned[0].slug && (
                      <span title={t.mentioned.map((m) => `${short(m.question_id)} (weeks 1 to ${m.week_cutoff})`).join(', ')}>
                        <PageLink vid={t.mentioned[0].version_id!} slug={t.mentioned[0].slug} page={t.mentioned[0].page!}>
                          Only mentioned, week {t.mentioned[0].week} page {t.mentioned[0].page}
                        </PageLink>
                      </span>
                    )}
                  </div>
                </Fragment>
              ))}
            </div>
            <div className="scale"><span><span className="d m"></span>Mentioned</span><span><span className="d e"></span>Explained</span><span><span className="d w"></span>Worked example</span><span><span className="d p"></span>Practised</span><span><span className="dotchg"></span>Changed since last run</span></div>
          </section>
        )}
        {lp && lp.gaps.length > 0 && (
          <section className="panel">
            <h2>Coverage gaps</h2>
            <p className="hint">Questions with a step that has no source, a citation the grounding checker rejected, or knowledge you rejected. A step with no source isn't linked to any topic above.</p>
            <ul className="list-plain">
              {lp.gaps.map((g) => <li key={g.question_id}><a className="q" href={q(g.question_id)}>{short(g.question_id)}</a><span>{g.steps.join(' · ')}</span><small>{g.text}</small></li>)}
            </ul>
          </section>
        )}
      </main>
    </VersionShell>
  )
}
