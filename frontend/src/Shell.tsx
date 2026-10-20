import type { ReactNode } from 'react'

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
  ].map((n) => ({ ...n, on: n.label === on }))
}
