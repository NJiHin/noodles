import { Fragment, useEffect, useState, type ReactNode } from 'react'
import { api } from './api'

export type Nav = { label: string; href: string; on?: boolean; n?: number; divider?: boolean }  // divider: a line above it

/** c-shell layout: left section list, then the page. */
export function Shell({ course, sub, nav, children }: { course: string; sub: string; nav: Nav[]; children: ReactNode }) {
  return (
    <>
      <aside className="side">
        <div className="course"><b>{course}</b><span>{sub}</span></div>
        {nav.map((n) => (
          <Fragment key={n.href}>
            {n.divider && <hr className="side-div" />}
            <a className={n.on ? 'on' : ''} href={n.href}>
              {n.label}{n.n !== undefined && <span className="n">{n.n}</span>}
            </a>
          </Fragment>
        ))}
      </aside>
      {children}
    </>
  )
}

export const fmtDate = (iso: string) =>
  new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })

export function versionNav(vid: string, on: string): Nav[] {
  return [
    { label: 'Courses', href: '#/' },
    { label: 'Materials', href: `#/v/${vid}/materials` },
    { label: 'Course map', href: `#/v/${vid}/map` },
    { label: 'Assessments', href: `#/v/${vid}/assessments` },
    { label: 'Assessment review', href: `#/v/${vid}/review`, divider: true },  // results below; the review runs the test-drive
    { label: 'Summary', href: `#/v/${vid}/summary` },
    { label: 'Changes since last run', href: `#/v/${vid}/changes` },
    { label: 'Method and limitations', href: `#/v/${vid}/method` },
  ].map((n) => ({ ...n, on: n.label === on }))
}

type Version = {
  id: string; course_code: string; created_at: string; map_reviewed_at: string | null; materials_changed_at: string | null
  added_files: { filename: string; week: number }[]; removed_files: { filename: string; week: number }[]
  outdated: { map: boolean; map_confirmed: boolean }
}

// each screen mounts its own shell; the cache keeps the side panel steady when switching screens
const seen = new Map<string, Version>()

/** The version, from the cache at once and then fresh from the API. */
function useVersion(vid: string) {
  const [v, setV] = useState<Version | null>(() => seen.get(vid) ?? null)
  useEffect(() => { api<Version>(`/versions/${vid}`).then((r) => { seen.set(vid, r); setV(r) }).catch(() => setV(null)) }, [vid])
  return v
}

/** Shell for a version's screens: course code and upload date in the side panel. */
export function VersionShell({ vid, on, children }: { vid: string; on: string; children: ReactNode }) {
  const v = useVersion(vid)
  return (
    <Shell course={v?.course_code ?? '…'} sub={v ? `Version of ${fmtDate(v.created_at)}` : ''} nav={versionNav(vid, on)}>
      {children}
    </Shell>
  )
}

export const RerunIcon = () => (
  <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
    <path d="M13 8a5 5 0 1 1-1.5-3.57" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    <path d="M13 2.5v3h-3" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

const fileList = (fs: { filename: string; week: number }[]) =>
  fs.map((f, i) => <span key={f.filename}>{i > 0 && ', '}<b>{f.filename}</b> (week {f.week})</span>)

/** Notice below a screen's title when files were added to or removed from the version after what the screen shows
 * was built (sys-design Stage 0, "Adding files to a course" and "Deleting"). `rebuild` is the course map's Rebuild;
 * `results` gives the questions whose results are from before the change, and a rerun for them. */
export function AddedNotice({ vid, screen, rebuild, results }: {
  vid: string; screen: 'materials' | 'map' | 'results'; rebuild?: () => void
  results?: { outdated: number; total: number; rerun: () => void }
}) {
  const v = useVersion(vid)
  if (!v?.materials_changed_at || !(v.added_files.length || v.removed_files.length)) return null
  const n = v.added_files.length + v.removed_files.length
  const changed = <>
    {v.added_files.length > 0 && <>{fileList(v.added_files)} {v.added_files.length === 1 ? 'was' : 'were'} added</>}
    {v.added_files.length > 0 && v.removed_files.length > 0 && ' and '}
    {v.removed_files.length > 0 && <>{fileList(v.removed_files)} {v.removed_files.length === 1 ? 'was' : 'were'} removed</>}
    {' '}on {fmtDate(v.materials_changed_at)}
  </>
  if (screen === 'materials') return <div className="notice info"><span>{changed}.</span></div>
  if (screen === 'map' && v.outdated.map) {
    const weeks = [...new Set([...v.added_files, ...v.removed_files].map((f) => f.week))].sort((a, b) => a - b).join(', ')
    return (
      <div className="notice warn">
        <span>{changed}, after this map was built. Rebuild the map to include {n === 1 ? 'the change' : 'the changes'}; only week{weeks.includes(',') ? 's' : ''} {weeks} {weeks.includes(',') ? 'are' : 'is'} read again.</span>
        {rebuild && <button className="btn primary" onClick={rebuild}>Rebuild</button>}
      </div>
    )
  }
  if (screen === 'results' && results && results.outdated > 0) {
    const one = results.total === 1
    const which = one ? 'This result is' : `${results.outdated} of ${results.total} questions have results`
    return v.outdated.map_confirmed ? (
      <div className="notice warn"><span>{which} from before {changed}.</span>
        <button className="btn primary rerun" onClick={results.rerun}><RerunIcon />{one ? 'Rerun this question' : `Rerun ${results.outdated} question${results.outdated === 1 ? '' : 's'}`}</button></div>
    ) : (
      <div className="notice warn"><span>{which} from before {changed}. Rebuild and confirm the course map first, then rerun.</span>
        <a className="btn" href={`#/v/${vid}/map`}>Go to course map</a></div>
    )
  }
  return null
}
