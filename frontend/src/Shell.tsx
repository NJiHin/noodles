import { useEffect, useState, type ReactNode } from 'react'
import { api } from './api'

export type Nav = { label: string; href: string; on?: boolean; n?: number }

/** c-shell layout: left section list, then the page. */
export function Shell({ course, sub, nav, children }: { course: string; sub: string; nav: Nav[]; children: ReactNode }) {
  return (
    <>
      <aside className="side">
        <div className="course"><b>{course}</b><span>{sub}</span></div>
        {nav.map((n) => (
          <a key={n.href} className={n.on ? 'on' : ''} href={n.href}>
            {n.label}{n.n !== undefined && <span className="n">{n.n}</span>}
          </a>
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
    { label: 'Summary', href: `#/v/${vid}/summary` },
    { label: 'Assessment review', href: `#/v/${vid}/review` },
    { label: 'Changes since last run', href: `#/v/${vid}/changes` },
    { label: 'Method and limitations', href: `#/v/${vid}/method` },
  ].map((n) => ({ ...n, on: n.label === on }))
}

type Version = {
  id: string; course_code: string; created_at: string; map_reviewed_at: string | null; materials_changed_at: string | null
  added_files: { filename: string; week: number }[]; outdated: { map: boolean; map_confirmed: boolean; results: boolean }
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

/** Notice below a screen's title when files were added to the version after what the screen shows was built
 * (sys-design Stage 0, "Adding files to a course"). `rebuild` is the course map's own Rebuild action. */
export function AddedNotice({ vid, screen, rebuild }: { vid: string; screen: 'materials' | 'map' | 'results'; rebuild?: () => void }) {
  const v = useVersion(vid)
  if (!v?.materials_changed_at || !v.added_files.length) return null
  const files = v.added_files.map((f, i) => <span key={f.filename}>{i > 0 && ', '}<b>{f.filename}</b> (week {f.week})</span>)
  const added = <>{files} {v.added_files.length === 1 ? 'was' : 'were'} added on {fmtDate(v.materials_changed_at)}</>
  if (screen === 'materials') return <div className="notice info"><span>{added}.</span></div>
  if (screen === 'map' && v.outdated.map) {
    const weeks = [...new Set(v.added_files.map((f) => f.week))].join(', ')
    return (
      <div className="notice warn">
        <span>{added}, after this map was built. Rebuild the map to include {v.added_files.length === 1 ? 'it' : 'them'}; only week{weeks.includes(',') ? 's' : ''} {weeks} {weeks.includes(',') ? 'are' : 'is'} read again.</span>
        {rebuild && <button className="btn primary" onClick={rebuild}>Rebuild</button>}
      </div>
    )
  }
  if (screen === 'results' && v.outdated.results) {
    return v.outdated.map_confirmed ? (
      <div className="notice warn"><span>These results are from before {added}. Rerun the test-drive.</span>
        <a className="btn" href={`#/v/${vid}/review`}>Go to assessment review</a></div>
    ) : (
      <div className="notice warn"><span>These results are from before {added}. Rebuild and confirm the course map first, then rerun the test-drive.</span>
        <a className="btn" href={`#/v/${vid}/map`}>Go to course map</a></div>
    )
  }
  return null
}
