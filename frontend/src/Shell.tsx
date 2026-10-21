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
    { label: 'Learning path', href: `#/v/${vid}/learning-path` },
    { label: 'Changes since last run', href: `#/v/${vid}/changes` },
    { label: 'Method and limitations', href: `#/v/${vid}/method` },
  ].map((n) => ({ ...n, on: n.label === on }))
}

type Version = { id: string; course_code: string; created_at: string; map_reviewed_at: string | null }

/** Shell for a version's screens: course code and upload date in the side panel. */
// each screen mounts its own shell; the cache keeps the side panel steady when switching screens
const seen = new Map<string, Version>()

export function VersionShell({ vid, on, children }: { vid: string; on: string; children: ReactNode }) {
  const [v, setV] = useState<Version | null>(() => seen.get(vid) ?? null)
  useEffect(() => { api<Version>(`/versions/${vid}`).then((r) => { seen.set(vid, r); setV(r) }).catch(() => setV(null)) }, [vid])
  return (
    <Shell course={v?.course_code ?? '…'} sub={v ? `Version of ${fmtDate(v.created_at)}` : ''} nav={versionNav(vid, on)}>
      {children}
    </Shell>
  )
}
