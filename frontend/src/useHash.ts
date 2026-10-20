import { useEffect, useState } from 'react'

/** Current hash route split into parts: '#/v/abc/materials' -> ['v', 'abc', 'materials']. */
export function useHash(): string[] {
  const read = () => window.location.hash.replace(/^#\/?/, '').split('/').filter(Boolean)
  const [parts, setParts] = useState(read)
  useEffect(() => {
    const on = () => setParts(read())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return parts
}

export const go = (path: string) => { window.location.hash = path }
