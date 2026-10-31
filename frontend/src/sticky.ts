import { useCallback, useSyncExternalStore } from 'react'

// Lives outside components, so a file read started on a screen still shows when you leave the screen and come back
// (a page reload clears it). A request that finishes while you are away updates it, and the screen shows the result.
const store = new Map<string, unknown>()
const subs = new Set<() => void>()
const subscribe = (cb: () => void) => { subs.add(cb); return () => { subs.delete(cb) } }

/** useState kept per key across unmounts. The setter takes a value, not an updater function. */
export function useSticky<T>(key: string, initial: T) {
  const v = useSyncExternalStore(subscribe, () => {
    if (!store.has(key)) store.set(key, initial)
    return store.get(key) as T
  })
  const set = useCallback((x: T) => { store.set(key, x); subs.forEach((cb) => cb()) }, [key])
  return [v, set] as const
}
