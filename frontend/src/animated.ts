import { flushSync } from 'react-dom'

/** Applies a list change inside a view transition where the browser has one, so removed items fade and the rest slide up.
 * Items that should slide need a unique `viewTransitionName` (see vtName). */
export function animated(update: () => void) {
  if (!document.startViewTransition) return update()
  document.startViewTransition(() => flushSync(update))
}

/** A view-transition name from any ID (names must be CSS identifiers). */
export const vtName = (prefix: string, id: string) => `${prefix}-${id.replace(/[^\w-]/g, '-')}`
